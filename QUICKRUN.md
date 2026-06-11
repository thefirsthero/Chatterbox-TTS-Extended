# Quick Run Guide

## Setup

```bash
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Or on Linux/Mac:
source .venv/bin/activate
```

## Prefetch Posts (Offline Mode)

```bash
# Prefetch 20 posts into local cache
python run_shorts_pipeline.py --prefetch-local-posts --prefetch-count 20

# Then run pipeline using cached posts (no Reddit API calls)
python run_shorts_pipeline.py --local-posts --max 3
```

## Default Pipeline (Live Scraping)

```bash
# Generate 3 videos from r/AmItheAsshole hot posts
python run_shorts_pipeline.py

# Generate 5 videos, different sort/subreddit
python run_shorts_pipeline.py --max 5 --subreddit tifu --sort top --top-time week
```

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

- **Final videos**: `output/videos/`
- **Per-post work**: `output/shorts/<post_id>/`
  - `video.mp4` — final short
  - `audio.wav` — narration
  - `script.txt` — full narration text
  - `reddit_card.png` — Reddit post card
  - `subtitles.ass` — subtitle file
- **Local post cache**: `output/cache/local_posts/` (JSON files)
- **Done posts log**: `output/shorts/done_posts.txt`

## Troubleshooting

**RSS timeout or 403 errors**  
→ Network issue; try again or switch sort/subreddit

**Empty video output**  
→ Check `output/shorts/<post_id>/error.log` for details

**No posts passed filters**  
→ Reduce `--min-upvotes` or `--min-body-chars`

**Missing gameplay clips**  
→ Run `python run_shorts_pipeline.py --download-gameplay-only`

---

**See full CLI help:**

```bash
python run_shorts_pipeline.py --help
```
