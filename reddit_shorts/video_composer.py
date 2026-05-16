"""
reddit_shorts/video_composer.py — assemble the final TikTok/Shorts video via FFmpeg.

Video layout (1080×1920 portrait):
  ┌─────────────────────┐  ← y=0
  │  Branding strip     │  ← ~100 px  (drawtext)
  │  ┌───────────────┐  │
  │  │ Reddit card   │  │  ← card viewport y=120–1660 (scrolling PNG crop)
  │  │  (scrolling)  │  │
  │  └───────────────┘  │
  │  Subtitle band      │  ← y=1670–1880  (ASS subtitles filter)
  │  ══ progress bar ══ │  ← y=1892–1908  (drawbox)
  └─────────────────────┘  ← y=1920

The Minecraft gameplay fills the entire background (scaled-to-fill + boxblur + darken).
The Reddit card PNG is overlaid via a panning crop:  as the narration progresses,
the crop window slides down the tall card, giving a "reading along" feel.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from reddit_shorts import config as cfg
from reddit_shorts.gameplay import build_looped_clip_sequence, discover_local_clips, ensure_gameplay_footage


# ── FFmpeg helpers ───────────────────────────────────────────────────────────

def _ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _ffprobe_dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        w, h = result.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 1920, 1080


def _write_concat_list(clips: list[Path], tmp_dir: str) -> str:
    list_path = os.path.join(tmp_dir, "concat.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for clip in clips:
            safe = str(clip.resolve()).replace("\\", "/")
            f.write(f"file '{safe}'\n")
    return list_path


def _build_gameplay_video(
    clips: list[Path],
    audio_duration: float,
    tmp_dir: str,
    fps: int = cfg.VIDEO_FPS,
) -> str:
    """
    Normalise, concatenate, and trim gameplay clips to audio_duration.
    Returns path to a single silent MP4 of the correct length.
    """
    # Determine reference resolution from first clip
    ref_w, ref_h = _ffprobe_dimensions(clips[0])

    # Normalise each clip to uniform fps + resolution
    normalised: list[str] = []
    for i, clip in enumerate(clips):
        out = os.path.join(tmp_dir, f"norm_{i:04d}.mp4")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(clip),
            "-vf", (
                f"scale={ref_w}:{ref_h}:force_original_aspect_ratio=decrease,"
                f"pad={ref_w}:{ref_h}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={fps}"
            ),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-an", out,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        normalised.append(out)

    # Concatenate
    concat_list = _write_concat_list([Path(p) for p in normalised], tmp_dir)
    raw_concat = os.path.join(tmp_dir, "gameplay_concat.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy", raw_concat,
        ],
        check=True,
        capture_output=True,
    )

    # Trim to exact duration
    trimmed = os.path.join(tmp_dir, "gameplay_trimmed.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", raw_concat,
            "-t", str(audio_duration + 1),
            "-c", "copy", trimmed,
        ],
        check=True,
        capture_output=True,
    )
    return trimmed


# ── Main composition ─────────────────────────────────────────────────────────

def compose_video(
    audio_path: Path,
    card_png: Path,
    subtitle_ass: Path,
    output_path: Path,
    card_height_px: int,
    hook_text: Optional[str] = None,
    gameplay_clips: Optional[list[Path]] = None,
) -> Path:
    """
    Compose the final video and save to *output_path*.

    Parameters
    ----------
    audio_path       : Normalised WAV narration audio
    card_png         : Full Reddit card PNG (may be taller than viewport)
    subtitle_ass     : ASS subtitle file
    output_path      : Where to save the final MP4
    card_height_px   : Height of card_png in pixels
    hook_text        : First hook sentence (drawn as large overlay text, first 3 s)
    gameplay_clips   : Pre-resolved list of background clips (auto-discovered if None)
    """
    audio_path = Path(audio_path)
    card_png = Path(card_png)
    subtitle_ass = Path(subtitle_ass)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_duration = _ffprobe_duration(audio_path)
    if audio_duration <= 0:
        raise ValueError(f"Could not read audio duration from {audio_path}")

    if gameplay_clips is None:
        gameplay_clips = ensure_gameplay_footage()

    W = cfg.VIDEO_WIDTH
    H = cfg.VIDEO_HEIGHT
    fps = cfg.VIDEO_FPS
    card_w = cfg.CARD_WIDTH
    card_x = cfg.CARD_X
    viewport_top = cfg.CARD_VIEWPORT_TOP
    viewport_h = cfg.CARD_VIEWPORT_H
    scroll_start = cfg.CARD_SCROLL_START_S
    scroll_end_margin = cfg.CARD_SCROLL_END_MARGIN_S
    blur = cfg.GAMEPLAY_BLUR_RADIUS
    darken = cfg.GAMEPLAY_DARKEN

    # Scroll math
    scroll_distance = max(0, card_height_px - viewport_h)
    scroll_available = max(1.0, audio_duration - scroll_start - scroll_end_margin)
    scroll_speed = scroll_distance / scroll_available  # px/s

    with tempfile.TemporaryDirectory(prefix="shorts_compose_") as tmp:
        # Step 1: prepare looped + trimmed gameplay
        clip_seq = build_looped_clip_sequence(gameplay_clips, audio_duration + 5)
        gameplay_mp4 = _build_gameplay_video(clip_seq, audio_duration, tmp, fps)

        # Step 2: build FFmpeg filter graph
        # ── Gameplay processing ───────────────────────────────────────────
        gameplay_filter = (
            f"[0:v]"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},"
            f"setsar=1,"
            f"boxblur=luma_radius={blur}:luma_power=2,"
            f"colorchannelmixer=rr={darken}:gg={darken}:bb={darken}"
            f"[bg];"
        )

        # ── Card crop (panning) ───────────────────────────────────────────
        # If card fits in viewport, just centre it vertically. Otherwise scroll.
        if scroll_distance <= 0:
            # Card shorter than viewport — centre it statically
            card_crop_filter = (
                f"[1:v]scale={card_w}:-1[card_full];"
                f"[card_full]pad={card_w}:{viewport_h}:0:(oh-ih)/2:color=#00000000[card];"
            )
        else:
            # Card is taller — crop a moving window
            crop_y_expr = (
                f"min(max((t-{scroll_start:.2f})*{scroll_speed:.4f},0),{scroll_distance})"
            )
            card_crop_filter = (
                f"[1:v]scale={card_w}:-1[card_full];"
                f"[card_full]crop={card_w}:{viewport_h}:0:'{crop_y_expr}'[card];"
            )

        # ── Overlay card on gameplay ──────────────────────────────────────
        overlay_filter = (
            f"[bg][card]overlay=x={card_x}:y={viewport_top}[v_card];"
        )

        # ── Branding strip (top) ──────────────────────────────────────────
        branding = cfg.BRANDING_TEXT.replace("'", "\\'")
        # For cross-platform safety use a font path without backslashes
        font_path_ff = cfg.FONT_BOLD.replace("\\", "/").replace(":", "\\:")
        branding_filter = (
            f"[v_card]drawtext="
            f"fontfile='{font_path_ff}':"
            f"text='{branding}':"
            f"fontsize={cfg.BRANDING_FONT_SIZE}:"
            f"fontcolor=white@0.85:"
            f"shadowcolor=black@0.7:shadowx=2:shadowy=2:"
            f"x=(w-text_w)/2:y={cfg.BRANDING_Y}"
            f"[v_brand];"
        )

        # ── Progress bar ──────────────────────────────────────────────────
        progress_filter = (
            f"[v_brand]drawbox="
            f"x=0:y={cfg.PROGRESS_BAR_Y}:"
            f"w='iw*(t/{audio_duration:.3f})':"
            f"h={cfg.PROGRESS_BAR_H}:"
            f"color={cfg.PROGRESS_BAR_COLOR}@0.95:"
            f"t=fill"
            f"[v_prog];"
        )

        # ── Subtitles (ASS) ───────────────────────────────────────────────
        # FFmpeg subtitles filter needs forward slashes and escaped colons on Windows
        ass_path_ff = str(subtitle_ass.resolve()).replace("\\", "/").replace(":", "\\:")
        subtitle_filter = (
            f"[v_prog]subtitles='{ass_path_ff}'[out]"
        )

        filter_complex = (
            gameplay_filter
            + card_crop_filter
            + overlay_filter
            + branding_filter
            + progress_filter
            + subtitle_filter
        )

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            # Input 0: gameplay
            "-i", gameplay_mp4,
            # Input 1: reddit card image (looped as video)
            "-loop", "1", "-i", str(card_png),
            # Input 2: narration audio
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "2:a",
            "-t", str(audio_duration),
            "-c:v", "libx264",
            "-preset", cfg.VIDEO_PRESET,
            "-crf", str(cfg.VIDEO_CRF),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ]

        print("[video] Composing final video…")
        print(f"[video] Audio duration: {audio_duration:.1f}s")
        print(f"[video] Card height: {card_height_px}px, scroll distance: {scroll_distance}px")

        result = subprocess.run(cmd, capture_output=False, text=False)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed (exit {result.returncode}). Check output above.")

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"[video] Done → {output_path}  ({size_mb:.1f} MB, {audio_duration:.0f}s)")
    return output_path
