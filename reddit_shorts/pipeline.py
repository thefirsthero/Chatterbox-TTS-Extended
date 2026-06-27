"""
reddit_shorts/pipeline.py — orchestrate the full Reddit → TikTok/Shorts pipeline.

Run via:
    python run_shorts_pipeline.py [options]

Or import and call process_post() from your own script.
"""

import json
import os
import shutil
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
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
from reddit_shorts.scraper import RedditPost, is_post_done, mark_post_done, scrape_posts
from reddit_shorts.safety import evaluate_post
from reddit_shorts.script_writer import generate_script
from reddit_shorts.subtitle_gen import SubtitleSpec, generate_ass
from reddit_shorts.transcription import transcribe_word_timestamps


def _post_output_dir(post_id: str, subreddit: str = "") -> Path:
    """Return the per-post output directory, scoped under the subreddit folder."""
    if subreddit:
        sub_dir = subreddit.lower().replace(" ", "_")
        return cfg.OUTPUT_DIR / sub_dir / post_id
    return cfg.OUTPUT_DIR / post_id


def _process_post_worker(args_tuple: tuple) -> list[Path]:
    """
    Worker function for ProcessPoolExecutor parallel processing.
    
    Takes a tuple of (post, gameplay_clips_list, blocked_terms) and processes
    the post independently in a subprocess.
    """
    post, gameplay_clips_list, blocked_terms = args_tuple
    try:
        return process_post(
            post,
            gameplay_clips=gameplay_clips_list,
            safety_filter=False,
            blocked_terms=blocked_terms,
        )
    except Exception as exc:
        print(f"[parallel] Error processing {post.post_id}: {exc}")
        traceback.print_exc()
        return []


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


def _publish_final_video(post_id: str, source_video: Path, subreddit: str = "", part: Optional[int] = None) -> Path:
    """Copy the per-post render into the canonical videos destination, organized by subreddit and date."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    if subreddit:
        safe_sub = subreddit.lower().replace(" ", "_")
        dest_dir = cfg.FINAL_VIDEOS_DIR / safe_sub / date_str
    else:
        dest_dir = cfg.FINAL_VIDEOS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    meta_path = _post_output_dir(post_id, subreddit) / "post_meta.json"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    resolved_subreddit = subreddit or "subreddit"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            processed_at = meta.get("processed_at")
            if processed_at:
                timestamp = datetime.fromisoformat(processed_at).strftime("%Y%m%d_%H%M%S")
            resolved_subreddit = str(meta.get("subreddit") or resolved_subreddit)
        except Exception:
            pass
    safe_subreddit = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in resolved_subreddit).strip("-") or "subreddit"
    if part is not None:
        published_path = dest_dir / f"{timestamp}__{safe_subreddit}__{post_id}__part{part}.mp4"
    else:
        published_path = dest_dir / f"{timestamp}__{safe_subreddit}__{post_id}.mp4"
    shutil.copy2(source_video, published_path)
    return published_path


def process_post(
    post: RedditPost,
    gameplay_clips: Optional[list[Path]] = None,
    skip_if_exists: bool = True,
    safety_filter: bool = True,
    blocked_terms: Optional[list[str]] = None,
) -> list[Path]:
    """
    Run the full pipeline for a single post.

    Returns a list of published MP4 paths (normally 1; may be 2 when a long
    post is split into Part 1 / Part 2).  Empty list = skipped or failed.
    """
    out_dir = _post_output_dir(post.post_id, post.subreddit)
    final_video = out_dir / "video.mp4"

    if is_post_done(post.post_id):
        if final_video.exists():
            published_video = _publish_final_video(post.post_id, final_video, post.subreddit)
            print(f"[pipeline] Skipping {post.post_id} — already processed")
            print(f"[pipeline] Published: {published_video}")
            return [published_video]
        print(f"[pipeline] Skipping {post.post_id} — already processed (done list)")
        return []

    if skip_if_exists and final_video.exists():
        published_video = _publish_final_video(post.post_id, final_video, post.subreddit)
        print(f"[pipeline] Skipping {post.post_id} — video already exists")
        print(f"[pipeline] Published: {published_video}")
        return [published_video]

    if safety_filter:
        terms = blocked_terms if blocked_terms is not None else cfg.SAFETY_BLOCKED_TERMS
        decision = evaluate_post(post, terms)
        if decision.blocked:
            print(
                f"[pipeline] Skipping {post.post_id} — safety filter matched: "
                + ", ".join(decision.matched_terms)
            )
            _append_safety_skip_log(post, decision.matched_terms)
            return []

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

    # ── Step 1b: Validate estimated duration / split if needed ───────────────
    from reddit_shorts.tts_narrator import estimate_narration_duration
    from reddit_shorts.script_writer import generate_split_scripts

    estimated_duration = estimate_narration_duration(script.full_text)
    print(f"[pipeline] Estimated duration: {estimated_duration:.1f}s")

    max_dur = cfg.MAX_VIDEO_DURATION_S

    # Decide: single video or split into parts
    if estimated_duration > max_dur and cfg.ENABLE_VIDEO_SPLITTING:
        print(
            f"[pipeline] Duration {estimated_duration:.0f}s > {max_dur}s limit — "
            f"splitting into Part 1 / Part 2"
        )
        scripts = generate_split_scripts(post, max_dur)
        print(
            f"[pipeline] Split into {len(scripts)} part(s): "
            f"{', '.join(str(len(s.full_text)) + ' chars' for s in scripts)}"
        )
    else:
        if estimated_duration > max_dur:
            print(
                f"[pipeline] SKIPPING {post.post_id} — estimated duration "
                f"{estimated_duration:.0f}s exceeds maximum {max_dur}s "
                f"(splitting disabled)"
            )
            return []
        scripts = [script]

    # ── Render each part ────────────────────────────────────────────────────
    results: list[Path] = []
    total_parts = len(scripts)
    for i, part_script in enumerate(scripts, 1):
        if total_parts > 1:
            print(f"\n{'─' * 40}")
            print(f"[pipeline] Rendering Part {i} of {total_parts}")
            print(f"{'─' * 40}")
            # Save part-specific script
            part_suffix = f"_part{i}"
            (out_dir / f"script{part_suffix}.txt").write_text(
                part_script.full_text, encoding="utf-8"
            )
            print(f"[pipeline] Part {i} script: {len(part_script.full_text)} chars")

        video = _render_video_from_script(
            post, part_script, out_dir, gameplay_clips,
            part_num=i if total_parts > 1 else None,
        )
        if video:
            results.append(video)

    # ── Step 6: Mark done (once for all parts) ──────────────────────────────
    if results:
        print("[pipeline] Step 6/6 — Marking post as done…")
        mark_post_done(post.post_id)
        # Clean up local post JSON
        for check_dir in [
            cfg.OUTPUT_DIR.parent / "cache" / "local_posts",
            cfg.OUTPUT_DIR.parent / "cache" / "local_posts" / post.subreddit.lower().replace(" ", "_"),
        ]:
            local_post_path = check_dir / f"{post.post_id}.json"
            if local_post_path.exists():
                local_post_path.unlink()
                print(f"[pipeline] Deleted local post file: {local_post_path}")

    return results

def _render_video_from_script(
    post: RedditPost,
    script,
    out_dir: Path,
    gameplay_clips,
    part_num: Optional[int] = None,
) -> Optional[Path]:
    """Execute Steps 2–6 for a single script (may be a part of a split post).

    Returns the published video path, or None on failure.
    """
    from reddit_shorts.tts_narrator import (
        generate_narration,
        get_audio_duration,
    )
    from reddit_shorts.video_composer import compose_video

    # ── Step 2: Audio ──────────────────────────────────────────────────
    print("[pipeline] Step 2/6 — Generating narration audio…")
    suffix = f"_part{part_num}" if part_num else ""
    audio_wav = out_dir / f"audio{suffix}.wav"
    generate_narration(
        text=script.full_text,
        output_wav=audio_wav,
        voice_profile=cfg.VOICE_PROFILE,
    )
    audio_duration = get_audio_duration(audio_wav)
    print(f"[pipeline] Audio duration: {audio_duration:.1f}s")

    if audio_duration < 40:
        print(f"[pipeline] WARNING: Audio is very short ({audio_duration:.0f}s).")

    # ── Step 3: Card ───────────────────────────────────────────────────
    print("[pipeline] Step 3/6 — Rendering Reddit card…")
    card_png = out_dir / f"reddit_card{suffix}.png"
    card_height = render_post_card(post, card_png)

    hook_overlay_png = out_dir / f"hook_overlay{suffix}.png"
    render_hook_overlay(script.hook, hook_overlay_png)

    # ── Step 4: Subtitles ──────────────────────────────────────────────
    print("[pipeline] Step 4/6 — Generating subtitles…")
    subtitle_ass = out_dir / f"subtitles{suffix}.ass"
    timed_words = transcribe_word_timestamps(audio_wav)
    spec = SubtitleSpec(
        hook_text=script.hook,
        body_text=script.full_text,
        audio_duration_s=audio_duration,
        timed_words=timed_words,
    )
    generate_ass(spec, subtitle_ass)

    # ── Step 5: Compose ────────────────────────────────────────────────
    print("[pipeline] Step 5/6 — Composing video…")
    final_video = out_dir / f"video{suffix}.mp4"

    compose_video(
        audio_path=audio_wav,
        card_png=card_png,
        subtitle_ass=subtitle_ass,
        output_path=final_video,
        card_height_px=card_height,
        hook_text=script.hook,
        gameplay_clips=gameplay_clips,
        subreddit=post.subreddit,
    )

    published_video = _publish_final_video(
        post.post_id, final_video, post.subreddit, part=part_num
    )

    print(f"\n[pipeline] ✓ Video ready: {final_video}")
    print(f"[pipeline] ✓ Published to: {published_video}\n")
    return published_video


def run_batch(
    max_videos: int = 5,
    subreddit: str = cfg.SUBREDDIT,
    sort: str = "hot",
    top_time: str = "week",
    min_upvotes: int = cfg.MIN_UPVOTES,
    min_body_chars: int = cfg.MIN_BODY_CHARS,
    max_body_chars: int = cfg.MAX_BODY_CHARS,
    auto_download_gameplay: bool = True,
    gameplay_clips: Optional[list[str]] = None,
    posts: Optional[list[RedditPost]] = None,
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
    gameplay_clips          : Optional pre-loaded gameplay clips (skips internal loading if provided)
    posts                   : Optional pre-loaded posts (skips scraping if provided)
    dry_run                 : If True, only print what would be done (no TTS/video)
    safety_filter           : If True, skip posts matching blocked terms
    blocked_terms           : Optional override/extension for blocked keywords
    """
    print(
        f"[pipeline] Starting batch run (max {max_videos} videos, "
        f"r/{subreddit}, sort={sort}, top_time={top_time})"
    )

    # Pre-load gameplay clips once for the whole batch
    if gameplay_clips is None and not dry_run:
        gameplay_clips = ensure_gameplay_footage(auto_download=auto_download_gameplay)

    # Use provided posts or scrape fresh ones
    if posts is not None:
        print(f"[pipeline] Using {len(posts)} pre-loaded post(s)")
    else:
        posts = scrape_posts(
            subreddit_name=subreddit,
            sort=sort,
            top_time=top_time,
            min_upvotes=min_upvotes,
            min_body_chars=min_body_chars,
            max_body_chars=max_body_chars,
            desired_count=max_videos,
            flair_whitelist=cfg.get_flair_whitelist(subreddit),
        )
        if not posts:
            print("[pipeline] No posts passed the filters. Try changing sort/subreddit/min_upvotes.")
            return []

        print(f"[pipeline] {len(posts)} post(s) ready to process")

    terms = blocked_terms if blocked_terms is not None else cfg.SAFETY_BLOCKED_TERMS

    produced: list[Path] = []
    errors: list[str] = []
    skipped_safety = 0

    # Pre-filter posts for safety before parallel processing
    posts_to_process = []
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
        posts_to_process.append(post)

    if dry_run:
        for post in posts_to_process:
            print(f"[DRY RUN] Would process: [{post.flair}] {post.title[:80]} ({post.upvotes:,} upvotes)")
        print(
            f"\n[pipeline] Dry run complete: {len(posts_to_process)} video(s) would be produced"
        )
        return []

    # Decide whether to use parallel processing
    use_parallel = len(posts_to_process) > 2
    
    if use_parallel:
        # Parallel processing for multiple posts
        from multiprocessing import cpu_count
        max_workers = cfg.MAX_PARALLEL_POSTS
        if max_workers is None:
            max_workers = max(1, cpu_count() // 3)
        max_workers = min(max_workers, len(posts_to_process))
        
        print(f"[pipeline] Processing {len(posts_to_process)} post(s) with {max_workers} parallel worker(s)")
        
        # Prepare work items
        work_items = [
            (post, gameplay_clips, terms)
            for post in posts_to_process
        ]
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_process_post_worker, item): item[0]
                for item in work_items
            }
            
            completed = 0
            for future in as_completed(futures):
                post = futures[future]
                try:
                    video_paths = future.result()
                    completed += 1
                    if video_paths:
                        produced.extend(video_paths)
                        print(f"[pipeline] [{completed}/{len(posts_to_process)}] ✓ {post.post_id}")
                    else:
                        print(f"[pipeline] [{completed}/{len(posts_to_process)}] ⊘ {post.post_id} (skipped)")
                except Exception as exc:
                    completed += 1
                    msg = f"Post {post.post_id} failed: {exc}"
                    print(f"[pipeline] [{completed}/{len(posts_to_process)}] ✗ {post.post_id}")
                    print(f"[pipeline]   Error: {exc}")
                    errors.append(msg)
                    err_path = _post_output_dir(post.post_id, post.subreddit) / "error.log"
                    err_path.parent.mkdir(parents=True, exist_ok=True)
                    err_path.write_text(traceback.format_exc(), encoding="utf-8")
    else:
        # Serial processing for small batches (≤2 posts)
        print(f"[pipeline] Processing {len(posts_to_process)} post(s) serially")
        
        for idx, post in enumerate(posts_to_process, 1):
            try:
                video_paths = process_post(
                    post,
                    gameplay_clips=gameplay_clips,
                    safety_filter=False,
                    blocked_terms=terms,
                )
                if video_paths:
                    produced.extend(video_paths)
            except Exception as exc:
                msg = f"Post {post.post_id} failed: {exc}"
                print(f"[pipeline] ERROR: {msg}")
                traceback.print_exc()
                errors.append(msg)
                err_path = _post_output_dir(post.post_id, post.subreddit) / "error.log"
                err_path.parent.mkdir(parents=True, exist_ok=True)
                err_path.write_text(traceback.format_exc(), encoding="utf-8")

    print(
        f"\n[pipeline] Batch complete: {len(produced)} video(s) produced, "
        f"{len(errors)} error(s), {skipped_safety} safety-skip(s)"
    )
    for p in produced:
        print(f"  -> {p}")
    return produced


def run_multi_subreddit_batch(
    subreddits: list[str] | None = None,
    max_videos_per: int = 3,
    sort: str = "hot",
    top_time: str = "week",
    auto_download_gameplay: bool = True,
    dry_run: bool = False,
    safety_filter: bool = True,
    blocked_terms: list[str] | None = None,
) -> dict[str, list[Path]]:
    """
    Run the pipeline across multiple subreddits in sequence.

    Parameters
    ----------
    subreddits           : List of subreddit names. If None, uses cfg.ENABLED_SUBREDDITS.
    max_videos_per       : Maximum videos per subreddit.
    sort                 : Reddit listing sort order.
    top_time             : Time filter for top sorting.
    auto_download_gameplay: Download gameplay footage if none found.
    dry_run              : If True, print what would be done without generating.
    safety_filter        : If True, skip posts matching blocked terms.
    blocked_terms        : Optional override for blocked keywords.

    Returns
    -------
    dict[str, list[Path]]
        Mapping of subreddit → list of produced video paths.
    """
    if subreddits is None:
        subreddits = cfg.ENABLED_SUBREDDITS

    if not subreddits:
        print("[pipeline] No subreddits configured. Check SUBREDDIT_CONFIGS in config.py.")
        return {}

    print(f"[pipeline] Multi-subreddit batch: {len(subreddits)} subreddit(s)")
    for sub in subreddits:
        cat = cfg.get_subreddit_category(sub)
        print(f"  • r/{sub}  ({cat})")

    # Pre-load gameplay clips once for all subreddits
    gameplay_clips = None
    if not dry_run:
        gameplay_clips = ensure_gameplay_footage(auto_download=auto_download_gameplay)

    all_results: dict[str, list[Path]] = {}
    total_produced = 0

    for sub in subreddits:
        cfg_entry = cfg.get_subreddit_config(sub)
        if not cfg_entry.get("enabled", True):
            print(f"\n[pipeline] Skipping r/{sub} — disabled in config")
            continue

        print(f"\n{'=' * 60}")
        print(f"[pipeline] Processing r/{sub}")
        print(f"{'=' * 60}")

        try:
            results = run_batch(
                max_videos=max_videos_per,
                subreddit=sub,
                sort=sort,
                top_time=top_time,
                min_upvotes=cfg.get_min_upvotes(sub),
                min_body_chars=cfg.MIN_BODY_CHARS,
                max_body_chars=cfg.MAX_BODY_CHARS,
                auto_download_gameplay=False,  # already loaded
                gameplay_clips=gameplay_clips,
                dry_run=dry_run,
                safety_filter=safety_filter,
                blocked_terms=blocked_terms,
            )
            all_results[sub] = results
            total_produced += len(results)
        except Exception as exc:
            print(f"[pipeline] Error processing r/{sub}: {exc}")
            traceback.print_exc()
            all_results[sub] = []

    print(f"\n[pipeline] Multi-subreddit batch complete: {total_produced} total video(s)")
    for sub, videos in all_results.items():
        print(f"  r/{sub}: {len(videos)} video(s)")
    return all_results
