"""
bible_shorts/pipeline.py — orchestrate the full Bible Scripture → Shorts pipeline.

Reuses shared rendering components from reddit_shorts where appropriate:
  • reddit_shorts.tts_narrator — ChatterboxTTS narration generation
  • reddit_shorts.transcription — Whisper word timestamp transcription
  • reddit_shorts.video_composer — FFmpeg video assembly (adapted)
  • reddit_shorts.scraper — RedditPost dataclass (not used; we have BibleVerse)

Bible-specific logic lives entirely within bible_shorts/:
  • content.py — verse database + selection
  • script_writer.py — Hook → Verse → Reflection → CTA scripts
  • bible_renderer.py — premium Scripture card rendering
  • background.py — cinematic footage management
  • subtitle_styler.py — Bible-optimized ASS subtitles
  • audio_mixer.py — voice + music + ambience mixing

Run via:
    python run_bible_shorts.py [options]
"""

import json
import shutil
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from bible_shorts import config as cfg
from bible_shorts.content import BibleVerse, get_provider
from bible_shorts.script_writer import BibleScript, generate_script


def _verse_output_dir(verse_ref: str) -> Path:
    """Return the per-verse output directory (sanitized reference)."""
    safe = verse_ref.lower().replace(" ", "_").replace(":", "-")
    return cfg.OUTPUT_DIR / safe


def _load_done_verses() -> set[str]:
    """Load set of already-processed verse references."""
    path = cfg.DONE_VERSES_FILE
    if not path.exists():
        return set()
    return {
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _mark_verse_done(verse_ref: str) -> None:
    """Append a verse reference to the done list."""
    cfg.DONE_VERSES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with cfg.DONE_VERSES_FILE.open("a", encoding="utf-8") as f:
        f.write(verse_ref.lower() + "\n")


def is_verse_done(verse_ref: str) -> bool:
    """Check if a verse has already been processed."""
    return verse_ref.lower() in _load_done_verses()


def _publish_final_video(verse_ref: str, source_video: Path, category: str = "") -> Path:
    """Copy the rendered video to the canonical destination, organized by date."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_cat = category.lower().replace(" ", "_") if category else "general"
    dest_dir = cfg.FINAL_VIDEOS_DIR / safe_cat / date_str
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in verse_ref).strip("-")
    published_path = dest_dir / f"{timestamp}__{safe_cat}__{safe_ref}.mp4"

    shutil.copy2(source_video, published_path)
    return published_path


def process_verse(
    verse: BibleVerse,
    background_clips: Optional[list[Path]] = None,
    skip_if_exists: bool = True,
    skip_if_done: bool = True,
) -> Optional[Path]:
    """Run the full Bible Shorts pipeline for a single verse.

    Steps:
      1. Generate narration script (Hook → Verse → Reflection → CTA)
      2. Generate narration audio via ChatterboxTTS
      3. Render premium Scripture card PNG
      4. Render hook overlay PNG
      5. Transcribe word timestamps (Whisper)
      6. Generate Bible-styled ASS subtitles
      7. Ensure cinematic background footage
      8. Mix voice + music + ambience
      9. Compose final video via FFmpeg
     10. Publish to destination directory
     11. Mark verse as done

    Returns the published video path, or None if skipped/failed.
    """
    verse_ref = verse.reference

    # ── Check if already processed ──────────────────────────────────────
    out_dir = _verse_output_dir(verse_ref)
    final_video = out_dir / "video.mp4"

    if skip_if_done and is_verse_done(verse_ref):
        if final_video.exists():
            published = _publish_final_video(verse_ref, final_video, verse.category)
            print(f"[bible] Skipping {verse_ref} — already processed")
            print(f"[bible] Published: {published}")
            return published
        print(f"[bible] Skipping {verse_ref} — already in done list")
        return None

    if skip_if_exists and final_video.exists():
        published = _publish_final_video(verse_ref, final_video, verse.category)
        print(f"[bible] Skipping {verse_ref} — video already exists")
        print(f"[bible] Published: {published}")
        return published

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"[bible] Processing: {verse_ref}")
    print(f"[bible] Category: {verse.category}  |  Tags: {', '.join(verse.tags)}")
    print(f"[bible] Text: {verse.text[:100]}…")
    print(f"{'=' * 60}\n")

    # Save verse metadata
    meta_path = out_dir / "verse_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "reference": verse.reference,
                "book": verse.book,
                "chapter": verse.chapter,
                "verse_num": verse.verse,
                "text": verse.text,
                "translation": verse.translation,
                "category": verse.category,
                "tags": verse.tags,
                "processed_at": datetime.now().isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # ── Step 1: Generate script ─────────────────────────────────────────
    print("[bible] Step 1/9 — Writing narration script…")
    script = generate_script(verse)
    script_path = out_dir / "script.txt"
    script_path.write_text(script.full_text, encoding="utf-8")
    print(f"[bible] Script: {len(script.full_text)} chars")
    print(f"[bible]   Hook: \"{script.hook}\"")
    print(f"[bible]   Verse: \"{script.verse_text[:60]}…\"")

    # ── Step 2: Generate narration audio ────────────────────────────────
    print("[bible] Step 2/9 — Generating narration audio…")
    from reddit_shorts.tts_narrator import (
        generate_narration,
        get_audio_duration,
    )

    audio_wav = out_dir / "audio.wav"
    generate_narration(
        text=script.full_text,
        output_wav=audio_wav,
        voice_profile=cfg.BIBLE_VOICE_PROFILE,
    )
    audio_duration = get_audio_duration(audio_wav)
    print(f"[bible] Audio duration: {audio_duration:.1f}s")

    if audio_duration < cfg.MIN_VIDEO_DURATION_S:
        print(
            f"[bible] WARNING: Audio is very short ({audio_duration:.0f}s). "
            f"Below minimum {cfg.MIN_VIDEO_DURATION_S}s."
        )
    if audio_duration > cfg.MAX_VIDEO_DURATION_S:
        print(
            f"[bible] WARNING: Audio is long ({audio_duration:.0f}s). "
            f"Max recommended is {cfg.MAX_VIDEO_DURATION_S}s."
        )

    # ── Step 3: Render Scripture card ───────────────────────────────────
    print("[bible] Step 3/9 — Rendering premium Scripture card…")
    from bible_shorts.bible_renderer import render_scripture_card, render_hook_overlay

    card_png = out_dir / "scripture_card.png"
    card_height = render_scripture_card(
        verse=verse,
        output_path=card_png,
        reflection=script.reflection,
    )
    print(f"[bible] Card: {card_height}px tall")

    hook_overlay_png = out_dir / "hook_overlay.png"
    render_hook_overlay(script.hook, hook_overlay_png)
    print(f"[bible] Hook overlay rendered")

    # ── Step 4: Generate subtitles ──────────────────────────────────────
    print("[bible] Step 4/9 — Generating Bible-styled subtitles…")
    from reddit_shorts.transcription import transcribe_word_timestamps
    from bible_shorts.subtitle_styler import generate_bible_ass_from_timed_words

    subtitle_ass = out_dir / "subtitles.ass"

    try:
        timed_words = transcribe_word_timestamps(audio_wav)
        if timed_words:
            generate_bible_ass_from_timed_words(
                timed_words,
                subtitle_ass,
                script.full_text,
            )
            print(f"[bible] Subtitles: {len(timed_words)} timed words from Whisper")
        else:
            # Fallback to text-based timing
            from bible_shorts.subtitle_styler import generate_bible_ass
            generate_bible_ass(
                script.full_text,
                audio_duration,
                subtitle_ass,
                hook_text=script.hook,
            )
            print("[bible] Subtitles: fallback text-based timing (no Whisper data)")
    except Exception as exc:
        print(f"[bible] WARNING: Whisper transcription failed ({exc}). Using text-based timing.")
        from bible_shorts.subtitle_styler import generate_bible_ass
        generate_bible_ass(
            script.full_text,
            audio_duration,
            subtitle_ass,
            hook_text=script.hook,
        )

    # ── Step 5: Background footage ──────────────────────────────────────
    print("[bible] Step 5/9 — Preparing cinematic background…")
    from bible_shorts.background import ensure_cinematic_footage

    if background_clips is None:
        background_clips = ensure_cinematic_footage(min_clips=6)
        if not background_clips:
            print("[bible] WARNING: No background clips available. Video will have solid background.")
    else:
        print(f"[bible] Using {len(background_clips)} provided background clip(s)")

    # ── Step 6: Mix audio ───────────────────────────────────────────────
    print("[bible] Step 6/9 — Mixing voice + music + ambience…")
    from bible_shorts.audio_mixer import mix_audio

    mixed_audio_wav = out_dir / "audio_mixed.wav"
    try:
        mix_audio(
            voice_wav=audio_wav,
            output_path=mixed_audio_wav,
        )
        # Use mixed audio for final composition
        final_audio = mixed_audio_wav
    except Exception as exc:
        print(f"[bible] NOTE: Audio mixing skipped ({exc}). Using raw narration.")
        final_audio = audio_wav

    # ── Step 7: Compose final video ─────────────────────────────────────
    print("[bible] Step 7/9 — Composing final video…")
    video_output = _compose_bible_video(
        audio_path=final_audio,
        card_png=card_png,
        subtitle_ass=subtitle_ass,
        output_path=final_video,
        card_height_px=card_height,
        hook_text=script.hook,
        background_clips=background_clips,
        verse=verse,
    )

    # ── Step 8: Render closing screen and append ────────────────────────
    print("[bible] Step 8/9 — Rendering closing screen…")
    from bible_shorts.bible_renderer import render_closing_screen
    from bible_shorts.content import get_outro

    outro_text = get_outro()
    outro_png = out_dir / "closing_screen.png"
    render_closing_screen(outro_text, outro_png)

    video_with_outro = _append_outro(video_output, outro_png, outro_text)

    # ── Step 9: Publish and mark done ───────────────────────────────────
    print("[bible] Step 9/9 — Publishing…")
    published = _publish_final_video(verse_ref, video_with_outro, verse.category)
    _mark_verse_done(verse_ref)

    size_mb = published.stat().st_size / 1_048_576
    print(f"\n[bible] ✅ Done! {published}")
    print(f"[bible]    Duration: {audio_duration:.0f}s  |  Size: {size_mb:.1f} MB")
    print(f"[bible]    Verse: {verse_ref}  |  Category: {verse.category}")

    return published


def _compose_bible_video(
    audio_path: Path,
    card_png: Path,
    subtitle_ass: Path,
    output_path: Path,
    card_height_px: int,
    hook_text: str = "",
    background_clips: Optional[list[Path]] = None,
    verse: Optional[BibleVerse] = None,
) -> Path:
    """Compose the final Bible Shorts video via FFmpeg.

    Video layout (1080×1920 portrait):
      ┌─────────────────────┐  ← y=0
      │  Branding strip     │  ← ~48px  (drawtext)
      │  ┌───────────────┐  │
      │  │ Scripture     │  │  ← card viewport y=200–1580 (scrolling crop)
      │  │   Card        │  │
      │  └───────────────┘  │
      │  Subtitle band      │  ← y=1620–1870  (ASS subtitles filter)
      │  ══ progress bar ══ │  ← y=1895–1903  (drawbox, gold)
      └─────────────────────┘  ← y=1920

    Cinematic background fills the entire frame (scaled-to-fill + gentle blur).
    """
    import os
    import subprocess
    import tempfile

    from reddit_shorts.video_composer import (
        _ffprobe_duration,
        _ffprobe_dimensions,
        _write_concat_list,
    )

    W = cfg.VIDEO_WIDTH
    H = cfg.VIDEO_HEIGHT
    audio_duration = _ffprobe_duration(audio_path)

    with tempfile.TemporaryDirectory(prefix="bible_compose_") as tmp_dir:
        # ── Build background video ──────────────────────────────────────
        if background_clips:
            from bible_shorts.background import build_looped_sequence

            bg_video = build_looped_sequence(
                background_clips,
                audio_duration + cfg.CLOSING_SCREEN_DURATION_S + 3,
                tmp_dir,
            )
        else:
            # Fallback: solid warm dark background
            bg_video = str(Path(tmp_dir) / "solid_bg.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi",
                    "-i", f"color=c=0x1A1A2E:s={W}x{H}:d={audio_duration + 5}:r={cfg.VIDEO_FPS}",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "18",
                    bg_video,
                ],
                check=True,
                capture_output=True,
            )

        # ── Card geometry ───────────────────────────────────────────────
        card_w = cfg.CARD_WIDTH
        card_x = cfg.CARD_X
        viewport_top = cfg.CARD_VIEWPORT_TOP
        viewport_h = cfg.CARD_VIEWPORT_H

        blur = cfg.BACKGROUND_BLUR_RADIUS
        darken = cfg.BACKGROUND_DARKEN

        # Scroll calculation
        scroll_start = cfg.CARD_SCROLL_START_S
        scroll_end_margin = cfg.CARD_SCROLL_END_MARGIN_S
        scroll_duration = max(0.1, audio_duration - scroll_start - scroll_end_margin)
        scroll_distance = max(0, card_height_px - viewport_h)

        # ── Build FFmpeg filter graph ───────────────────────────────────
        # Background processing
        bg_filter = (
            f"[0:v]"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},"
            f"setsar=1,"
            f"boxblur=luma_radius={blur}:luma_power=1.5,"
            f"colorchannelmixer=rr={darken}:gg={darken}:bb={darken},"
            # Slow Ken Burns zoom
            f"zoompan=z='min(zoom+0.0004,1.03)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={cfg.VIDEO_FPS}"
            f"[bg];"
        )

        # Card crop with gentle motion
        if scroll_distance <= 0:
            motion_pad = max(cfg.CARD_IDLE_BOB_PX * 2, 24)
            crop_y_expr = (
                f"{motion_pad}+({cfg.CARD_IDLE_BOB_PX}*sin(2*PI*t/{cfg.CARD_IDLE_PERIOD_S:.2f}))"
            )
            card_filter = (
                f"[1:v]scale={card_w}:-1[card_full];"
                f"[card_full]pad={card_w}:{viewport_h + motion_pad * 2}:0:(oh-ih)/2:color=#00000000[card_pad];"
                f"[card_pad]crop={card_w}:{viewport_h}:0:'{crop_y_expr}'[card];"
            )
            overlay_x = f"{card_x}+({cfg.CARD_IDLE_SWAY_PX}*sin(2*PI*t/{cfg.CARD_IDLE_PERIOD_S:.2f}))"
        else:
            scroll_speed = scroll_distance / max(0.1, scroll_duration)
            crop_y_expr = (
                f"min(max((t-{scroll_start:.2f})*{scroll_speed:.4f},0),{scroll_distance})"
            )
            card_filter = (
                f"[1:v]scale={card_w}:-1[card_full];"
                f"[card_full]crop={card_w}:{viewport_h}:0:'{crop_y_expr}'[card];"
            )
            overlay_x = str(card_x)

        # Overlay card on background
        overlay_filter = (
            f"[bg][card]overlay=x='{overlay_x}':y={viewport_top}"
            f":enable='gte(t,{cfg.HOOK_DURATION_S})'[v_card];"
        )

        # Branding strip
        font_path_ff = cfg.FONT_SANS_BOLD.replace("\\", "/").replace(":", "\\:")
        branding_filter = (
            f"[v_card]drawtext="
            f"fontfile='{font_path_ff}':"
            f"text='{cfg.BRANDING_TEXT}':"
            f"fontsize={cfg.BRANDING_FONT_SIZE}:"
            f"fontcolor=white@0.7:"
            f"shadowcolor=black@0.5:shadowx=2:shadowy=2:"
            f"x=(w-text_w)/2:y={cfg.BRANDING_Y}"
            f"[v_brand];"
        )

        # Progress bar (gold)
        progress_filter = (
            f"[v_brand]drawbox="
            f"x=0:y={cfg.PROGRESS_BAR_Y}:"
            f"w='iw*(t/{audio_duration:.3f})':"
            f"h={cfg.PROGRESS_BAR_H}:"
            f"color={cfg.PROGRESS_BAR_COLOR}@0.8:"
            f"t=fill"
            f"[v_prog];"
        )

        # Subtitles
        ass_path_ff = str(subtitle_ass.resolve()).replace("\\", "/").replace(":", "\\:")
        subtitle_filter = f"[v_prog]subtitles='{ass_path_ff}'[out]"

        filter_complex = (
            bg_filter
            + card_filter
            + overlay_filter
            + branding_filter
            + progress_filter
            + subtitle_filter
        )

        print(f"[bible:video] Audio duration: {audio_duration:.1f}s")
        print(f"[bible:video] Card height: {card_height_px}px, scroll: {scroll_distance}px")

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-i", bg_video,
            "-loop", "1", "-i", str(card_png),
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "2:a",
            "-t", str(audio_duration),
            "-c:v", "libx264",
            "-preset", cfg.VIDEO_PRESET,
            "-crf", str(cfg.VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", cfg.VIDEO_AUDIO_BITRATE,
            "-movflags", "+faststart",
            str(output_path),
        ]

        result = subprocess.run(cmd, capture_output=False, text=False)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed (exit {result.returncode}). Check output above.")

    return output_path


def _append_outro(
    video_path: Path,
    outro_png: Path,
    outro_text: str = "",
) -> Path:
    """Append a calm closing screen to the video with audio fade.

    Returns path to the video with outro appended.
    """
    import os
    import subprocess
    import tempfile

    outro_duration = cfg.CLOSING_SCREEN_DURATION_S
    out_path = Path(str(video_path).replace(".mp4", "_with_outro.mp4"))

    with tempfile.TemporaryDirectory(prefix="bible_outro_") as tmp_dir:
        # Create outro video segment (silent)
        outro_video = str(Path(tmp_dir) / "outro.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-loop", "1", "-i", str(outro_png),
                "-t", str(outro_duration),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                outro_video,
            ],
            check=True,
            capture_output=True,
        )

        # Create silent audio segment
        silent_audio = str(Path(tmp_dir) / "silent.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi",
                "-i", f"anullsrc=r=44100:cl=stereo",
                "-t", str(outro_duration),
                silent_audio,
            ],
            check=True,
            capture_output=True,
        )

        # Extract original audio and fade out
        faded_audio = str(Path(tmp_dir) / "faded.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(video_path),
                "-af", f"afade=t=out:st=0:d={outro_duration}",
                "-vn",
                faded_audio,
            ],
            check=True,
            capture_output=True,
        )

        # Concat: video + outro video, audio + silent
        concat_list = str(Path(tmp_dir) / "concat.txt")
        video_abs = str(video_path.resolve()).replace("\\", "/")
        outro_abs = outro_video.replace("\\", "/")
        faded_abs = faded_audio.replace("\\", "/")
        silent_abs = silent_audio.replace("\\", "/")

        with open(concat_list, "w") as f:
            f.write(f"file '{video_abs}'\n")
            f.write(f"file '{outro_abs}'\n")

        concat_audio = str(Path(tmp_dir) / "concat_audio.txt")
        with open(concat_audio, "w") as f:
            f.write(f"file '{faded_abs}'\n")
            f.write(f"file '{silent_abs}'\n")

        # Use concat demuxer
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", concat_list,
                "-f", "concat", "-safe", "0", "-i", concat_audio,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", cfg.VIDEO_AUDIO_BITRATE,
                "-movflags", "+faststart",
                str(out_path),
            ],
            check=True,
            capture_output=True,
        )

    return out_path


def process_category(
    category: str,
    count: int = 3,
    background_clips: Optional[list[Path]] = None,
) -> list[Path]:
    """Process multiple verses from a single category.

    Returns list of published video paths.
    """
    provider = get_provider()
    verses = provider.get_verses_by_category(category)

    if not verses:
        print(f"[bible] No verses found for category: {category}")
        return []

    # Filter out done verses, then pick up to `count`
    available = [v for v in verses if not is_verse_done(v.reference)]

    import random
    random.shuffle(available)

    results: list[Path] = []
    for verse in available[:count]:
        try:
            result = process_verse(verse, background_clips=background_clips)
            if result:
                results.append(result)
        except Exception as exc:
            print(f"[bible] Error processing {verse.reference}: {exc}")
            traceback.print_exc()

    return results


def process_daily_batch(
    count: int = 5,
    categories: Optional[list[str]] = None,
    background_clips: Optional[list[Path]] = None,
) -> list[Path]:
    """Process a diverse daily batch across multiple categories.

    Returns list of published video paths.
    """
    if categories is None:
        categories = cfg.DEFAULT_CATEGORIES

    provider = get_provider()
    verses = provider.get_daily_batch(count)

    results: list[Path] = []
    for verse in verses:
        try:
            result = process_verse(verse, background_clips=background_clips)
            if result:
                results.append(result)
        except Exception as exc:
            print(f"[bible] Error processing {verse.reference}: {exc}")
            traceback.print_exc()

    return results
