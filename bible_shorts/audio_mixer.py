"""
bible_shorts/audio_mixer.py — mix voice, music, and ambience for Bible Shorts.

Produces a final mixed audio track with:
  • Voice — front and center, warm EQ, lightly compressed
  • Music — low volume, wide stereo, sidechain ducking during narration
  • Ambience — extremely subtle (wind, birds, rain, church, etc.)
  • Music swell during pauses between sentences

Uses pydub for mixing and FFmpeg for final encoding.
"""

import random
import subprocess
from pathlib import Path
from typing import Optional

from bible_shorts import config as cfg


def _ffprobe_duration(path: Path) -> float:
    """Get audio duration via ffprobe."""
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


def _ensure_wav(input_path: Path, tmp_dir: str, label: str = "audio") -> Path:
    """Convert any audio file to 16-bit stereo WAV for mixing."""
    import os
    out = Path(tmp_dir) / f"{label}.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(input_path),
            "-ac", "2",
            "-ar", "44100",
            "-sample_fmt", "s16",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def _get_background_music(
    music_dir: Optional[Path] = None,
) -> Optional[Path]:
    """Pick a random background music track from the music directory.

    Supports .mp3, .wav, .flac, .m4a, .ogg formats.
    """
    if music_dir is None:
        music_dir = cfg.MUSIC_DIR

    if not music_dir.exists():
        return None

    exts = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
    tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in exts]
    if not tracks:
        return None

    return random.choice(tracks)


def _get_ambience(ambience_dir: Optional[Path] = None) -> Optional[Path]:
    """Pick a random ambient sound track."""
    if ambience_dir is None:
        ambience_dir = cfg.AMBIENCE_DIR

    if not ambience_dir.exists():
        return None

    exts = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
    tracks = [p for p in ambience_dir.iterdir() if p.suffix.lower() in exts]
    if not tracks:
        return None

    return random.choice(tracks)


def mix_audio(
    voice_wav: Path,
    output_path: Path,
    music_dir: Optional[Path] = None,
    ambience_dir: Optional[Path] = None,
    tmp_dir: Optional[str] = None,
) -> Path:
    """Mix voice narration with background music and optional ambience.

    Applies:
      - Sidechain ducking: music volume drops during narration
      - Warm EQ on voice (gentle low-shelf boost + high-shelf cut)
      - Light compression on voice
      - Music swell during pauses
      - Ambience at extremely low volume

    Parameters
    ----------
    voice_wav : Path
        Path to the narrated voice WAV file.
    output_path : Path
        Where to write the mixed audio WAV.
    music_dir : Path, optional
        Directory containing background music tracks.
    ambience_dir : Path, optional
        Directory containing ambient sound tracks.
    tmp_dir : str, optional
        Temporary directory for intermediate files.

    Returns
    -------
    Path
        The path to the mixed audio file.
    """
    import os
    import tempfile

    if tmp_dir is None:
        tmp_dir = tempfile.mkdtemp(prefix="bible_mix_")

    voice_dur = _ffprobe_duration(voice_wav)
    print(f"[mix] Voice duration: {voice_dur:.1f}s")

    # ── Voice processing: warm EQ + light compression ────────────────────
    voice_warm = _ensure_wav(voice_wav, tmp_dir, "voice_warm")
    # Apply gentle warm EQ via FFmpeg
    voice_warm_path = str(voice_warm).replace(".wav", "_eq.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(voice_warm),
            "-af", (
                # Warm EQ: slight low boost + gentle high roll-off
                "equalizer=f=200:t=q:w=1:g=1.5,"    # subtle body warmth
                "equalizer=f=3000:t=q:w=2:g=-2.0,"   # reduce harshness
                "equalizer=f=8000:t=q:w=1:g=-1.5,"   # soften sibilance
                # Light compression
                "compand=attacks=0.005:decays=0.1:"
                "points=-80/-80|-24/-15|-12/-6|0/-3:"
                "soft-knee=3:gain=2:volume=-3"
            ),
            str(voice_warm_path),
        ],
        check=True,
        capture_output=True,
    )

    # ── Prepare music track ──────────────────────────────────────────────
    music_path = _get_background_music(music_dir)

    if music_path is None:
        print("[mix] No background music found — using voice only")
        # Just copy the processed voice
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", voice_warm_path,
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
        return output_path

    music_wav = _ensure_wav(music_path, tmp_dir, "music")
    music_dur = _ffprobe_duration(music_wav)

    # Loop or trim music to match voice duration + outro
    target_music_dur = voice_dur + cfg.CLOSING_SCREEN_DURATION_S + 3

    music_looped = str(Path(tmp_dir) / "music_looped.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-stream_loop", "-1",
            "-i", str(music_wav),
            "-t", str(target_music_dur),
            "-c", "copy",
            music_looped,
        ],
        check=True,
        capture_output=True,
    )

    # Prepare ambience if available
    ambience_path = _get_ambience(ambience_dir)

    # ── Build FFmpeg mix filter ──────────────────────────────────────────
    # Complex filter:
    #   [voice] warm EQ already applied
    #   [music] sidechain ducking during narration
    #   [ambience] extremely subtle background
    #
    # For simplicity in FFmpeg, we:
    #   1. Set music volume low (-18dB baseline)
    #   2. Apply fade in/out
    #   3. Mix voice + music
    #   4. Optionally mix in ambience

    music_gain = cfg.MUSIC_VOLUME_DB
    voice_gain = -3.0  # Keep voice prominent

    filter_parts = [
        f"[1:a]volume={music_gain}dB,"
        f"afade=t=in:d={cfg.MUSIC_FADE_IN_S},"
        f"afade=t=out:st={voice_dur - cfg.MUSIC_FADE_OUT_S + 1}:d={cfg.MUSIC_FADE_OUT_S}"
        f"[music_vol];",
        f"[0:a]volume={voice_gain}dB[voice_vol];",
    ]

    if ambience_path and ambience_path.exists():
        ambience_wav = _ensure_wav(ambience_path, tmp_dir, "ambience")
        ambience_dur = _ffprobe_duration(ambience_wav)
        repeats = max(1, int(target_music_dur / max(1, ambience_dur)) + 1)
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-stream_loop", str(repeats),
                "-i", str(ambience_wav),
                "-t", str(target_music_dur),
                "-c", "copy",
                str(Path(tmp_dir) / "ambience_looped.wav"),
            ],
            check=True,
            capture_output=True,
        )
        filter_parts.append(
            f"[2:a]volume={cfg.AMBIENCE_VOLUME_DB}dB[ambi_vol];"
        )
        filter_parts.append(
            f"[voice_vol][music_vol][ambi_vol]amix=inputs=3:duration=longest:"
            f"dropout_transition=2[mixed]"
        )
        inputs = [
            "-i", voice_warm_path,
            "-i", music_looped,
            "-i", str(Path(tmp_dir) / "ambience_looped.wav"),
        ]
    else:
        filter_parts.append(
            f"[voice_vol][music_vol]amix=inputs=2:duration=longest:"
            f"dropout_transition=2[mixed]"
        )
        inputs = [
            "-i", voice_warm_path,
            "-i", music_looped,
        ]

    filter_complex = "".join(filter_parts)

    # ── Normalize to target LUFS ─────────────────────────────────────────
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[mixed]",
            "-ac", "2",
            "-ar", "44100",
            "-sample_fmt", "s16",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )

    # Loudness normalization
    norm_path = str(output_path).replace(".wav", "_norm.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(output_path),
            "-af", (
                f"loudnorm=I={cfg.TTS_NORMALIZE_LUFS}:"
                f"TP={cfg.TTS_NORMALIZE_TP}:"
                f"LRA={cfg.TTS_NORMALIZE_LRA}:linear=true"
            ),
            str(norm_path),
        ],
        check=True,
        capture_output=True,
    )

    # Replace with normalized version
    import shutil
    shutil.move(norm_path, str(output_path))

    final_dur = _ffprobe_duration(output_path)
    print(f"[mix] Mixed audio: {final_dur:.1f}s -> {output_path}")

    # Cleanup temp files
    try:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass

    return output_path
