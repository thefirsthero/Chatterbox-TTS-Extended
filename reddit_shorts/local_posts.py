"""
Local post storage — bypass Reddit API entirely by storing posts as JSON files.

This allows users to:
1. Manually curate posts and save them locally
2. Run the pipeline offline without hitting Reddit's servers
3. Avoid 403 Forbidden errors and OAuth credential requirements

Usage:
    # Add a post from template
    python -c "from reddit_shorts.local_posts import save_post; save_post('title', 'post body', 'author_name', 'aita')"
    
    # Or manually create JSON files in output/cache/local_posts/
    # Then reference them with: python run_shorts_pipeline.py --local-posts
"""

import json
from pathlib import Path
from dataclasses import asdict
from reddit_shorts.scraper import RedditPost
from reddit_shorts import config as cfg

LOCAL_POSTS_DIR = cfg.OUTPUT_DIR.parent / "cache" / "local_posts"


def get_local_posts_dir() -> Path:
    """Return path to local posts storage directory."""
    LOCAL_POSTS_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_POSTS_DIR


def save_post(
    title: str,
    body: str,
    author: str,
    subreddit: str = cfg.SUBREDDIT,
    post_id: str = None,
    upvotes: int = 5000,
    num_comments: int = 100,
) -> Path:
    """
    Save a post as JSON locally (no Reddit API needed).
    
    Args:
        title: Post title
        body: Post body/selftext
        author: Author username
        subreddit: Subreddit name (used for URL generation)
        post_id: Post ID (auto-generated if None)
        upvotes: Upvote count
        num_comments: Comment count
    
    Returns:
        Path to saved JSON file
    """
    import uuid
    
    if not post_id:
        post_id = uuid.uuid4().hex[:6].lower()
    
    post = RedditPost(
        post_id=post_id,
        title=title,
        body=body,
        author=author,
        upvotes=upvotes,
        num_comments=num_comments,
        flair=None,
        url=f"https://reddit.com/r/{subreddit}/comments/{post_id}/",
        subreddit=subreddit,
        top_comments=[],
    )
    
    posts_dir = get_local_posts_dir()
    file_path = posts_dir / f"{post_id}.json"
    
    with file_path.open("w", encoding="utf-8") as f:
        json.dump(asdict(post), f, indent=2, ensure_ascii=False)
    
    print(f"[local_posts] Saved: {file_path}")
    return file_path


def load_local_posts(limit: int = None) -> list[RedditPost]:
    """
    Load all posts from local JSON files.
    
    Args:
        limit: Max posts to load (None = all)
    
    Returns:
        List of RedditPost objects
    """
    posts_dir = get_local_posts_dir()
    
    if not posts_dir.exists():
        return []
    
    posts: list[RedditPost] = []
    done_ids = set()
    
    try:
        from reddit_shorts.scraper import _load_done_posts
        done_ids = _load_done_posts()
    except Exception:
        pass
    
    for json_file in sorted(posts_dir.glob("*.json")):
        if limit and len(posts) >= limit:
            break
        
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            post_id = data.get("post_id", "")
            
            if post_id in done_ids:
                continue
            
            post = RedditPost(
                post_id=str(data.get("post_id", "")),
                title=str(data.get("title", "")),
                body=str(data.get("body", "")),
                author=str(data.get("author", "[local]")),
                upvotes=int(data.get("upvotes", 0)),
                num_comments=int(data.get("num_comments", 0)),
                flair=data.get("flair"),
                url=str(data.get("url", "")),
                subreddit=str(data.get("subreddit", "unknown")),
                top_comments=[str(c) for c in data.get("top_comments", [])],
            )
            posts.append(post)
        except Exception as exc:
            print(f"[local_posts] Error loading {json_file}: {exc}")
    
    print(f"[local_posts] Loaded {len(posts)} posts from {posts_dir}")
    return posts


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        posts = load_local_posts()
        for post in posts:
            print(f"  {post.post_id}: {post.title[:60]}")
    else:
        print(f"Local posts directory: {get_local_posts_dir()}")
        print(f"Usage: python -m reddit_shorts.local_posts list")
