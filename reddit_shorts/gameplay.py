"""
reddit_shorts/gameplay.py — manage background gameplay footage.

Priority order:
1. Local clips in video_clips/raw/  (user-provided or previously downloaded)
2. Download via yt-dlp from YouTube (CC-licensed or fair-use sources)

NOTE: Always verify the licence of downloaded footage before publishing.
      The default search terms target no-commentary / CC-friendly channels.
      You are responsible for compliance with platform terms of service.
"""

import random
import subprocess
import sys
from pathlib import Path
from typing import Optional

from reddit_shorts import config as cfg

_SUPPORTED_EXTS = {".mp4", ".mov", ".webm", ".mkv"}


def discover_local_clips(clips_dir: Optional[Path] = None) -> list[Path]:
    if clips_dir is None:
        clips_dir = cfg.GAMEPLAY_DIR
    if not clips_dir.exists():
        return []
    clips = [p for p in clips_dir.iterdir() if p.suffix.lower() in _SUPPORTED_EXTS]
    return sorted(clips)


def _ytdlp_available() -> bool:
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def download_gameplay_footage(
    queries: Optional[list[str]] = None,
    output_dir: Optional[Path] = None,
    max_videos: int = 3,
    max_duration_s: int = cfg.GAMEPLAY_MAX_DURATION_S,
) -> list[Path]:
    """
    Download CC-friendly Minecraft gameplay clips via yt-dlp.

    Returns list of downloaded file paths.
    """
    if not _ytdlp_available():
        print(
            "[gameplay] yt-dlp not found. Install with: pip install yt-dlp\n"
            "           Or place your own gameplay clips in video_clips/raw/"
        )
        return []

    if queries is None:
        queries = cfg.DEFAULT_GAMEPLAY_QUERIES
    if output_dir is None:
        output_dir = cfg.GAMEPLAY_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []

    for query in queries[:max_videos]:
        search_url = f"ytsearch1:{query}"
        out_template = str(output_dir / "%(id)s.%(ext)s")

        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--match-filter", f"duration < {max_duration_s}",
            "--format", cfg.GAMEPLAY_YTDLP_FORMAT,
            "--merge-output-format", "mp4",
            "--output", out_template,
            "--no-warnings",
            "--quiet",
            "--progress",
            search_url,
        ]
        print(f"[gameplay] Downloading: {query!r}")
        try:
            result = subprocess.run(cmd, capture_output=False, text=False)
            if result.returncode == 0:
                # Find the newly downloaded file
                new_clips = discover_local_clips(output_dir)
                for clip in new_clips:
                    if clip not in downloaded:
                        downloaded.append(clip)
        except Exception as exc:
            print(f"[gameplay] Download failed for query {query!r}: {exc}")

    print(f"[gameplay] {len(downloaded)} clip(s) available in {output_dir}")
    return downloaded


def ensure_gameplay_footage(auto_download: bool = True) -> list[Path]:
    """
    Return available gameplay clips, downloading if necessary.

    Raises RuntimeError if no footage is available after attempting download.
    """
    clips = discover_local_clips()

    if not clips and auto_download:
        print("[gameplay] No local clips found. Attempting to download…")
        clips = download_gameplay_footage()

    if not clips:
        raise RuntimeError(
            "No gameplay footage available.\n"
            f"  • Place MP4/MOV clips in: {cfg.GAMEPLAY_DIR}\n"
            "  • Or install yt-dlp and let the pipeline download them automatically.\n"
            "  • Or set auto_download=True in the pipeline config."
        )

    print(f"[gameplay] {len(clips)} clip(s) ready")
    return clips


def get_duration(clip_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(clip_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def build_looped_clip_sequence(clips: list[Path], target_duration_s: float) -> list[Path]:
    """
    Shuffle clips and repeat until their combined duration covers target_duration_s.
    """
    shuffled = clips[:]
    random.shuffle(shuffled)

    result: list[Path] = []
    accumulated = 0.0
    idx = 0

    while accumulated < target_duration_s:
        clip = shuffled[idx % len(shuffled)]
        result.append(clip)
        accumulated += get_duration(clip)
        idx += 1
        if idx % len(shuffled) == 0:
            random.shuffle(shuffled)

    return result
