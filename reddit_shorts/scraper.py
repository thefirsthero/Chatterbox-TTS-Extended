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
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

import praw
import requests

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
    resp = requests.get(url, headers=_build_headers(), params=params, timeout=25)
    if resp.status_code != 200:
        raise RuntimeError(f"Public post fetch failed ({resp.status_code}) for {post_id}")

    payload = resp.json()
    if not isinstance(payload, list) or len(payload) < 1:
        raise RuntimeError(f"Unexpected Reddit response for {post_id}")

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
        f"[scraper] Public JSON mode: fetched {fetch_limit} posts → "
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
        print(f"[scraper] OAuth mode: fetched {fetch_limit} posts → {len(posts)} passed filters from r/{subreddit_name}")
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
        except Exception:
            if cached_posts is not None:
                print(f"[scraper] Falling back to cached results for r/{subreddit_name}")
                return cached_posts
            raise
