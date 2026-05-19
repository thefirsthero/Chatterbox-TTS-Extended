"""
reddit_shorts/tts_narrator.py — generate ASMR audio via ChatterboxTTS.

Adapted from asmr_longform.py for shorter-form content (60–180 s).
Chunks the script, generates N candidates per chunk, picks the lowest-artifact
take, then assembles with pauses and exports a final normalised WAV + MP3.
"""

import os
import random
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torchaudio
from pydub import AudioSegment

from chatterbox.src.chatterbox.tts import ChatterboxTTS, Conditionals
from reddit_shorts import config as cfg


# ── Device detection ────────────────────────────────────────────────────────

def _detect_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# ── Text preprocessing ──────────────────────────────────────────────────────

def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def _chunk_sentences(
    sentences: list[str],
    min_chars: int = cfg.TTS_MIN_CHUNK_CHARS,
    max_chars: int = cfg.TTS_MAX_CHUNK_CHARS,
) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if len(s) > max_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current, current_len = [], 0
            chunks.extend(
                s[i : i + max_chars].strip()
                for i in range(0, len(s), max_chars)
                if s[i : i + max_chars].strip()
            )
            continue
        add_len = len(s) + (1 if current else 0)
        if current_len + add_len <= max_chars:
            current.append(s)
            current_len += add_len
        else:
            if current:
                chunks.append(" ".join(current).strip())
            current, current_len = [s], len(s)

    if current:
        chunks.append(" ".join(current).strip())

    # Merge tiny trailing chunks into the previous
    merged: list[str] = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if len(c) >= min_chars or i == len(chunks) - 1:
            merged.append(c)
            i += 1
        elif i + 1 < len(chunks):
            candidate = (c + " " + chunks[i + 1]).strip()
            if len(candidate) <= max_chars:
                merged.append(candidate)
                i += 2
            else:
                merged.append(c)
                i += 1
        else:
            merged.append(c)
            i += 1
    return merged


# ── Artifact scoring (from asmr_longform.py) ─────────────────────────────

def _artifact_score(wav: torch.Tensor, sample_rate: int) -> float:
    x = wav[0] if wav.ndim == 2 else wav
    x = x.detach().float().cpu()
    if x.numel() == 0:
        return 1e9
    eps = 1e-8
    rms = torch.sqrt(torch.mean(x * x) + eps).item()
    peak = torch.max(torch.abs(x)).item()
    crest = peak / (rms + eps)
    clipped = (torch.abs(x) > 0.98).float().mean().item()
    n = int(x.numel())
    if n >= 128:
        spec = torch.fft.rfft(x)
        power = torch.abs(spec) ** 2
        freqs = torch.fft.rfftfreq(n, d=1.0 / float(sample_rate))
        low_ratio = (torch.sum(power[freqs < 120.0]) / (torch.sum(power) + eps)).item()
    else:
        low_ratio = 0.0
    score = clipped * 25.0 + max(0.0, crest - 7.5) * 0.6 + max(0.0, low_ratio - 0.28) * 8.0
    if rms < 0.01:
        score += 4.0
    return float(score)


# ── Post-clean filter ────────────────────────────────────────────────────

def _apply_post_clean(wav_path: str) -> None:
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", wav_path,
            "-af", "highpass=f=60,lowpass=f=14000,alimiter=limit=0.97",
            tmp,
        ]
        subprocess.run(cmd, check=True)
        os.replace(tmp, wav_path)
    except Exception as exc:
        print(f"[tts] Post-clean skipped: {exc}")
        if os.path.exists(tmp):
            os.remove(tmp)


# ── Loudness normalisation ────────────────────────────────────────────────

def _normalize_loudness(wav_path: str, out_path: str) -> None:
    lufs = cfg.TTS_NORMALIZE_LUFS
    tp = cfg.TTS_NORMALIZE_TP
    lra = cfg.TTS_NORMALIZE_LRA
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", wav_path,
        "-af", f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=none",
        out_path,
    ]
    subprocess.run(cmd, check=True)


# ── Main generation function ──────────────────────────────────────────────

def generate_narration(
    text: str,
    output_wav: Path,
    voice_profile: Optional[Path] = None,
    seed: int = cfg.TTS_SEED,
) -> Path:
    """
    Generate ASMR narration for *text* and save it to *output_wav*.

    Returns the path to the normalised WAV file.
    """
    output_wav = Path(output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)

    if voice_profile is None:
        voice_profile = cfg.VOICE_PROFILE

    if not Path(voice_profile).is_file():
        raise FileNotFoundError(
            f"Voice profile not found: {voice_profile}\n"
            "Run the Chatterbox Gradio app and save a locked voice profile first."
        )

    device = _detect_device()
    print(f"[tts] Loading ChatterboxTTS on {device}…")
    model = ChatterboxTTS.from_pretrained(device)
    print(f"[tts] Model loaded. Sample rate: {model.sr}")

    # Load voice profile and set as model default
    conds = Conditionals.load(str(voice_profile), map_location="cpu").to(device)
    model.default_conds = conds
    print(f"[tts] Loaded voice profile: {voice_profile}")

    sentences = _split_sentences(text)
    chunks = _chunk_sentences(sentences)
    if not chunks:
        raise ValueError("No text chunks produced.")
    print(f"[tts] {len(chunks)} chunks to generate")

    tmp_dir = cfg.TEMP_DIR / "tts"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    assembled: Optional[AudioSegment] = None

    for idx, chunk_text in enumerate(chunks):
        best_wav: Optional[torch.Tensor] = None
        best_score = float("inf")
        n_cands = cfg.TTS_CANDIDATES_PER_CHUNK

        for cand_idx in range(n_cands):
            cand_seed = seed + idx * 100 + cand_idx
            torch.manual_seed(cand_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(cand_seed)

            wav = model.generate(
                chunk_text,
                audio_prompt_path=None,
                exaggeration=cfg.TTS_EXAGGERATION,
                cfg_weight=cfg.TTS_CFG_WEIGHT,
                temperature=cfg.TTS_TEMPERATURE,
                apply_watermark=False,
            )
            score = _artifact_score(wav, model.sr)
            if score < best_score:
                best_score = score
                best_wav = wav

        if best_wav is None:
            raise RuntimeError(f"Chunk {idx}: all candidates failed")

        chunk_path = str(tmp_dir / f"chunk_{idx:04d}.wav")
        wav_to_save = best_wav if best_wav.ndim == 2 else best_wav.unsqueeze(0)
        torchaudio.save(chunk_path, wav_to_save.cpu(), model.sr)

        seg = AudioSegment.from_wav(chunk_path)
        pause_ms = random.randint(cfg.TTS_PAUSE_MIN_MS, cfg.TTS_PAUSE_MAX_MS)
        seg = seg + AudioSegment.silent(duration=pause_ms)

        if assembled is None:
            assembled = seg
        else:
            assembled = assembled.append(seg, crossfade=cfg.TTS_CROSSFADE_MS)

        print(f"[tts] chunk {idx + 1}/{len(chunks)} score={best_score:.4f}")

    # Export raw assembly
    raw_wav = str(tmp_dir / "raw_assembly.wav")
    assembled.export(raw_wav, format="wav")

    # Apply gentle post-clean filter
    _apply_post_clean(raw_wav)

    # Normalise loudness
    _normalize_loudness(raw_wav, str(output_wav))
    print(f"[tts] Audio saved: {output_wav}")

    # Export MP3 alongside
    mp3_path = output_wav.with_suffix(".mp3")
    mp3_cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(output_wav), "-codec:a", "libmp3lame", "-b:a", "192k",
        str(mp3_path),
    ]
    subprocess.run(mp3_cmd, check=True)
    print(f"[tts] MP3 saved: {mp3_path}")

    return output_wav


def get_audio_duration(wav_path: Path) -> float:
    """Return duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0
