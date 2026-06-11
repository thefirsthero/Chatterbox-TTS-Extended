#!/usr/bin/env python
"""
run_shorts_pipeline.py — CLI entry point for the Reddit Shorts pipeline.

Usage examples:

  # Produce up to 3 videos from r/AmItheAsshole hot posts
  python run_shorts_pipeline.py

  # Produce 5 videos from top posts this week
  python run_shorts_pipeline.py --max 5 --sort top --top-time week

  # Use a different subreddit
  python run_shorts_pipeline.py --subreddit tifu --max 3

    # Tune scraping filters
    python run_shorts_pipeline.py --min-upvotes 1500 --min-body-chars 350 --max-body-chars 3200

  # Dry-run: just print what would be processed
  python run_shorts_pipeline.py --dry-run

  # Process a single post by URL or ID (skips scraping)
  python run_shorts_pipeline.py --post-id abc123

    # Process a single post by full URL
    python run_shorts_pipeline.py --post-url https://www.reddit.com/r/AmItheAsshole/comments/abc123/example/

    # Process many posts from a text file (one URL/ID per line)
    python run_shorts_pipeline.py --post-list-file scripts/post_urls.txt

  # Download gameplay footage and exit
  python run_shorts_pipeline.py --download-gameplay-only
"""

import argparse
import sys
from pathlib import Path


def _setup_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Reddit → ASMR TikTok/Shorts automated pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--max", type=int, default=3, metavar="N",
                   help="Maximum number of videos to produce (default: 3)")
    p.add_argument("--subreddit", default=None,
                   help="Subreddit to scrape (default: from config.py)")
    p.add_argument("--sort", choices=["hot", "top", "new"], default="hot",
                   help="Reddit listing to use (default: hot)")
    p.add_argument("--top-time", choices=["day", "week", "month", "year", "all"],
                   default="week", dest="top_time",
                   help="Time filter when --sort=top (default: week)")
    p.add_argument("--min-upvotes", type=int, default=None, dest="min_upvotes",
                   help="Minimum upvotes filter for scraped posts")
    p.add_argument("--min-body-chars", type=int, default=None, dest="min_body_chars",
                   help="Minimum body length for scraped posts")
    p.add_argument("--max-body-chars", type=int, default=None, dest="max_body_chars",
                   help="Maximum body length for scraped posts")
    p.add_argument("--post-id", default=None, dest="post_id",
                   help="Process a single Reddit post by ID (skips scraping)")
    p.add_argument("--post-url", default=None, dest="post_url",
                   help="Process a single Reddit post by URL (skips scraping)")
    p.add_argument("--post-list-file", default=None, dest="post_list_file",
                   help="Path to text file with Reddit post URLs/IDs (one per line)")
    p.add_argument("--no-dedupe-list", action="store_true",
                   help="Disable de-duplication when using --post-list-file")
    p.add_argument("--no-skip-done", action="store_true",
                   help="Do not skip posts already listed in done_posts.txt")
    p.add_argument("--no-gameplay-download", action="store_true",
                   help="Do not attempt to download gameplay footage automatically")
    p.add_argument("--no-safety-filter", action="store_true",
                   help="Disable blocked-keyword safety filtering")
    p.add_argument("--safety-extra-keywords", default="", dest="safety_extra_keywords",
                   help="Comma-separated extra blocked terms (appended to defaults)")
    p.add_argument("--download-gameplay-only", action="store_true",
                   help="Just download gameplay clips and exit")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be done without generating audio/video")
    p.add_argument("--voice-profile", default=None,
                   help="Path to a .pt voice profile file (overrides config.py)")
    return p.parse_args()


def main() -> int:
    args = _setup_args()

    # Apply CLI overrides to config before importing pipeline
    if args.voice_profile:
        import reddit_shorts.config as cfg
        cfg.VOICE_PROFILE = Path(args.voice_profile)

    subreddit = args.subreddit  # None → pipeline uses config.SUBREDDIT

    import reddit_shorts.config as cfg
    from reddit_shorts.safety import evaluate_post

    extra_terms = [t.strip() for t in args.safety_extra_keywords.split(",") if t.strip()]
    blocked_terms = list(cfg.SAFETY_BLOCKED_TERMS) + extra_terms
    safety_enabled = not args.no_safety_filter

    # ── Download gameplay only ────────────────────────────────────────────
    if args.download_gameplay_only:
        from reddit_shorts.gameplay import download_gameplay_footage
        clips = download_gameplay_footage()
        if clips:
            print(f"Downloaded {len(clips)} clip(s):")
            for c in clips:
                print(f"  {c}")
        else:
            print("No clips downloaded. Check yt-dlp installation.")
        return 0

    # ── Manual single post mode (ID or URL) ───────────────────────────────
    if args.post_id or args.post_url:
        from reddit_shorts.scraper import fetch_post_public, is_post_done

        selector = args.post_url or args.post_id
        print(f"[cli] Fetching single post: {selector}")
        post = fetch_post_public(selector, subreddit_hint=subreddit)

        if is_post_done(post.post_id):
            print(f"[cli] Skipping {post.post_id} — post already processed")
            return 0

        if safety_enabled:
            decision = evaluate_post(post, blocked_terms)
            if decision.blocked:
                print(
                    "[cli] Skipping post due to safety filter: "
                    + ", ".join(decision.matched_terms)
                )
                return 1

        gameplay_clips = None
        if not args.dry_run:
            from reddit_shorts.gameplay import ensure_gameplay_footage
            gameplay_clips = ensure_gameplay_footage(
                auto_download=not args.no_gameplay_download
            )

        if args.dry_run:
            print(f"[DRY RUN] Would process: [{post.flair}] {post.title}")
            return 0

        from reddit_shorts.pipeline import process_post
        result = process_post(
            post,
            gameplay_clips=gameplay_clips,
            safety_filter=safety_enabled,
            blocked_terms=blocked_terms,
        )
        return 0 if result else 1

    # ── Manual list mode (file with URLs/IDs) ─────────────────────────────
    if args.post_list_file:
        from reddit_shorts.scraper import fetch_posts_from_list

        list_path = Path(args.post_list_file)
        if not list_path.exists():
            print(f"[cli] post list file not found: {list_path}")
            return 1

        lines = list_path.read_text(encoding="utf-8").splitlines()
        posts = fetch_posts_from_list(
            lines,
            subreddit_hint=subreddit,
            dedupe=not args.no_dedupe_list,
            skip_done=not args.no_skip_done,
            min_upvotes=args.min_upvotes or 0,
            min_body_chars=args.min_body_chars or 0,
            max_body_chars=args.max_body_chars,
        )
        if not posts:
            print("[cli] No valid posts found in list file.")
            return 1

        print(f"[cli] Loaded {len(posts)} post(s) from {list_path}")

        if safety_enabled:
            safe_posts = []
            skipped = 0
            for post in posts:
                decision = evaluate_post(post, blocked_terms)
                if decision.blocked:
                    skipped += 1
                    print(
                        f"[cli] Skipping {post.post_id} due to safety filter: "
                        + ", ".join(decision.matched_terms)
                    )
                    continue
                safe_posts.append(post)
            posts = safe_posts
            if skipped:
                print(f"[cli] Safety filter skipped {skipped} post(s) in list mode")

        if not posts:
            print("[cli] No safe posts remain after filtering.")
            return 1

        gameplay_clips = None
        if not args.dry_run:
            from reddit_shorts.gameplay import ensure_gameplay_footage
            gameplay_clips = ensure_gameplay_footage(
                auto_download=not args.no_gameplay_download
            )

        produced = 0
        for post in posts[:args.max]:
            if args.dry_run:
                print(f"[DRY RUN] Would process: [{post.flair}] {post.title}")
                continue
            try:
                from reddit_shorts.pipeline import process_post
                result = process_post(
                    post,
                    gameplay_clips=gameplay_clips,
                    safety_filter=safety_enabled,
                    blocked_terms=blocked_terms,
                )
                if result:
                    produced += 1
            except Exception as exc:
                print(f"[cli] Failed {post.post_id}: {exc}")

        return 0 if produced > 0 or args.dry_run else 1

    # ── Batch mode (default) ──────────────────────────────────────────────
    from reddit_shorts.pipeline import run_batch

    produced = run_batch(
        max_videos=args.max,
        subreddit=subreddit or cfg.SUBREDDIT,
        sort=args.sort,
        top_time=args.top_time,
        min_upvotes=args.min_upvotes if args.min_upvotes is not None else cfg.MIN_UPVOTES,
        min_body_chars=args.min_body_chars if args.min_body_chars is not None else cfg.MIN_BODY_CHARS,
        max_body_chars=args.max_body_chars if args.max_body_chars is not None else cfg.MAX_BODY_CHARS,
        auto_download_gameplay=not args.no_gameplay_download,
        dry_run=args.dry_run,
        safety_filter=safety_enabled,
        blocked_terms=blocked_terms,
    )

    return 0 if produced or args.dry_run else 1


if __name__ == "__main__":
    sys.exit(main())
