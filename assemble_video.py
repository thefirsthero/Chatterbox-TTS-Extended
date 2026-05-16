"""
assemble_video.py — ASMR video assembler
Loops/shuffles short video clips to fill an audio track, then muxes them into a final MP4.

Usage:
    python assemble_video.py --clips video_clips/raw --audio output/batch/ep01_soft_rain.mp3 --output output/video/ep01.mp4
    python assemble_video.py --clips video_clips/raw --audio-dir output/batch --output-dir output/video  # batch mode
"""

import argparse
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def get_duration(path: str) -> float:
    """Return duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise RuntimeError(f"Could not read duration of {path}: {result.stderr}")


def discover_clips(clips_dir: Path) -> list[Path]:
    exts = {".mp4", ".mov", ".webm", ".mkv"}
    clips = [p for p in clips_dir.iterdir() if p.suffix.lower() in exts]
    if not clips:
        raise RuntimeError(f"No video clips found in {clips_dir}")
    return sorted(clips)


def build_looped_clip_list(clips: list[Path], target_duration: float) -> list[Path]:
    """
    Shuffle and repeat clips until total coverage >= target_duration.
    Returns an ordered list of clip paths to concatenate.
    """
    shuffled = clips[:]
    random.shuffle(shuffled)

    result = []
    accumulated = 0.0
    idx = 0
    while accumulated < target_duration:
        clip = shuffled[idx % len(shuffled)]
        result.append(clip)
        accumulated += get_duration(clip)
        idx += 1
        if idx % len(shuffled) == 0:
            random.shuffle(shuffled)  # re-shuffle each full pass for variety

    return result


def write_concat_list(clip_list: list[Path], tmp_dir: str) -> str:
    list_path = os.path.join(tmp_dir, "concat_list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for clip in clip_list:
            # ffmpeg concat demuxer requires forward slashes and escaped paths
            safe = str(clip.resolve()).replace("\\", "/")
            f.write(f"file '{safe}'\n")
    return list_path


def assemble(clips_dir: Path, audio_path: Path, output_path: Path,
             crossfade_sec: float = 0.5, target_fps: int = 30):

    print(f"[video] Assembling: {output_path.name}")
    print(f"[video] Audio: {audio_path}")
    print(f"[video] Clips dir: {clips_dir}")

    audio_duration = get_duration(audio_path)
    print(f"[video] Audio duration: {audio_duration:.1f}s")

    clips = discover_clips(clips_dir)
    print(f"[video] Found {len(clips)} source clip(s): {[c.name for c in clips]}")

    clip_list = build_looped_clip_list(clips, audio_duration + 10)  # +10s buffer
    print(f"[video] Built loop sequence of {len(clip_list)} clips")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="asmr_video_") as tmp:
        # Step 1: re-encode all clips to uniform spec (fps, resolution, codec)
        normalised = []
        ref_w, ref_h = None, None

        for i, clip in enumerate(clip_list):
            out = os.path.join(tmp, f"norm_{i:04d}.mp4")
            # Probe first clip to get resolution
            if ref_w is None:
                probe_cmd = [
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=s=x:p=0", str(clip)
                ]
                res = subprocess.run(probe_cmd, capture_output=True, text=True)
                try:
                    ref_w, ref_h = (int(x) for x in res.stdout.strip().split("x"))
                except Exception:
                    ref_w, ref_h = 1920, 1080

            cmd = [
                "ffmpeg", "-y", "-i", str(clip),
                "-vf", f"scale={ref_w}:{ref_h}:force_original_aspect_ratio=decrease,"
                       f"pad={ref_w}:{ref_h}:(ow-iw)/2:(oh-ih)/2,fps={target_fps}",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-an", out,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            normalised.append(out)

        # Step 2: concatenate (simple concat — clips already normalised)
        concat_list = write_concat_list([Path(p) for p in normalised], tmp)
        raw_video = os.path.join(tmp, "raw_concat.mp4")
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy", raw_video,
        ]
        subprocess.run(concat_cmd, check=True, capture_output=True)

        # Step 3: trim to exact audio duration and mux audio
        final_cmd = [
            "ffmpeg", "-y",
            "-i", raw_video,
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", str(audio_duration),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
        subprocess.run(final_cmd, check=True, capture_output=True)

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"[video] Done → {output_path}  ({size_mb:.1f} MB, {audio_duration:.0f}s)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ASMR video assembler")
    parser.add_argument("--clips", required=True, help="Folder containing raw .mp4 video clips")
    parser.add_argument("--audio", help="Single audio file (.mp3 or .wav)")
    parser.add_argument("--audio-dir", help="Folder of audio files for batch mode")
    parser.add_argument("--output", help="Output .mp4 path (single mode)")
    parser.add_argument("--output-dir", default="output/video", help="Output folder (batch mode)")
    parser.add_argument("--fps", type=int, default=30, help="Output frame rate (default 30)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for clip ordering")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    clips_dir = Path(args.clips)
    if not clips_dir.is_dir():
        print(f"ERROR: clips folder not found: {clips_dir}", file=sys.stderr)
        sys.exit(1)

    # ── single mode ──
    if args.audio:
        if not args.output:
            print("ERROR: --output required in single mode", file=sys.stderr)
            sys.exit(1)
        assemble(clips_dir, Path(args.audio), Path(args.output), target_fps=args.fps)
        return

    # ── batch mode ──
    if args.audio_dir:
        audio_dir = Path(args.audio_dir)
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        audio_files = sorted(
            p for p in audio_dir.iterdir()
            if p.suffix.lower() in {".mp3", ".wav"}
        )
        if not audio_files:
            print(f"ERROR: no audio files found in {audio_dir}", file=sys.stderr)
            sys.exit(1)

        print(f"[batch] Found {len(audio_files)} audio file(s)")
        for audio in audio_files:
            out = out_dir / (audio.stem + ".mp4")
            if out.exists():
                print(f"[batch] Skipping (exists): {out.name}")
                continue
            assemble(clips_dir, audio, out, target_fps=args.fps)

        print("\n[batch] All done.")
        return

    print("ERROR: provide --audio (single) or --audio-dir (batch)", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
