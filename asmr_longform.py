import argparse
import datetime
import os
import random
import re
from typing import List

import numpy as np
import torch
import torchaudio
from pydub import AudioSegment

from chatterbox.src.chatterbox.tts import ChatterboxTTS, Conditionals


def detect_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def split_sentences(text: str) -> List[str]:
    # Simple sentence splitter to avoid hard dependency on NLTK in this script.
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p and p.strip()]


def chunk_sentences(sentences: List[str], min_chars: int = 60, max_chars: int = 180) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue

        if len(s) > max_chars:
            if current:
                chunks.append(" ".join(current).strip())
                current = []
                current_len = 0
            forced = [s[i:i + max_chars].strip() for i in range(0, len(s), max_chars)]
            chunks.extend([f for f in forced if f])
            continue

        add_len = len(s) + (1 if current else 0)
        if current_len + add_len <= max_chars:
            current.append(s)
            current_len += add_len
        else:
            merged = " ".join(current).strip()
            if merged:
                chunks.append(merged)
            current = [s]
            current_len = len(s)

    if current:
        merged = " ".join(current).strip()
        if merged:
            chunks.append(merged)

    # Ensure very short chunks are merged forward where possible for smoother cadence.
    merged_chunks: List[str] = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if len(c) >= min_chars or i == len(chunks) - 1:
            merged_chunks.append(c)
            i += 1
            continue

        candidate = (c + " " + chunks[i + 1]).strip()
        if len(candidate) <= max_chars:
            merged_chunks.append(candidate)
            i += 2
        else:
            merged_chunks.append(c)
            i += 1

    return merged_chunks


def estimate_required_words(minutes: float, wpm: int = 105) -> int:
    return int(minutes * wpm)


def render_asmr(
    text: str,
    reference_audio: str | None,
    output_path: str,
    target_minutes: float,
    exaggeration: float,
    cfg_weight: float,
    temperature: float,
    pause_min_ms: int,
    pause_max_ms: int,
    crossfade_ms: int,
    min_chunk_chars: int,
    max_chunk_chars: int,
    seed: int,
    loop_script: bool,
    export_mp3: bool,
    temp_drift: float,
    exaggeration_drift: float,
    voice_profile_in: str | None,
    voice_profile_out: str | None,
) -> str:
    if not reference_audio and not voice_profile_in:
        raise ValueError("Provide --reference-audio or --voice-profile-in")

    if reference_audio and not os.path.isfile(reference_audio):
        raise FileNotFoundError(f"Reference audio not found: {reference_audio}")

    if voice_profile_in and not os.path.isfile(voice_profile_in):
        raise FileNotFoundError(f"Voice profile not found: {voice_profile_in}")

    if target_minutes < 10 or target_minutes > 25:
        raise ValueError("target_minutes must be between 10 and 25 for this ASMR workflow")

    text = normalize_text(text)
    if not text:
        raise ValueError("Input text is empty")

    words = len(re.findall(r"\b\w+\b", text))
    needed = estimate_required_words(target_minutes)
    if words < needed and not loop_script:
        raise ValueError(
            f"Input appears too short ({words} words) for {target_minutes:.1f} min. "
            f"Provide around {needed}+ words or enable --loop-script."
        )

    set_seed(seed)
    device = detect_device()
    print(f"[ASMR] Device: {device}")

    model = ChatterboxTTS.from_pretrained(device)
    print(f"[ASMR] Model loaded. Sample rate: {model.sr}")

    # Build/load a fixed speaker profile once and reuse it for every chunk.
    if voice_profile_in:
        conds = Conditionals.load(voice_profile_in, map_location="cpu").to(device)
        print(f"[ASMR] Loaded voice profile: {voice_profile_in}")
    else:
        conds = model._build_conditionals(reference_audio, exaggeration=0.5)
        if voice_profile_out:
            os.makedirs(os.path.dirname(voice_profile_out) or ".", exist_ok=True)
            conds.save(voice_profile_out)
            print(f"[ASMR] Saved voice profile: {voice_profile_out}")

    model.default_conds = conds

    sentences = split_sentences(text)
    chunks = chunk_sentences(sentences, min_chars=min_chunk_chars, max_chars=max_chunk_chars)
    if not chunks:
        raise ValueError("No chunks were produced from input text")

    os.makedirs("temp", exist_ok=True)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    assembled: AudioSegment | None = None
    target_ms = int(target_minutes * 60 * 1000)
    idx = 0
    pass_num = 0

    while True:
        if idx >= len(chunks):
            if not loop_script:
                break
            idx = 0
            pass_num += 1

        chunk_text = chunks[idx]
        # Drift is optional; set drift args to 0.0 for strict speaker consistency.
        if temp_drift > 0:
            local_temp = max(0.2, min(1.0, temperature + random.uniform(-temp_drift, temp_drift)))
        else:
            local_temp = temperature

        if exaggeration_drift > 0:
            local_exag = max(0.1, min(0.9, exaggeration + random.uniform(-exaggeration_drift, exaggeration_drift)))
        else:
            local_exag = exaggeration

        wav = model.generate(
            chunk_text,
            audio_prompt_path=None,
            exaggeration=local_exag,
            cfg_weight=cfg_weight,
            temperature=local_temp,
            apply_watermark=False,
        )

        chunk_path = os.path.join("temp", f"asmr_chunk_{pass_num:02d}_{idx:04d}.wav")
        torchaudio.save(chunk_path, wav.cpu(), model.sr)

        seg = AudioSegment.from_wav(chunk_path)
        pause = AudioSegment.silent(duration=random.randint(pause_min_ms, pause_max_ms))
        seg = seg + pause

        if assembled is None:
            assembled = seg
        else:
            assembled = assembled.append(seg, crossfade=max(0, crossfade_ms))

        idx += 1

        if assembled is not None and len(assembled) >= target_ms:
            break

    if assembled is None:
        raise RuntimeError("No audio was generated")

    if len(assembled) > target_ms:
        assembled = assembled[:target_ms]

    assembled.export(output_path, format="wav")
    print(f"[ASMR] Saved WAV: {output_path}")

    if export_mp3:
        mp3_path = output_path.rsplit(".", 1)[0] + ".mp3"
        assembled.export(mp3_path, format="mp3", bitrate="320k")
        print(f"[ASMR] Saved MP3: {mp3_path}")

    print(f"[ASMR] Final duration: {len(assembled) / 1000:.1f}s")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-form ASMR generator (10-25 min) for Chatterbox")
    parser.add_argument("--text-file", type=str, default=None, help="Path to input script text file")
    parser.add_argument("--text", type=str, default=None, help="Inline input script text")
    parser.add_argument("--reference-audio", type=str, default=None, help="Reference WAV/MP3 used to build speaker profile")
    parser.add_argument("--voice-profile-in", type=str, default=None, help="Path to prebuilt speaker profile (.pt)")
    parser.add_argument("--voice-profile-out", type=str, default=None, help="Optional output path to save speaker profile (.pt)")
    parser.add_argument("--target-minutes", type=float, default=12.0, help="Target output duration in minutes (10-25)")
    parser.add_argument("--output", type=str, default=None, help="Output WAV path")

    parser.add_argument("--seed", type=int, default=20260429)
    parser.add_argument("--exaggeration", type=float, default=0.32)
    parser.add_argument("--cfg-weight", type=float, default=0.36)
    parser.add_argument("--temperature", type=float, default=0.46)

    parser.add_argument("--pause-min-ms", type=int, default=420)
    parser.add_argument("--pause-max-ms", type=int, default=1050)
    parser.add_argument("--crossfade-ms", type=int, default=45)
    parser.add_argument("--temp-drift", type=float, default=0.0, help="Per-chunk random drift for temperature (0 for strict)")
    parser.add_argument("--exaggeration-drift", type=float, default=0.0, help="Per-chunk random drift for exaggeration (0 for strict)")

    parser.add_argument("--min-chunk-chars", type=int, default=60)
    parser.add_argument("--max-chunk-chars", type=int, default=180)

    parser.add_argument("--loop-script", action="store_true", help="Repeat script if needed to hit target duration")
    parser.add_argument("--export-mp3", action="store_true", help="Also export a 320k MP3")

    args = parser.parse_args()

    if not args.text_file and not args.text:
        raise ValueError("Provide either --text-file or --text")

    text = args.text or ""
    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            file_text = f.read()
        text = (text + "\n\n" + file_text).strip() if text else file_text

    if args.output:
        out_path = args.output
    else:
        ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        out_path = os.path.join("output", f"asmr_longform_{ts}.wav")

    render_asmr(
        text=text,
        reference_audio=args.reference_audio,
        output_path=out_path,
        target_minutes=args.target_minutes,
        exaggeration=args.exaggeration,
        cfg_weight=args.cfg_weight,
        temperature=args.temperature,
        pause_min_ms=args.pause_min_ms,
        pause_max_ms=args.pause_max_ms,
        crossfade_ms=args.crossfade_ms,
        min_chunk_chars=args.min_chunk_chars,
        max_chunk_chars=args.max_chunk_chars,
        seed=args.seed,
        loop_script=args.loop_script,
        export_mp3=args.export_mp3,
        temp_drift=args.temp_drift,
        exaggeration_drift=args.exaggeration_drift,
        voice_profile_in=args.voice_profile_in,
        voice_profile_out=args.voice_profile_out,
    )


if __name__ == "__main__":
    main()
