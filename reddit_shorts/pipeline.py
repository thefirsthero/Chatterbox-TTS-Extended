"""
reddit_shorts/pipeline.py — orchestrate the full Reddit → TikTok/Shorts pipeline.

Run via:
    python run_shorts_pipeline.py [options]

Or import and call process_post() from your own script.
"""

import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# Load .env if present (python-dotenv optional dependency)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from reddit_shorts import config as cfg
from reddit_shorts.gameplay import ensure_gameplay_footage
from reddit_shorts.post_renderer import render_hook_overlay, render_post_card
from reddit_shorts.scraper import RedditPost, mark_post_done, scrape_posts
from reddit_shorts.safety import evaluate_post
from reddit_shorts.script_writer import generate_script
from reddit_shorts.subtitle_gen import SubtitleSpec, generate_ass
from reddit_shorts.transcription import transcribe_word_timestamps


def _post_output_dir(post_id: str) -> Path:
    return cfg.OUTPUT_DIR / post_id


def _append_safety_skip_log(post: RedditPost, matched_terms: list[str]) -> None:
    """Append a structured log entry for safety-filtered posts."""
    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = cfg.OUTPUT_DIR / "skipped_safety.jsonl"
    row = {
        "post_id": post.post_id,
        "subreddit": post.subreddit,
        "title": post.title,
        "url": post.url,
        "matched_terms": matched_terms,
        "timestamp": datetime.now().isoformat(),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def process_post(
    post: RedditPost,
    gameplay_clips: Optional[list[Path]] = None,
    skip_if_exists: bool = True,
    safety_filter: bool = True,
    blocked_terms: Optional[list[str]] = None,
) -> Optional[Path]:
    """
    Run the full pipeline for a single post.

    Returns the path to the final MP4, or None if skipped/failed.
    """
    out_dir = _post_output_dir(post.post_id)
    final_video = out_dir / "video.mp4"

    if skip_if_exists and final_video.exists():
        print(f"[pipeline] Skipping {post.post_id} — video already exists")
        return final_video

    if safety_filter:
        terms = blocked_terms if blocked_terms is not None else cfg.SAFETY_BLOCKED_TERMS
        decision = evaluate_post(post, terms)
        if decision.blocked:
            print(
                f"[pipeline] Skipping {post.post_id} — safety filter matched: "
                + ", ".join(decision.matched_terms)
            )
            _append_safety_skip_log(post, decision.matched_terms)
            return None

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"[pipeline] Processing post: {post.post_id}")
    print(f"[pipeline] Title: {post.title[:80]}")
    print(f"[pipeline] Score: {post.upvotes:,}  Flair: {post.flair}")
    print(f"{'='*60}\n")

    # Save post metadata for reference
    meta_path = out_dir / "post_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "post_id": post.post_id,
                "title": post.title,
                "author": post.author,
                "upvotes": post.upvotes,
                "num_comments": post.num_comments,
                "flair": post.flair,
                "url": post.url,
                "subreddit": post.subreddit,
                "processed_at": datetime.now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # ── Step 1: Generate narration script ───────────────────────────────────
    print("[pipeline] Step 1/6 — Writing narration script…")
    script = generate_script(post)
    script_path = out_dir / "script.txt"
    script_path.write_text(script.full_text, encoding="utf-8")
    print(f"[pipeline] Script: {len(script.full_text)} chars")

    # ── Step 2: Generate ASMR audio ─────────────────────────────────────────
    print("[pipeline] Step 2/6 — Generating ASMR audio…")
    # Lazy import keeps CLI dry-runs fast and avoids heavyweight model imports
    # unless we actually render audio/video.
    from reddit_shorts.tts_narrator import generate_narration, get_audio_duration

    audio_wav = out_dir / "audio.wav"
    generate_narration(
        text=script.full_text,
        output_wav=audio_wav,
        voice_profile=cfg.VOICE_PROFILE,
    )
    audio_duration = get_audio_duration(audio_wav)
    print(f"[pipeline] Audio duration: {audio_duration:.1f}s")

    # Guard: Shorts / TikTok sweet spot is 60–180 s
    if audio_duration < 40:
        print(f"[pipeline] WARNING: Audio is very short ({audio_duration:.0f}s). Post may be too brief.")
    if audio_duration > 240:
        print(f"[pipeline] WARNING: Audio is long ({audio_duration:.0f}s). Consider a shorter post body.")

    # ── Step 3: Render Reddit post card ─────────────────────────────────────
    print("[pipeline] Step 3/6 — Rendering Reddit card…")
    card_png = out_dir / "reddit_card.png"
    card_height = render_post_card(post, card_png)

    hook_overlay_png = out_dir / "hook_overlay.png"
    render_hook_overlay(script.hook, hook_overlay_png)

    # ── Step 4: Generate subtitles ───────────────────────────────────────────
    print("[pipeline] Step 4/6 — Generating subtitles…")
    subtitle_ass = out_dir / "subtitles.ass"
    subtitle_body_text = script.body + ("\n\n" + script.comment_section if script.comment_section else "") + "\n\n" + script.cta
    timed_words = transcribe_word_timestamps(audio_wav, expected_text=subtitle_body_text)
    spec = SubtitleSpec(
        hook_text=script.hook,
        body_text=subtitle_body_text,
        audio_duration_s=audio_duration,
        timed_words=timed_words,
    )
    generate_ass(spec, subtitle_ass)

    # ── Step 5: Compose video ────────────────────────────────────────────────
    print("[pipeline] Step 5/6 — Composing video…")
    from reddit_shorts.video_composer import compose_video

    if gameplay_clips is None:
        gameplay_clips = ensure_gameplay_footage()

    compose_video(
        audio_path=audio_wav,
        card_png=card_png,
        subtitle_ass=subtitle_ass,
        output_path=final_video,
        card_height_px=card_height,
        hook_text=script.hook,
        gameplay_clips=gameplay_clips,
    )

    # ── Step 6: Mark done ────────────────────────────────────────────────────
    print("[pipeline] Step 6/6 — Marking post as done…")
    mark_post_done(post.post_id)

    print(f"\n[pipeline] ✓ Video ready: {final_video}\n")
    return final_video


def run_batch(
    max_videos: int = 5,
    subreddit: str = cfg.SUBREDDIT,
    sort: str = "hot",
    top_time: str = "week",
    min_upvotes: int = cfg.MIN_UPVOTES,
    min_body_chars: int = cfg.MIN_BODY_CHARS,
    max_body_chars: int = cfg.MAX_BODY_CHARS,
    auto_download_gameplay: bool = True,
    dry_run: bool = False,
    safety_filter: bool = True,
    blocked_terms: Optional[list[str]] = None,
) -> list[Path]:
    """
    Scrape, filter, and process multiple posts.

    Parameters
    ----------
    max_videos              : Maximum number of videos to produce in this run
    subreddit               : Subreddit to scrape
    sort                    : "hot" | "top" | "new"
    top_time                : Time filter for top sorting (day/week/month/year/all)
    min_upvotes             : Minimum upvotes required
    min_body_chars          : Minimum post body length
    max_body_chars          : Maximum post body length
    auto_download_gameplay  : Download Minecraft footage if none found locally
    dry_run                 : If True, only print what would be done (no TTS/video)
    safety_filter           : If True, skip posts matching blocked terms
    blocked_terms           : Optional override/extension for blocked keywords
    """
    print(
        f"[pipeline] Starting batch run (max {max_videos} videos, "
        f"r/{subreddit}, sort={sort}, top_time={top_time})"
    )

    # Pre-load gameplay clips once for the whole batch
    gameplay_clips = None
    if not dry_run:
        gameplay_clips = ensure_gameplay_footage(auto_download=auto_download_gameplay)

    # Scrape posts
    posts = scrape_posts(
        subreddit_name=subreddit,
        sort=sort,
        top_time=top_time,
        min_upvotes=min_upvotes,
        min_body_chars=min_body_chars,
        max_body_chars=max_body_chars,
    )
    if not posts:
        print("[pipeline] No posts passed the filters. Try changing sort/subreddit/min_upvotes.")
        return []

    print(f"[pipeline] {len(posts)} post(s) ready to process")

    terms = blocked_terms if blocked_terms is not None else cfg.SAFETY_BLOCKED_TERMS

    produced: list[Path] = []
    errors: list[str] = []
    skipped_safety = 0

    for post in posts[:max_videos]:
        if safety_filter:
            decision = evaluate_post(post, terms)
            if decision.blocked:
                skipped_safety += 1
                print(
                    f"[pipeline] Skipping {post.post_id} — safety filter matched: "
                    + ", ".join(decision.matched_terms)
                )
                _append_safety_skip_log(post, decision.matched_terms)
                continue

        if dry_run:
            print(f"[DRY RUN] Would process: [{post.flair}] {post.title[:80]} ({post.upvotes:,} ▲)")
            continue
        try:
            video_path = process_post(
                post,
                gameplay_clips=gameplay_clips,
                safety_filter=False,
                blocked_terms=terms,
            )
            if video_path:
                produced.append(video_path)
        except Exception as exc:
            msg = f"Post {post.post_id} failed: {exc}"
            print(f"[pipeline] ERROR: {msg}")
            traceback.print_exc()
            errors.append(msg)
            # Write error log so we can review
            err_path = _post_output_dir(post.post_id) / "error.log"
            err_path.parent.mkdir(parents=True, exist_ok=True)
            err_path.write_text(traceback.format_exc(), encoding="utf-8")

    print(
        f"\n[pipeline] Batch complete: {len(produced)} video(s) produced, "
        f"{len(errors)} error(s), {skipped_safety} safety-skip(s)"
    )
    for p in produced:
        print(f"  → {p}")
    return produced
