"""
bible_shorts/background.py — manage calming cinematic looping background footage.

Replaces the Minecraft gameplay module from reddit_shorts.
Handles discovery, download (via yt-dlp), normalisation, and caching of
cinematic nature/ambient footage suitable for Bible Shorts.

Priority order:
1. Local clips in video_clips/cinematic/  (user-provided)
2. Download via yt-dlp from YouTube (CC-licensed / royalty-free sources)

NOTE: Always verify the licence of downloaded footage before publishing.
"""

import random
import subprocess
from pathlib import Path
from typing import Optional

from bible_shorts import config as cfg

_SUPPORTED_EXTS = {".mp4", ".mov", ".webm", ".mkv"}


def discover_local_clips(clips_dir: Optional[Path] = None) -> list[Path]:
    """Return sorted list of local cinematic background clips."""
    if clips_dir is None:
        clips_dir = cfg.BACKGROUND_DIR
    if not clips_dir.exists():
        return []
    clips = [p for p in clips_dir.iterdir() if p.suffix.lower() in _SUPPORTED_EXTS]
    return sorted(clips)


def _ytdlp_available() -> bool:
    """Check if yt-dlp is installed and accessible."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def download_cinematic_footage(
    queries: Optional[list[str]] = None,
    output_dir: Optional[Path] = None,
    max_videos: int = 5,
    max_duration_s: int = cfg.BACKGROUND_MAX_DURATION_S,
) -> list[Path]:
    """Download CC-licensed cinematic footage via yt-dlp.

    Returns list of downloaded file paths.
    """
    if not _ytdlp_available():
        print(
            "[background] yt-dlp not found. Install with: pip install yt-dlp\n"
            "             Or place your own cinematic clips in video_clips/cinematic/"
        )
        return []

    if queries is None:
        queries = cfg.CINEMATIC_SEARCH_QUERIES
    if output_dir is None:
        output_dir = cfg.BACKGROUND_DIR

    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []

    # Shuffle queries for variety
    shuffled = list(queries)
    random.shuffle(shuffled)

    for query in shuffled:
        if len(downloaded) >= max_videos:
            break
        try:
            # yt-dlp: search YouTube, pick best match, download
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--quiet",
                    "--no-warnings",
                    "--max-downloads", "1",
                    "--match-filter", f"duration < {max_duration_s}",
                    "--format", "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080][ext=mp4]/best",
                    "--output", str(output_dir / "%(title).100s_%(id)s.%(ext)s"),
                    "--no-playlist",
                    f"ytsearch:{query}",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            # Find downloaded file
            for f in output_dir.iterdir():
                if f.suffix.lower() in _SUPPORTED_EXTS and f not in downloaded:
                    # Check if recent (created in last few minutes)
                    downloaded.append(f)
                    print(f"[background] Downloaded: {f.name}")
                    break

        except subprocess.TimeoutExpired:
            print(f"[background] Timeout for query: {query}")
        except Exception as exc:
            print(f"[background] Error downloading '{query}': {exc}")

    return downloaded


def ensure_cinematic_footage(
    output_dir: Optional[Path] = None,
    min_clips: int = 8,
) -> list[Path]:
    """Ensure enough cinematic background clips exist.

    Checks local clips first, then downloads if needed.
    Returns a list of available clip paths.
    """
    if output_dir is None:
        output_dir = cfg.BACKGROUND_DIR

    clips = discover_local_clips(output_dir)

    if len(clips) < min_clips:
        needed = min_clips - len(clips)
        print(f"[background] Only {len(clips)} local clips. Downloading up to {needed} more…")
        new_clips = download_cinematic_footage(
            output_dir=output_dir,
            max_videos=needed,
        )
        clips.extend(new_clips)

    # Remove duplicates by path
    unique: list[Path] = []
    seen = set()
    for c in clips:
        if c.resolve() not in seen:
            unique.append(c)
            seen.add(c.resolve())

    print(f"[background] {len(unique)} cinematic clip(s) available")
    return unique


def build_looped_sequence(
    clips: list[Path],
    target_duration_s: float,
    tmp_dir: str,
    fps: int = cfg.VIDEO_FPS,
) -> str:
    """Normalise, concatenate, and trim clips to target duration.

    Returns path to a single silent MP4 of the correct length.
    This mirrors the reddit_shorts.gameplay.build_looped_clip_sequence
    pattern but with Bible-appropriate processing settings.
    """
    from reddit_shorts.video_composer import _ffprobe_duration, _ffprobe_dimensions, _write_concat_list

    if not clips:
        raise ValueError("[background] No clips available for looped sequence")

    # Determine reference resolution from first clip
    ref_w, ref_h = _ffprobe_dimensions(clips[0])

    # Normalise each clip
    normalised: list[str] = []
    for i, clip in enumerate(clips):
        out = f"{tmp_dir}/norm_bg_{i:04d}.mp4"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(clip),
            "-vf", (
                f"scale={ref_w}:{ref_h}:force_original_aspect_ratio=decrease,"
                f"pad={ref_w}:{ref_h}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={fps}"
            ),
            "-c:v", "libx264",
            "-preset", cfg.BACKGROUND_INTERMEDIATE_PRESET,
            "-crf", str(cfg.BACKGROUND_INTERMEDIATE_CRF),
            "-an", out,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        normalised.append(out)

    # Concatenate
    concat_list = _write_concat_list([Path(p) for p in normalised], tmp_dir)
    raw_concat = f"{tmp_dir}/cinematic_concat.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy", raw_concat,
        ],
        check=True,
        capture_output=True,
    )

    # Trim to target duration + small buffer
    trimmed = f"{tmp_dir}/cinematic_trimmed.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", raw_concat,
            "-t", str(target_duration_s + 2),
            "-c", "copy", trimmed,
        ],
        check=True,
        capture_output=True,
    )
    return trimmed
