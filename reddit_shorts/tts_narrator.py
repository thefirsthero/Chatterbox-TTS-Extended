"""
reddit_shorts/tts_narrator.py — generate ASMR audio via ChatterboxTTS.

Adapted from asmr_longform.py for shorter-form content (60–180 s).
Chunks the script, generates N candidates per chunk, picks the lowest-artifact
take, then assembles with pauses and exports a final normalised WAV + MP3.
"""

import os
import random
import re
import json
import hashlib
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


def estimate_narration_duration(text: str) -> float:
    """
    Estimate the duration (in seconds) of ASMR narration for the given text.
    
    Uses a conservative word-per-minute rate to account for ASMR pacing,
    pauses between chunks, and punctuation-based silence gaps.
    
    Parameters
    ----------
    text : str
        The full narration text (typically a NarrationScript.full_text)
    
    Returns
    -------
    float
        Estimated duration in seconds
    """
    if not text or not text.strip():
        return 0.0
    
    # ASMR narration speaking rate (words per minute)
    # Estimated from ChatterboxTTS + config pause settings (45-140ms between chunks)
    # This is conservative to avoid exceeding the target on actual audio
    WORDS_PER_MINUTE = 105
    
    # Count words (simple: split on whitespace)
    word_count = len(text.split())
    
    # Base narration duration
    duration_s = (word_count / WORDS_PER_MINUTE) * 60
    
    # Account for chunk breaks and pauses:
    # - Average ~50ms pause per chunk
    # - For ~175 char chunks at ~5 chars/word, that's ~35 words per chunk
    # - So roughly 1 pause per 35 words
    estimated_chunks = max(1, word_count // 35)
    avg_pause_ms = 100  # Conservative average of pause min/max
    pause_overhead_s = (estimated_chunks * avg_pause_ms) / 1000.0
    
    total_duration = duration_s + pause_overhead_s
    return total_duration


def _chunk_cache_dir(output_wav: Path) -> Path:
    return output_wav.parent / "_tts_chunks" / output_wav.stem


def _chunk_cache_signature(chunk_text: str, voice_profile: Optional[Path]) -> str:
    payload = {
        "chunk_text": chunk_text,
        "voice_profile": str(voice_profile) if voice_profile else "builtin_default_voice",
        "exaggeration": cfg.TTS_EXAGGERATION,
        "cfg_weight": cfg.TTS_CFG_WEIGHT,
        "temperature": cfg.TTS_TEMPERATURE,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _load_cached_chunk(chunk_path: Path, meta_path: Path, signature: str) -> tuple[Optional[AudioSegment], Optional[int]]:
    if not chunk_path.exists() or not meta_path.exists():
        return None, None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    if meta.get("signature") != signature:
        return None, None
    pause_ms = int(meta.get("pause_ms", cfg.TTS_PAUSE_MIN_MS))
    return AudioSegment.from_wav(str(chunk_path)), pause_ms


def _save_cached_chunk(chunk_path: Path, meta_path: Path, wav: torch.Tensor, sample_rate: int, signature: str, pause_ms: int) -> None:
    wav_to_save = wav if wav.ndim == 2 else wav.unsqueeze(0)
    torchaudio.save(str(chunk_path), wav_to_save.cpu(), sample_rate)
    meta_path.write_text(
        json.dumps({"signature": signature, "pause_ms": pause_ms}, indent=2),
        encoding="utf-8",
    )


# ── TTS text normalisation ──────────────────────────────────────────────────

# Known subreddits with idiomatic spoken forms (CamelCase split often fails these)
_SUBREDDIT_SPOKEN: dict[str, str] = {
    "AmItheAsshole": "Am I The Asshole",
    "AITA": "Am I The Asshole",
    "relationship_advice": "relationship advice",
    "legaladvice": "legal advice",
    "tifu": "today I messed up",
    "TrueOffMyChest": "True Off My Chest",
    "confessions": "confessions",
    "pettyrevenge": "petty revenge",
    "ProRevenge": "pro revenge",
    "MaliciousCompliance": "malicious compliance",
    "entitledparents": "entitled parents",
    "bridezillas": "bridezillas",
    "offmychest": "off my chest",
    "raisedbynarcissists": "raised by narcissists",
    "weddingshaming": "wedding shaming",
    "AmIOverreacting": "Am I Overreacting",
}


def _split_camel_case(name: str) -> str:
    """'RelationshipAdvice' → 'Relationship Advice' (generic fallback)."""
    # Insert space before a capital that follows a lower-case letter
    result = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Handle consecutive caps like 'ACROCase' → 'ACRO Case'
    result = re.sub(r"([A-Z]{2,})([A-Z][a-z])", r"\1 \2", result)
    # Replace underscores (snake_case subreddit names)
    result = result.replace("_", " ")
    return result


def _tts_normalize_text(text: str) -> str:
    """
    Rewrite patterns that a TTS model mis-pronounces into natural spoken English.

    This is applied to the full narration text BEFORE it is chunked and sent
    to ChatterboxTTS.  The original script text is kept unchanged for display /
    subtitle purposes.
    """
    # ── Subreddit mentions ─────────────────────────────────────────────────
    # r/AmItheAsshole  →  r slash Am I The Asshole
    def _expand_subreddit(m: re.Match) -> str:
        raw = m.group(1)
        name = _SUBREDDIT_SPOKEN.get(raw) or _split_camel_case(raw)
        return f"r slash {name}"
    text = re.sub(r"\br/(\w+)", _expand_subreddit, text)

    # ── User mentions ──────────────────────────────────────────────────────
    # u/someuser  →  user someuser  (already handled by script_writer but be safe)
    text = re.sub(r"\bu/(\w+)", r"user \1", text)

    # ── Dollar amounts ─────────────────────────────────────────────────────
    # $300/month  →  300 dollars a month
    text = re.sub(
        r"\$(\d[\d,]*)(?:\s*/\s*month|\s+per\s+month)",
        lambda m: m.group(1).replace(",", "") + " dollars a month",
        text,
    )
    # $1,500  →  1500 dollars
    text = re.sub(
        r"\$(\d[\d,]*)",
        lambda m: m.group(1).replace(",", "") + " dollars",
        text,
    )

    # ── Numbers with commas that TTS reads digit-by-digit ─────────────────
    # 1,121  →  1121  (let TTS say "one thousand one hundred twenty-one")
    text = re.sub(r"(?<!\w)(\d{1,3}),(\d{3})(?!\d)", r"\1\2", text)

    # ── Common Reddit/internet abbreviations ───────────────────────────────
    # (script_writer already handles AITA/NTA/YTA in the body; handle any
    # that slip through in the hook, attribution, or comments)
    abbrevs = {
        r"\bAITA\b": "am I the asshole",
        r"\bWIBTA\b": "would I be the asshole",
        r"\bNTA\b": "not the asshole",
        r"\bYTA\b": "you're the asshole",
        r"\bESH\b": "everyone sucks here",
        r"\bNAH\b": "no assholes here",
        r"\bOP\b": "the original poster",
        r"\bIMO\b": "in my opinion",
        r"\bIMHO\b": "in my honest opinion",
        r"\bTBH\b": "to be honest",
        r"\bTBF\b": "to be fair",
        r"\bIIRC\b": "if I recall correctly",
        r"\bFYI\b": "for your information",
        r"\bTLDR\b": "to summarize",
        r"\bTL;DR\b": "to summarize",
    }
    for pattern, replacement in abbrevs.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # ── Punctuation that causes unnatural pauses or artefacts ─────────────
    # Ellipsis → short pause via comma
    text = text.replace("…", ", ")
    text = re.sub(r"\.{3,}", ", ", text)
    # Em dash without surrounding spaces → add spaces so TTS treats it as a pause
    text = re.sub(r"(?<!\s)—(?!\s)", " — ", text)
    # Doubled dashes
    text = re.sub(r"--+", " — ", text)

    # ── Smart / curly quotes → straight (TTS tokenisers handle these better) ─
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2018", "'").replace("\u2019", "'")

    # ── Tidy up any double spaces introduced above ─────────────────────────
    text = re.sub(r" {2,}", " ", text)
    return text


# ── Text chunking ──────────────────────────────────────────────────────────

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


def _normalize_seg_rms(seg: AudioSegment, target_dbfs: float = -20.0) -> AudioSegment:
    """Adjust gain so all chunks land at the same loudness before crossfade assembly."""
    if seg.dBFS == float("-inf"):
        return seg  # silence, leave alone
    delta = target_dbfs - seg.dBFS
    # Clamp to ±12 dB so we don't amplify near-silent artefact chunks
    delta = max(-12.0, min(12.0, delta))
    return seg.apply_gain(delta)


def _pause_for_chunk_text(chunk_text: str) -> int:
    """Choose a deterministic pause from the chunk's final punctuation."""
    stripped = chunk_text.rstrip()
    if not stripped:
        return cfg.TTS_PAUSE_MIN_MS

    if stripped.endswith(("?", "!")):
        return 170
    if stripped.endswith("."):
        return 135
    if stripped.endswith((":", ";")):
        return 110
    if stripped.endswith(","):
        return 85
    if stripped.endswith(("-",)):
        return 75
    return 60


# ── Post-clean filter ────────────────────────────────────────────────────

def _apply_post_clean(wav_path: str) -> None:
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", wav_path,
              "-af", (
                  # Add slight warmth/presence while avoiding heavy dynamics that caused artifacts.
                  "highpass=f=70,"
                  "lowpass=f=12000,"
                  "equalizer=f=190:width_type=o:width=1.5:g=0.8,"
                  "equalizer=f=260:width_type=o:width=1.8:g=-0.9,"
                  "equalizer=f=3200:width_type=o:width=1.6:g=0.5,"
                  "alimiter=limit=0.97:level_in=1"
              ),
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
    if voice_profile is not None:
        voice_profile = Path(voice_profile)
        if not voice_profile.is_file():
            raise FileNotFoundError(
                f"Voice profile not found: {voice_profile}\n"
                "If you want a custom voice, supply a valid profile file."
            )

    device = _detect_device()
    print(f"[tts] Loading ChatterboxTTS on {device}…")
    model = ChatterboxTTS.from_pretrained(device)
    print(f"[tts] Model loaded. Sample rate: {model.sr}")

    # Either use an explicit saved profile or the model's built-in default voice.
    if voice_profile is not None:
        conds = Conditionals.load(str(voice_profile), map_location="cpu").to(device)
        model.default_conds = conds
        print(f"[tts] Loaded voice profile: {voice_profile}")
    else:
        if model.default_conds is None:
            raise RuntimeError("Built-in default voice is unavailable in the pretrained checkpoint.")
        print("[tts] Using built-in soothing default voice")

    if hasattr(model, "eval"):
        model.eval()

    tts_text = _tts_normalize_text(text)
    max_chunk_chars = cfg.TTS_CPU_MAX_CHUNK_CHARS if device == "cpu" else cfg.TTS_MAX_CHUNK_CHARS
    sentences = _split_sentences(tts_text)
    chunks = _chunk_sentences(sentences, max_chars=max_chunk_chars)
    if not chunks:
        raise ValueError("No text chunks produced.")
    print(f"[tts] {len(chunks)} chunks to generate")

    tmp_dir = _chunk_cache_dir(output_wav)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    assembled: Optional[AudioSegment] = None

    try:
        for idx, chunk_text in enumerate(chunks):
            chunk_file = tmp_dir / f"chunk_{idx:04d}.wav"
            meta_file = tmp_dir / f"chunk_{idx:04d}.json"
            signature = _chunk_cache_signature(chunk_text, voice_profile)
            cached_seg, cached_pause_ms = (None, None)
            if cfg.TTS_RESUME_PARTIALS:
                cached_seg, cached_pause_ms = _load_cached_chunk(chunk_file, meta_file, signature)

            if cached_seg is not None and cached_pause_ms is not None:
                speech = _normalize_seg_rms(cached_seg).fade_in(40).fade_out(40)
                seg = speech + AudioSegment.silent(duration=cached_pause_ms)
                if assembled is None:
                    assembled = seg
                else:
                    assembled = assembled.append(seg, crossfade=cfg.TTS_CROSSFADE_MS)
                print(f"[tts] chunk {idx + 1}/{len(chunks)} resumed from cache")
                continue

            best_wav: Optional[torch.Tensor] = None
            best_score = float("inf")
            n_cands = cfg.TTS_CANDIDATES_PER_CHUNK_CPU if device == "cpu" else cfg.TTS_CANDIDATES_PER_CHUNK

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

            pause_ms = _pause_for_chunk_text(chunk_text)
            _save_cached_chunk(chunk_file, meta_file, best_wav, model.sr, signature, pause_ms)

            speech = _normalize_seg_rms(AudioSegment.from_wav(str(chunk_file))).fade_in(40).fade_out(40)
            seg = speech + AudioSegment.silent(duration=pause_ms)

            if assembled is None:
                assembled = seg
            else:
                assembled = assembled.append(seg, crossfade=cfg.TTS_CROSSFADE_MS)

            print(f"[tts] chunk {idx + 1}/{len(chunks)} score={best_score:.4f}")
    except KeyboardInterrupt:
        print("[tts] Interrupted. Completed chunks remain cached for resume.")
        raise

    if assembled is None:
        raise RuntimeError("No narration audio was assembled.")

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
