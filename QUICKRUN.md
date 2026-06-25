# Quick Run Guide

## Setup

```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Or on Linux/Mac:
source .venv/bin/activate
```

## Scraping Strategy

The pipeline automatically falls back through these methods:

1. **OAuth/PRAW** — if Reddit API credentials exist
2. **Public JSON** — blocked since mid-2026, tried for compat
3. **HTML scrape** (old.reddit.com) — **primary fallback**, most reliable
4. **RSS** — last resort fallback (may be killed in future)
5. **Local cache** — if all else fails

No OAuth credentials, API keys, or app registration required.

## Prefetch Posts (Offline Mode)

```bash
# Prefetch 20 posts into local JSON cache
python run_shorts_pipeline.py --prefetch-local-posts --prefetch-count 20

# Then run pipeline using cached posts (no Reddit requests at all)
python run_shorts_pipeline.py --local-posts --max 3
```

## Default Pipeline

```bash
# Generate 3 videos from r/AmItheAsshole hot posts (uses HTML scrape)
python run_shorts_pipeline.py

# Generate 5 videos, different sort/subreddit
python run_shorts_pipeline.py --max 5 --subreddit tifu --sort top --top-time week

# Multi-subreddit batch: process AITAH + TrueOffMyChest + TIFU in one run
python run_shorts_pipeline.py --subreddits "AmItheAsshole,TrueOffMyChest,TIFU" --max 3

# Multi-subreddit with a single subreddit (same as --subreddit but uses multi-batch path)
python run_shorts_pipeline.py --subreddits "TIFU" --max 5
```

## Supported Subreddits

Configured in `reddit_shorts/config.py` → `SUBREDDIT_CONFIGS`:

| Subreddit | Category | Flair Filter |
|-----------|----------|-------------|
| AmItheAsshole | Drama / Moral dilemmas / Conflict | "Not the A-hole", "Asshole", "Everyone Sucks", "No A-holes here" |
| TrueOffMyChest | Emotional stories / Confessions / Personal struggles | None (all flairs) |
| TIFU | Comedy / Embarrassing situations / Funny mistakes | None (all flairs) |

Add new subreddits by adding entries to `SUBREDDIT_CONFIGS` in `config.py`. No code changes required.

## Process Specific Posts

```bash
# Single post by ID
python run_shorts_pipeline.py --post-id 1tbgfyh

# Single post by URL
python run_shorts_pipeline.py --post-url https://www.reddit.com/r/AmItheAsshole/comments/1tbgfyh/...

# Multiple posts from file (one URL/ID per line)
python run_shorts_pipeline.py --post-list-file scripts/post_urls.txt
```

## Filters & Options

```bash
# Apply minimum upvotes/body length filters
python run_shorts_pipeline.py --min-upvotes 3000 --min-body-chars 500

# Disable safety filter (not recommended)
python run_shorts_pipeline.py --no-safety-filter

# Add extra blocked keywords
python run_shorts_pipeline.py --safety-extra-keywords "crypto,nft,gambling"
```

## Gameplay & Testing

```bash
# Download Minecraft clips only
python run_shorts_pipeline.py --download-gameplay-only

# Dry run — show what would process without generating
python run_shorts_pipeline.py --dry-run

# Custom voice profile
python run_shorts_pipeline.py --voice-profile output/voice_profiles/custom.pt
```

## Output Locations

### Per-Subreddit Organization

```
output/
├── shorts/
│   ├── amitheasshole/
│   │   ├── abc123/
│   │   │   ├── video.mp4
│   │   │   ├── audio.wav
│   │   │   ├── script.txt
│   │   │   ├── reddit_card.png
│   │   │   └── subtitles.ass
│   │   └── def456/
│   ├── trueoffmychest/
│   │   └── ghi789/
│   └── tifu/
│       └── jkl012/
├── videos/
│   ├── amitheasshole/
│   │   └── 2026-06-20/
│   │       └── 20260620_120000__amitheasshole__abc123.mp4
│   ├── trueoffmychest/
│   │   └── 2026-06-20/
│   │       └── 20260620_120500__trueoffmychest__ghi789.mp4
│   └── tifu/
│       └── 2026-06-20/
│           └── 20260620_121000__tifu__jkl012.mp4
└── cache/
    ├── reddit_scrapes/     (auto-scrape cache, keyed by subreddit + query)
    └── local_posts/        (--local-posts mode, optionally scoped per subreddit)
```

- **Final videos**: `output/videos/<subreddit>/<YYYY-MM-DD>/`
- **Per-post work**: `output/shorts/<subreddit>/<post_id>/`
  - `video.mp4` — final short
  - `audio.wav` — narration
  - `script.txt` — full narration text
  - `reddit_card.png` — Reddit post card
  - `subtitles.ass` — subtitle file
- **Post cache**: `output/cache/reddit_scrapes/<subreddit>/` (auto-scrape cache)
- **Local post cache**: `output/cache/local_posts/<subreddit>/` (--local-posts mode)
- **Done posts log**: `output/shorts/done_posts.txt`

## Troubleshooting

**Post fetch fails (403, timeout, etc.)**  
→ The pipeline auto-falls back through HTML scrape → RSS → cache. If all fail, check network connectivity or try `--sort top --top-time week` for different content.

**Empty video output**  
→ Check `output/shorts/<post_id>/error.log` for details

**No posts passed filters**  
→ Reduce `--min-upvotes` or `--min-body-chars`. On old.reddit.com listing pages, scores and flairs may differ from the JSON API.

**Missing gameplay clips**  
→ Run `python run_shorts_pipeline.py --download-gameplay-only`

**RSS/HTML scrape returns 0 posts**  
→ Try `--sort top --top-time week` or a different subreddit via `--subreddit`

---

**See full CLI help:**

```bash
python run_shorts_pipeline.py --help
```
