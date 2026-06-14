"""
reddit_shorts/scraper.py — fetch and filter Reddit posts via PRAW.

Requires environment variables:
    REDDIT_CLIENT_ID      — from https://www.reddit.com/prefs/apps
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT     — optional, defaults to "RedditShorts/1.0"

Set these in a .env file (loaded by pipeline.py via python-dotenv) or export
them in your shell before running the pipeline.
"""

import hashlib
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

import praw
import requests
from bs4 import BeautifulSoup

from reddit_shorts import config as cfg


@dataclass
class RedditPost:
    post_id: str
    title: str
    body: str
    author: str
    upvotes: int
    num_comments: int
    flair: Optional[str]
    url: str
    subreddit: str
    top_comments: list[str] = field(default_factory=list)


def _clean_body(text: str) -> str:
    """Strip Reddit markdown artefacts and normalise whitespace."""
    # Remove edit sections (often meta-noise)
    text = re.sub(r"\n+EDIT[:\s].*", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\n+UPDATE[:\s].*", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove markdown bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    # Strip hyperlinks but keep link text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def _load_done_posts() -> set[str]:
    path = cfg.DONE_POSTS_FILE
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _serialize_post(post: RedditPost) -> dict:
    return {
        "post_id": post.post_id,
        "title": post.title,
        "body": post.body,
        "author": post.author,
        "upvotes": post.upvotes,
        "num_comments": post.num_comments,
        "flair": post.flair,
        "url": post.url,
        "subreddit": post.subreddit,
        "top_comments": post.top_comments,
    }


def _deserialize_post(data: dict) -> RedditPost:
    return RedditPost(
        post_id=str(data.get("post_id") or ""),
        title=str(data.get("title") or ""),
        body=str(data.get("body") or ""),
        author=str(data.get("author") or "[deleted]"),
        upvotes=int(data.get("upvotes", 0) or 0),
        num_comments=int(data.get("num_comments", 0) or 0),
        flair=(data.get("flair") or None),
        url=str(data.get("url") or ""),
        subreddit=str(data.get("subreddit") or "unknown"),
        top_comments=[str(item) for item in data.get("top_comments", []) if str(item).strip()],
    )


def _scrape_cache_query(
    subreddit_name: str,
    fetch_limit: int,
    min_upvotes: int,
    min_body_chars: int,
    max_body_chars: int,
    flair_whitelist: Optional[list[str]],
    sort: str,
    top_time: str,
) -> dict:
    return {
        "subreddit_name": subreddit_name,
        "fetch_limit": int(fetch_limit),
        "min_upvotes": int(min_upvotes),
        "min_body_chars": int(min_body_chars),
        "max_body_chars": int(max_body_chars),
        "flair_whitelist": sorted(flair_whitelist or []),
        "sort": sort,
        "top_time": top_time,
    }


def _scrape_cache_path(query: dict) -> Path:
    payload = json.dumps(query, sort_keys=True, separators=(",", ":"))
    cache_key = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return cfg.SCRAPE_CACHE_DIR / query["subreddit_name"] / f"{cache_key}.json"


def _load_scrape_cache(query: dict) -> list[RedditPost] | None:
    path = _scrape_cache_path(query)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("query") != query:
            return None
        return [_deserialize_post(item) for item in payload.get("posts", [])]
    except Exception:
        return None


def _save_scrape_cache(query: dict, posts: list[RedditPost], source: str) -> Path:
    path = _scrape_cache_path(query)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "query": query,
        "cached_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "count": len(posts),
        "posts": [_serialize_post(post) for post in posts],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def is_post_done(post_id: str) -> bool:
    """Return True if post_id has already been processed."""
    return post_id in _load_done_posts()


def mark_post_done(post_id: str) -> None:
    cfg.DONE_POSTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    done_ids = _load_done_posts()
    if post_id in done_ids:
        return
    with cfg.DONE_POSTS_FILE.open("a", encoding="utf-8") as f:
        f.write(post_id + "\n")


def build_reddit_client() -> praw.Reddit:
    client_id = os.environ.get("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise EnvironmentError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set.\n"
            "Create a Reddit app at https://www.reddit.com/prefs/apps "
            "and add the credentials to your .env file."
        )
    user_agent = os.environ.get("REDDIT_USER_AGENT", "RedditShorts:v1.0 (automated content pipeline)")
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def _build_headers() -> dict[str, str]:
    user_agent = os.environ.get(
        "REDDIT_USER_AGENT",
        "RedditShorts:v1.0 (public-json-fallback)",
    )
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
    }


def _fetch_top_comments_public(subreddit_name: str, post_id: str, limit: int = 25) -> list[str]:
    """Fetch top comments from the public JSON endpoint (no OAuth app required)."""
    url = f"https://www.reddit.com/r/{subreddit_name}/comments/{post_id}.json"
    params = {"limit": str(limit), "sort": "top", "raw_json": "1"}
    try:
        resp = requests.get(url, headers=_build_headers(), params=params, timeout=20)
        if resp.status_code != 200:
            return []
        payload = resp.json()
        if not isinstance(payload, list) or len(payload) < 2:
            return []
        comments_listing = payload[1]
        children = comments_listing.get("data", {}).get("children", [])
        out: list[str] = []
        for child in children:
            data = child.get("data", {})
            body = (data.get("body") or "").strip()
            if len(body) < 20 or len(body) > cfg.MAX_COMMENT_CHARS:
                continue
            lowered = body.lower()
            if "[removed]" in lowered or "[deleted]" in lowered or "i am a bot" in lowered:
                continue
            out.append(body)
            if len(out) >= cfg.TOP_COMMENTS_COUNT:
                break
        return out
    except Exception:
        return []


# ── HTML scraping (old.reddit.com) ──────────────────────────────────────────
# This is the most future-proof approach. old.reddit.com renders pure HTML
# that is trivial to parse. It does not rely on:
#   - The .json API (now blocked without OAuth)
#   - RSS feeds (may be killed)
#   - OAuth2 credentials (no app needed)
# old.reddit.com has maintained the same HTML structure for over a decade.

_HTML_UA = os.environ.get(
    "REDDIT_USER_AGENT",
    "RedditShorts:v1.0 (html-scraper)",
)


def _fetch_post_public_html(post_id: str, subreddit: str | None = None) -> RedditPost:
    """Fetch a single Reddit post by scraping old.reddit.com HTML."""
    slug = f"https://old.reddit.com/r/{subreddit}/comments/{post_id}/" if subreddit else f"https://old.reddit.com/comments/{post_id}/"
    resp = requests.get(slug, headers={"User-Agent": _HTML_UA}, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTML post fetch failed ({resp.status_code}) for {post_id}")

    soup = BeautifulSoup(resp.text, "html.parser")
    thing = soup.find("div", class_="thing", attrs={"data-type": "link"})
    if thing is None:
        raise RuntimeError(f"No post data found in HTML for {post_id}")

    pid_raw = thing.get("data-fullname", "")  # "t3_1tbgfyh"
    pid = pid_raw.replace("t3_", "") if pid_raw else post_id
    found_sub = thing.get("data-subreddit", subreddit or "unknown")
    author = thing.get("data-author", "[deleted]")
    score = int(thing.get("data-score", 0) or 0)
    num_comments = int(thing.get("data-num-comments", 0) or 0)
    permalink = thing.get("data-permalink", f"/r/{found_sub}/comments/{pid}/")

    title_elem = soup.find("a", class_="title")
    title = title_elem.text.strip() if title_elem else ""

    flair_elem = soup.find("span", class_="linkflairlabel")
    flair = flair_elem.text.strip() if flair_elem else None

    # Body is inside the .entry .usertext-body
    body = ""
    entry = thing.find("div", class_="entry")
    if entry:
        utb = entry.find("div", class_="usertext-body")
        if utb:
            md = utb.find("div", class_="md")
            if md:
                body = md.get_text("\n", strip=True)

    # Comments — extracted from .thing divs with data-type="comment"
    top_comments: list[str] = []
    for comment_thing in soup.find_all("div", class_="thing", attrs={"data-type": "comment"}):
        cbody_div = comment_thing.find("div", class_="md")
        if cbody_div is None:
            continue
        ctext = cbody_div.get_text(" ", strip=True)
        if len(ctext) < 20 or len(ctext) > cfg.MAX_COMMENT_CHARS:
            continue
        clower = ctext.lower()
        if "[removed]" in clower or "[deleted]" in clower or "i am a bot" in clower:
            continue
        top_comments.append(ctext)
        if len(top_comments) >= cfg.TOP_COMMENTS_COUNT:
            break

    return RedditPost(
        post_id=pid,
        title=title,
        body=_clean_body(body),
        author=author,
        upvotes=score,
        num_comments=num_comments,
        flair=flair,
        url=f"https://reddit.com{permalink}",
        subreddit=found_sub,
        top_comments=top_comments,
    )


def _scrape_posts_public_html(
    subreddit_name: str,
    fetch_limit: int,
    min_upvotes: int,
    min_body_chars: int,
    max_body_chars: int,
    flair_whitelist: list[str] | None,
    skip_done: bool,
    sort: str,
    top_time: str,
) -> list[RedditPost]:
    """Scrape a subreddit listing from old.reddit.com HTML."""
    done = _load_done_posts() if skip_done else set()

    if sort == "top":
        list_url = f"https://old.reddit.com/r/{subreddit_name}/top/"
        params: dict[str, str] = {"t": top_time, "limit": str(fetch_limit)}
    elif sort == "new":
        list_url = f"https://old.reddit.com/r/{subreddit_name}/new/"
        params = {"limit": str(fetch_limit)}
    else:
        list_url = f"https://old.reddit.com/r/{subreddit_name}/hot/"
        params = {"limit": str(fetch_limit)}

    resp = requests.get(
        list_url,
        headers={"User-Agent": _HTML_UA},
        params=params,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Public HTML listing request failed ({resp.status_code}) for r/{subreddit_name}"
        )

    soup = BeautifulSoup(resp.text, "html.parser")
    things = soup.find_all("div", class_="thing", attrs={"data-type": "link"})

    posts: list[RedditPost] = []
    for thing in things:
        pid_raw = thing.get("data-fullname", "")
        pid = pid_raw.replace("t3_", "") if pid_raw else ""
        if not pid or pid in done:
            continue

        score = int(thing.get("data-score", 0) or 0)
        if score < min_upvotes:
            continue

        domain = thing.get("data-domain", "")
        if domain and not domain.startswith("self."):
            continue  # skip link posts, only keep self/text posts

        title_elem = thing.find("a", class_="title")
        title = title_elem.text.strip() if title_elem else ""
        if not title:
            continue

        author = thing.get("data-author", "[deleted]")
        found_sub = thing.get("data-subreddit", subreddit_name)
        num_comments = int(thing.get("data-num-comments", 0) or 0)
        permalink = thing.get("data-permalink", f"/r/{found_sub}/comments/{pid}/")

        # For listing pages, the full body is not available without expanding.
        # We fetch the individual post page to get the body.
        # To keep things fast, fetch the body in a separate pass.
        # For now, set body empty and do a follow-up fetch.
        body = ""
        expando = thing.find("div", class_="expando")
        if expando:
            md = expando.find("div", class_="md")
            if md:
                body = md.get_text("\n", strip=True)

        # On listing pages, body is often empty (expando collapsed).
        # Don't filter by body length here; do it after the follow-up fetch below.
        if max_body_chars is not None and len(body) > max_body_chars:
            continue

        flair_elem = thing.find("span", class_="linkflairlabel")
        flair = flair_elem.text.strip() if flair_elem else None
        if flair_whitelist and not any(allowed.lower() in (flair or "").lower() for allowed in flair_whitelist):
            continue

        posts.append(
            RedditPost(
                post_id=pid,
                title=title,
                body=_clean_body(body),
                author=author,
                upvotes=score,
                num_comments=num_comments,
                flair=flair,
                url=f"https://reddit.com{permalink}",
                subreddit=found_sub,
                top_comments=[],
            )
        )

    # For posts that need body fetched individually, do parallel fetches
    posts_to_fetch = [p for p in posts if len(p.body) < min_body_chars or not p.body]
    if posts_to_fetch:
        print(f"[scraper] HTML mode: fetching full body for {len(posts_to_fetch)} post(s)...")
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            def _fetch_body(fp: RedditPost) -> RedditPost | None:
                try:
                    full = _fetch_post_public_html(fp.post_id, subreddit=fp.subreddit)
                    fp.body = full.body
                    fp.top_comments = full.top_comments
                    return fp
                except Exception:
                    return None
            results = list(executor.map(_fetch_body, posts_to_fetch))
        # Track which post_ids were successfully enriched
        enriched_ids: set[str] = set()
        for r in results:
            if r is not None:
                enriched_ids.add(r.post_id)
        # Remove posts that still don't meet body length criteria after fetch
        posts = [
            p for p in posts
            if len(p.body) >= min_body_chars
            and (max_body_chars is None or len(p.body) <= max_body_chars)
            and (p.post_id not in posts_to_fetch or p.post_id in enriched_ids)
        ]

    posts.sort(key=lambda p: p.upvotes, reverse=True)
    print(
        f"[scraper] Public HTML mode: fetched {fetch_limit} posts -> "
        f"{len(posts)} passed filters from r/{subreddit_name}"
    )
    return posts


def _strip_html_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()


def _clean_rss_body(text: str) -> str:
    text = _strip_html_tags(text)
    # Remove Reddit metadata appended to the post preview
    text = re.sub(
        r"\s*submitted by\s+/u/[^\s]+\s+to\s+r/[^\s]+.*$",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"\s*\[link\].*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\s*\[comments\].*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


def _xml_find_text(element: ET.Element, *names: str) -> str:
    for child in element.iter():
        tag = child.tag
        if not isinstance(tag, str):
            continue
        if any(tag.endswith(name) for name in names):
            if child.text and child.text.strip():
                return child.text.strip()
    return ""


def _xml_find_link(element: ET.Element) -> str:
    for child in element.iter():
        tag = child.tag
        if not isinstance(tag, str):
            continue
        if tag.endswith("link"):
            href = child.get("href") or (child.text.strip() if child.text else "")
            if not href:
                continue
            rel = (child.get("rel") or "").lower()
            if rel and rel != "self":
                return href.strip()
            if not rel:
                return href.strip()
    return ""


def _fetch_post_public_rss(post_id: str, subreddit: str | None = None) -> RedditPost:
    generic_rss_url = f"https://www.reddit.com/comments/{post_id}/.rss"
    rss_url = generic_rss_url
    if subreddit:
        rss_url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/.rss"

    resp = requests.get(
        rss_url,
        headers={"User-Agent": os.environ.get("REDDIT_USER_AGENT", "RedditShorts:v1.0 (rss-fallback)")},
        timeout=25,
    )
    if resp.status_code == 404 and rss_url != generic_rss_url:
        resp = requests.get(
            generic_rss_url,
            headers={"User-Agent": os.environ.get("REDDIT_USER_AGENT", "RedditShorts:v1.0 (rss-fallback)")},
            timeout=25,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Public RSS post fetch failed ({resp.status_code}) for {post_id}")

    root = ET.fromstring(resp.text)
    item = next((el for el in root.iter() if isinstance(el.tag, str) and el.tag.endswith("item")), None)
    if item is None:
        item = next((el for el in root.iter() if isinstance(el.tag, str) and el.tag.endswith("entry")), None)
    if item is None:
        raise RuntimeError(f"No RSS item returned for {post_id}")

    title = _xml_find_text(item, "title")
    link = _xml_find_link(item)
    body = _clean_rss_body(_xml_find_text(item, "description", "content", "summary"))
    author = _xml_find_text(item, "name", "author", "creator") or "[deleted]"
    subreddit_name = subreddit or "unknown"
    if not link and title:
        link = f"https://www.reddit.com/comments/{post_id}/"
    if subreddit_name == "unknown" and link:
        try:
            _, extracted_sub = _extract_post_id_and_subreddit(link)
            if extracted_sub:
                subreddit_name = extracted_sub
        except Exception:
            pass

    return RedditPost(
        post_id=post_id,
        title=title,
        body=_clean_body(body),
        author=author,
        upvotes=0,
        num_comments=0,
        flair=None,
        url=link or f"https://reddit.com/comments/{post_id}/",
        subreddit=subreddit_name,
        top_comments=[],
    )


def _scrape_posts_public_rss(
    subreddit_name: str,
    fetch_limit: int,
    min_upvotes: int,
    min_body_chars: int,
    max_body_chars: int,
    flair_whitelist: Optional[list[str]],
    skip_done: bool,
    sort: str,
    top_time: str,
) -> list[RedditPost]:
    done = _load_done_posts() if skip_done else set()

    if sort == "hot":
        list_url = f"https://www.reddit.com/r/{subreddit_name}/hot.rss"
    elif sort == "new":
        list_url = f"https://www.reddit.com/r/{subreddit_name}/new.rss"
    else:
        list_url = f"https://www.reddit.com/r/{subreddit_name}/top.rss"

    params = {"limit": str(fetch_limit)}
    if sort == "top":
        params["t"] = top_time

    resp = requests.get(list_url, headers={"User-Agent": os.environ.get("REDDIT_USER_AGENT", "RedditShorts:v1.0 (rss-fallback)")}, params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Public Reddit RSS request failed ({resp.status_code}). "
            "Try again later or switch subreddit/sort."
        )

    root = ET.fromstring(resp.text)
    items = [el for el in root.iter() if isinstance(el.tag, str) and (el.tag.endswith("item") or el.tag.endswith("entry"))]
    posts: list[RedditPost] = []

    if min_upvotes > 0:
        print("[scraper] RSS mode cannot enforce min_upvotes; ignoring score filter.")

    for item in items:
        title = _xml_find_text(item, "title")
        link = _xml_find_link(item)
        body = _clean_rss_body(_xml_find_text(item, "description", "content", "summary"))
        author = _xml_find_text(item, "name", "author", "creator") or "[deleted]"

        try:
            post_id, _ = _extract_post_id_and_subreddit(link)
        except Exception:
            continue
        if not post_id or post_id in done:
            continue

        if len(body) < min_body_chars or (max_body_chars is not None and len(body) > max_body_chars):
            continue

        flair = None
        score = 0

        posts.append(
            RedditPost(
                post_id=post_id,
                title=title,
                body=_clean_body(body),
                author=author,
                upvotes=score,
                num_comments=0,
                flair=flair,
                url=link or f"https://reddit.com/r/{subreddit_name}/comments/{post_id}/",
                subreddit=subreddit_name,
                top_comments=[],
            )
        )

    posts.sort(key=lambda p: p.upvotes, reverse=True)
    print(
        f"[scraper] Public RSS mode: fetched {fetch_limit} posts -> "
        f"{len(posts)} passed filters from r/{subreddit_name}"
    )
    return posts


def save_posts_to_local_cache(
    posts: list[RedditPost],
    output_dir: Path | None = None,
) -> list[Path]:
    """Save RedditPost objects as JSON files for offline local post mode."""
    output_dir = Path(output_dir) if output_dir is not None else cfg.OUTPUT_DIR.parent / "cache" / "local_posts"
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[Path] = []
    for post in posts:
        out_path = output_dir / f"{post.post_id}.json"
        out_path.write_text(
            json.dumps(_serialize_post(post), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        saved_files.append(out_path)
    return saved_files


def prefetch_posts_to_local_cache(
    count: int = 20,
    subreddit_name: str = cfg.SUBREDDIT,
    sort: str = "hot",
    top_time: str = "week",
    skip_done: bool = True,
) -> int:
    """Fetch a batch of posts and save them to local JSON storage."""
    print(
        f"[scraper] Prefetching up to {count} posts from r/{subreddit_name} "
        f"(sort={sort}, top_time={top_time}, skip_done={skip_done})"
    )
    posts = scrape_posts(
        subreddit_name=subreddit_name,
        fetch_limit=max(count * 3, 50),
        desired_count=count,
        skip_done=skip_done,
        sort=sort,
        top_time=top_time,
    )
    if not posts:
        print(f"[scraper] No posts found to prefetch for r/{subreddit_name}.")
        return 0

    saved_files = save_posts_to_local_cache(posts[:count])
    print(f"[scraper] Saved {len(saved_files)} posts to {cfg.OUTPUT_DIR.parent / 'cache' / 'local_posts'}")
    return len(saved_files)


def _extract_post_id_and_subreddit(post_url: str) -> tuple[str, str]:
    """Extract (post_id, subreddit) from a Reddit post URL."""
    parsed = urlparse(post_url)
    parts = [p for p in parsed.path.split("/") if p]
    # Expected forms include:
    # /r/<subreddit>/comments/<post_id>/...
    # /comments/<post_id>/...
    post_id = ""
    subreddit = ""

    if len(parts) >= 4 and parts[0] == "r" and parts[2] == "comments":
        subreddit = parts[1]
        post_id = parts[3]
    elif len(parts) >= 2 and parts[0] == "comments":
        post_id = parts[1]

    if not post_id:
        raise ValueError(f"Could not parse Reddit post ID from URL: {post_url}")
    return post_id, subreddit


def _extract_post_id(entry: str) -> str:
    """Extract post ID from either a URL or a raw ID string."""
    raw = entry.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        post_id, _ = _extract_post_id_and_subreddit(raw)
        return post_id.lower()
    if not re.fullmatch(r"[a-z0-9]+", raw, flags=re.IGNORECASE):
        raise ValueError(f"Invalid Reddit post id: {raw}")
    return raw.lower()


def fetch_post_public(post_id_or_url: str, subreddit_hint: str | None = None) -> RedditPost:
    """
    Fetch one Reddit post via public JSON endpoints by ID or URL.

    Useful fallback when API app creation is unavailable.
    """
    raw = post_id_or_url.strip()
    if not raw:
        raise ValueError("post_id_or_url cannot be empty")

    if raw.startswith("http://") or raw.startswith("https://"):
        post_id, parsed_sub = _extract_post_id_and_subreddit(raw)
        subreddit = subreddit_hint or parsed_sub
    else:
        post_id = raw
        subreddit = subreddit_hint or ""

    if not re.fullmatch(r"[a-z0-9]+", post_id, flags=re.IGNORECASE):
        raise ValueError(f"Invalid Reddit post id: {post_id}")

    # Post JSON endpoint works with ID-only URLs.
    url = f"https://www.reddit.com/comments/{post_id}.json"
    params = {"raw_json": "1", "sort": "top", "limit": "50"}
    try:
        resp = requests.get(url, headers=_build_headers(), params=params, timeout=25)
        if resp.status_code != 200:
            raise RuntimeError(f"Public post fetch failed ({resp.status_code}) for {post_id}")

        payload = resp.json()
        if not isinstance(payload, list) or len(payload) < 1:
            raise RuntimeError(f"Unexpected Reddit response for {post_id}")
    except Exception:
        # JSON blocked (403) → try HTML scrape, then RSS as last resort
        try:
            return _fetch_post_public_html(post_id, subreddit=subreddit)
        except Exception:
            return _fetch_post_public_rss(post_id, subreddit=subreddit)

    listing = payload[0]
    children = listing.get("data", {}).get("children", [])
    if not children:
        raise RuntimeError(f"No post data returned for {post_id}")

    data = children[0].get("data", {})
    if not subreddit:
        subreddit = data.get("subreddit") or "unknown"

    title = data.get("title") or ""
    body = _clean_body(data.get("selftext") or "")
    author = data.get("author") or "[deleted]"
    upvotes = int(data.get("score", 0) or 0)
    num_comments = int(data.get("num_comments", 0) or 0)
    flair = (data.get("link_flair_text") or "").strip() or None
    permalink = data.get("permalink") or f"/r/{subreddit}/comments/{post_id}/"

    top_comments: list[str] = []
    if len(payload) > 1:
        comments_listing = payload[1]
        comment_children = comments_listing.get("data", {}).get("children", [])
        for child in comment_children:
            cdata = child.get("data", {})
            cbody = (cdata.get("body") or "").strip()
            if len(cbody) < 20 or len(cbody) > cfg.MAX_COMMENT_CHARS:
                continue
            lowered = cbody.lower()
            if "[removed]" in lowered or "[deleted]" in lowered or "i am a bot" in lowered:
                continue
            top_comments.append(cbody)
            if len(top_comments) >= cfg.TOP_COMMENTS_COUNT:
                break

    return RedditPost(
        post_id=post_id,
        title=title,
        body=body,
        author=author,
        upvotes=upvotes,
        num_comments=num_comments,
        flair=flair,
        url=f"https://reddit.com{permalink}",
        subreddit=subreddit,
        top_comments=top_comments,
    )


def save_posts_to_local_cache(
    posts: list[RedditPost],
    output_dir: Path | None = None,
) -> list[Path]:
    """Save RedditPost objects as JSON files for offline local post mode."""
    output_dir = Path(output_dir) if output_dir is not None else cfg.OUTPUT_DIR.parent / "cache" / "local_posts"
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files: list[Path] = []
    for post in posts:
        out_path = output_dir / f"{post.post_id}.json"
        out_path.write_text(
            json.dumps(_serialize_post(post), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        saved_files.append(out_path)
    return saved_files


def prefetch_posts_to_local_cache(
    count: int = 20,
    subreddit_name: str = cfg.SUBREDDIT,
    sort: str = "hot",
    top_time: str = "week",
    skip_done: bool = True,
) -> int:
    """Fetch a batch of posts and save them to local JSON storage."""
    print(
        f"[scraper] Prefetching up to {count} posts from r/{subreddit_name} "
        f"(sort={sort}, top_time={top_time}, skip_done={skip_done})"
    )
    posts = scrape_posts(
        subreddit_name=subreddit_name,
        fetch_limit=max(count * 3, 50),
        desired_count=count,
        skip_done=skip_done,
        sort=sort,
        top_time=top_time,
    )
    if not posts:
        print(f"[scraper] No posts found to prefetch for r/{subreddit_name}.")
        return 0

    saved_files = save_posts_to_local_cache(posts[:count])
    print(f"[scraper] Saved {len(saved_files)} posts to {cfg.OUTPUT_DIR.parent / 'cache' / 'local_posts'}")
    return len(saved_files)


def fetch_posts_from_list(
    entries: list[str],
    subreddit_hint: str | None = None,
    dedupe: bool = True,
    skip_done: bool = True,
    min_upvotes: int = 0,
    min_body_chars: int = 0,
    max_body_chars: int | None = None,
) -> list[RedditPost]:
    """
    Fetch multiple posts from a list of IDs/URLs; skips invalid entries.

    Enhancements:
    - dedupe repeated URLs/IDs by canonical post id
    - optionally skip already processed posts from done_posts.txt
    - apply minimal quality filters so manual lists can stay noisy
    """
    posts: list[RedditPost] = []
    seen_ids: set[str] = set()
    done_ids = _load_done_posts() if skip_done else set()

    total_entries = 0
    skipped_duplicates = 0
    skipped_done = 0
    skipped_filters = 0

    for raw in entries:
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        total_entries += 1
        try:
            post_id = _extract_post_id(item)
            if dedupe and post_id in seen_ids:
                skipped_duplicates += 1
                continue
            seen_ids.add(post_id)

            if post_id in done_ids:
                skipped_done += 1
                continue

            post = fetch_post_public(item, subreddit_hint=subreddit_hint)

            if post.upvotes < max(0, int(min_upvotes)):
                skipped_filters += 1
                continue
            if len(post.body or "") < max(0, int(min_body_chars)):
                skipped_filters += 1
                continue
            if max_body_chars is not None and len(post.body or "") > int(max_body_chars):
                skipped_filters += 1
                continue

            posts.append(post)
            time.sleep(0.3)
        except Exception as exc:
            print(f"[scraper] Skipping entry {item!r}: {exc}")

    print(
        "[scraper] Manual list mode: "
        f"entries={total_entries}, loaded={len(posts)}, "
        f"duplicates={skipped_duplicates}, done={skipped_done}, filtered={skipped_filters}"
    )
    return posts


def _scrape_posts_public_json(
    subreddit_name: str,
    fetch_limit: int,
    min_upvotes: int,
    min_body_chars: int,
    max_body_chars: int,
    flair_whitelist: Optional[list[str]],
    skip_done: bool,
    sort: str,
    top_time: str,
) -> list[RedditPost]:
    """
    Scrape posts using Reddit's public JSON listing endpoints.

    This mode avoids app credentials and is useful when Reddit app creation is
    restricted for your account. It is more rate-limited than OAuth mode.
    """
    done = _load_done_posts() if skip_done else set()

    base = f"https://www.reddit.com/r/{subreddit_name}"
    if sort == "top":
        list_url = f"{base}/top.json"
    elif sort == "new":
        list_url = f"{base}/new.json"
    else:
        list_url = f"{base}/hot.json"

    params = {
        "limit": str(fetch_limit),
        "raw_json": "1",
    }
    if sort == "top":
        params["t"] = top_time

    resp = requests.get(list_url, headers=_build_headers(), params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Public Reddit JSON request failed ({resp.status_code}). "
            "Try again later or switch subreddit/sort."
        )

    payload = resp.json()
    children = payload.get("data", {}).get("children", [])

    posts: list[RedditPost] = []

    for child in children:
        data = child.get("data", {})
        post_id = data.get("id", "")
        if not post_id or post_id in done:
            continue

        if data.get("over_18"):
            continue
        if not data.get("is_self", False):
            continue

        score = int(data.get("score", 0) or 0)
        if score < min_upvotes:
            continue

        body = _clean_body(data.get("selftext") or "")
        if not (min_body_chars <= len(body) <= max_body_chars):
            continue

        flair = (data.get("link_flair_text") or "").strip()
        if flair_whitelist:
            if not any(allowed.lower() in flair.lower() for allowed in flair_whitelist):
                continue

        author_name = data.get("author") or "[deleted]"
        permalink = data.get("permalink") or f"/r/{subreddit_name}/comments/{post_id}/"

        # Light delay to avoid hammering endpoints when pulling comments.
        time.sleep(0.35)
        top_comments = _fetch_top_comments_public(subreddit_name, post_id)

        posts.append(
            RedditPost(
                post_id=post_id,
                title=data.get("title") or "",
                body=body,
                author=author_name,
                upvotes=score,
                num_comments=int(data.get("num_comments", 0) or 0),
                flair=flair or None,
                url=f"https://reddit.com{permalink}",
                subreddit=subreddit_name,
                top_comments=top_comments,
            )
        )

    posts.sort(key=lambda p: p.upvotes, reverse=True)
    print(
        f"[scraper] Public JSON mode: fetched {fetch_limit} posts -> "
        f"{len(posts)} passed filters from r/{subreddit_name}"
    )
    return posts


def scrape_posts(
    subreddit_name: str = cfg.SUBREDDIT,
    fetch_limit: int = cfg.POST_LIMIT_FETCH,
    min_upvotes: int = cfg.MIN_UPVOTES,
    min_body_chars: int = cfg.MIN_BODY_CHARS,
    max_body_chars: int = cfg.MAX_BODY_CHARS,
    desired_count: int | None = None,
    flair_whitelist: Optional[list[str]] = None,
    skip_done: bool = True,
    sort: str = "hot",          # "hot" | "top" | "new"
    top_time: str = "week",     # only used when sort="top"
) -> list[RedditPost]:
    """
    Return a filtered list of RedditPost objects ready for narration.

    Psychology selection criteria:
    - High upvote count → already proven engagement bait
    - Resolved flair → the story has a satisfying conclusion to tease
    - Body length in range → long enough for a real story, short enough for Shorts
    - Not NSFW → platform-safe
    """
    if flair_whitelist is None:
        flair_whitelist = cfg.FLAIR_WHITELIST

    query = _scrape_cache_query(
        subreddit_name=subreddit_name,
        fetch_limit=fetch_limit,
        min_upvotes=min_upvotes,
        min_body_chars=min_body_chars,
        max_body_chars=max_body_chars,
        flair_whitelist=flair_whitelist,
        sort=sort,
        top_time=top_time,
    )
    desired_count = desired_count or fetch_limit
    done_ids = _load_done_posts() if skip_done else set()

    cached_posts = _load_scrape_cache(query)
    if cached_posts is not None:
        cached_posts = [post for post in cached_posts if post.post_id not in done_ids]
        if len(cached_posts) >= desired_count:
            print(
                f"[scraper] Cache hit: loaded {len(cached_posts)} post(s) for r/{subreddit_name} "
                f"(sort={sort}, top_time={top_time})"
            )
            return cached_posts
        print(
            f"[scraper] Cache hit but only {len(cached_posts)} post(s) remain after done-post filtering; "
            "refreshing live source..."
        )

    # Prefer OAuth/PRAW mode when credentials are present, but gracefully
    # fall back to public JSON mode for accounts blocked from app creation.
    try:
        reddit = build_reddit_client()
        done = done_ids

        subreddit = reddit.subreddit(subreddit_name)
        if sort == "top":
            submissions = subreddit.top(time_filter=top_time, limit=fetch_limit)
        elif sort == "new":
            submissions = subreddit.new(limit=fetch_limit)
        else:
            submissions = subreddit.hot(limit=fetch_limit)

        posts: list[RedditPost] = []

        for submission in submissions:
            if submission.id in done:
                continue
            if submission.over_18:
                continue
            if not submission.is_self:
                continue
            if submission.score < min_upvotes:
                continue

            body = _clean_body(submission.selftext or "")
            if not (min_body_chars <= len(body) <= max_body_chars):
                continue

            flair = submission.link_flair_text or ""
            if flair_whitelist:
                if not any(allowed.lower() in flair.lower() for allowed in flair_whitelist):
                    continue

            # Collect top-level comments only
            try:
                submission.comments.replace_more(limit=0)
                top_comments: list[str] = []
                for comment in submission.comments[:20]:
                    if not hasattr(comment, "body"):
                        continue
                    cbody = comment.body.strip()
                    if len(cbody) < 20 or len(cbody) > cfg.MAX_COMMENT_CHARS:
                        continue
                    if any(kw in cbody.lower() for kw in ["[removed]", "[deleted]", "i am a bot"]):
                        continue
                    top_comments.append(cbody)
                    if len(top_comments) >= cfg.TOP_COMMENTS_COUNT:
                        break
            except Exception:
                top_comments = []

            author_name = "[deleted]"
            try:
                if submission.author:
                    author_name = submission.author.name
            except Exception:
                pass

            posts.append(RedditPost(
                post_id=submission.id,
                title=submission.title,
                body=body,
                author=author_name,
                upvotes=submission.score,
                num_comments=submission.num_comments,
                flair=flair or None,
                url=f"https://reddit.com{submission.permalink}",
                subreddit=subreddit_name,
                top_comments=top_comments,
            ))

        posts.sort(key=lambda p: p.upvotes, reverse=True)
        _save_scrape_cache(query, posts, source="oauth")
        print(f"[scraper] OAuth mode: fetched {fetch_limit} posts -> {len(posts)} passed filters from r/{subreddit_name}")
        return posts

    except Exception as exc:
        print(f"[scraper] OAuth mode unavailable ({exc}). Falling back to public JSON mode.")
        try:
            posts = _scrape_posts_public_json(
                subreddit_name=subreddit_name,
                fetch_limit=fetch_limit,
                min_upvotes=min_upvotes,
                min_body_chars=min_body_chars,
                max_body_chars=max_body_chars,
                flair_whitelist=flair_whitelist,
                skip_done=skip_done,
                sort=sort,
                top_time=top_time,
            )
            _save_scrape_cache(query, posts, source="public-json")
            return posts
        except Exception as json_exc:
            print(f"[scraper] Public JSON failed ({json_exc}). Trying HTML scrape mode...")
            try:
                posts = _scrape_posts_public_html(
                    subreddit_name=subreddit_name,
                    fetch_limit=fetch_limit,
                    min_upvotes=min_upvotes,
                    min_body_chars=min_body_chars,
                    max_body_chars=max_body_chars,
                    flair_whitelist=flair_whitelist,
                    skip_done=skip_done,
                    sort=sort,
                    top_time=top_time,
                )
                _save_scrape_cache(query, posts, source="public-html")
                return posts
            except Exception as html_exc:
                print(f"[scraper] HTML mode failed ({html_exc}). Falling back to RSS mode.")
                try:
                    posts = _scrape_posts_public_rss(
                        subreddit_name=subreddit_name,
                        fetch_limit=fetch_limit,
                        min_upvotes=min_upvotes,
                        min_body_chars=min_body_chars,
                        max_body_chars=max_body_chars,
                        flair_whitelist=flair_whitelist,
                        skip_done=skip_done,
                        sort=sort,
                        top_time=top_time,
                    )
                    _save_scrape_cache(query, posts, source="public-rss")
                    return posts
                except Exception:
                    if cached_posts is not None:
                        print(f"[scraper] Falling back to cached results for r/{subreddit_name}")
                        return cached_posts
                    raise


def generate_post_urls_to_file(
    output_file: str | Path,
    subreddit_name: str = cfg.SUBREDDIT,
    count: int = 20,
    sort: str = "hot",
    top_time: str = "week",
    skip_done: bool = True,
) -> int:
    """
    Fetch posts from a subreddit and write their URLs to a file (one per line).

    This automates sourcing for --post-list-file mode. Useful for repeated bulk runs
    without manual curation.

    Returns: number of URLs written to file.
    """
    output_path = Path(output_file)
    try:
        print(f"[scraper] Fetching {count} posts from r/{subreddit_name} (sort={sort})...")
        posts = scrape_posts(
            subreddit_name=subreddit_name,
            fetch_limit=count * 2,  # Fetch extra to account for filtering
            desired_count=count,
            skip_done=skip_done,
            sort=sort,
            top_time=top_time,
        )

        if not posts:
            print(f"[scraper] No posts found for r/{subreddit_name}. Output file not updated.")
            return 0

        # Write URLs (one per line)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            for post in posts[:count]:
                f.write(post.url + "\n")

        print(f"[scraper] Wrote {len(posts[:count])} post URLs to {output_path}")
        return len(posts[:count])

    except Exception as exc:
        print(f"[scraper] Error generating post list: {exc}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Automate Reddit post fetching for local post list mode.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="scripts/post_urls_generated.txt",
        help="Output file for post URLs (default: scripts/post_urls_generated.txt)",
    )
    parser.add_argument(
        "--subreddit",
        type=str,
        default=cfg.SUBREDDIT,
        help=f"Subreddit to scrape (default: {cfg.SUBREDDIT})",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of posts to fetch (default: 20)",
    )
    parser.add_argument(
        "--sort",
        type=str,
        choices=["hot", "top", "new"],
        default="hot",
        help="Sort order (default: hot)",
    )
    parser.add_argument(
        "--top-time",
        type=str,
        default="week",
        help="Time filter for --sort=top (default: week)",
    )
    parser.add_argument(
        "--skip-done",
        action="store_true",
        default=True,
        help="Skip posts already in done_posts.txt (default: true)",
    )

    args = parser.parse_args()
    count = generate_post_urls_to_file(
        output_file=args.output,
        subreddit_name=args.subreddit,
        count=args.count,
        sort=args.sort,
        top_time=args.top_time,
        skip_done=args.skip_done,
    )
    exit(0 if count > 0 else 1)
