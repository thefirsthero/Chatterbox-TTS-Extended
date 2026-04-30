import argparse
import datetime
import os
import random
import re
import shutil
import subprocess
import tempfile
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


def _artifact_score(wav: torch.Tensor, sample_rate: int) -> float:
    """
    Heuristic artifact score. Lower is better.
    Penalizes clipping, extreme crest factor (bursty gasps/plosives),
    and excessive low-frequency rumble often perceived as "wind".
    """
    x = wav
    if x.ndim == 2:
        x = x[0]
    x = x.detach().float().cpu()

    if x.numel() == 0:
        return 1e9

    eps = 1e-8
    rms = torch.sqrt(torch.mean(x * x) + eps).item()
    peak = torch.max(torch.abs(x)).item()
    crest = peak / (rms + eps)
    clipped_ratio = (torch.abs(x) > 0.98).float().mean().item()

    # FFT power ratio below 120 Hz (wind/rumble indicator)
    n = int(x.numel())
    if n < 128:
        low_ratio = 0.0
    else:
        spec = torch.fft.rfft(x)
        power = torch.abs(spec) ** 2
        freqs = torch.fft.rfftfreq(n, d=1.0 / float(sample_rate))
        total = torch.sum(power).item() + eps
        low = torch.sum(power[freqs < 120.0]).item()
        low_ratio = low / total

    score = 0.0
    score += clipped_ratio * 25.0
    score += max(0.0, crest - 7.5) * 0.6
    score += max(0.0, low_ratio - 0.28) * 8.0
    # Avoid near-silent degenerations
    if rms < 0.01:
        score += 4.0
    return float(score)


def _apply_post_clean_filter_if_available(wav_path: str) -> None:
    """Run a gentle ffmpeg cleanup chain in-place if ffmpeg is available."""
    if not shutil.which("ffmpeg"):
        print("[ASMR] ffmpeg not found; skipping post-clean filter")
        return

    fd, temp_out = tempfile.mkstemp(prefix="asmr_clean_", suffix=".wav")
    os.close(fd)
    try:
        filt = "highpass=f=80,lowpass=f=12000,afftdn=nf=-24,alimiter=limit=0.93"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", wav_path,
            "-af", filt,
            temp_out,
        ]
        subprocess.run(cmd, check=True)
        os.replace(temp_out, wav_path)
        print("[ASMR] Applied post-clean filter (ffmpeg)")
    except Exception as exc:
        print(f"[ASMR] Post-clean filter skipped: {exc}")
        if os.path.exists(temp_out):
            try:
                os.remove(temp_out)
            except OSError:
                pass


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
    candidates_per_chunk: int,
    clean_mode: bool,
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
    generated_chunk_paths: list[str] = []
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

        # Generate N candidates and keep the one with the lowest artifact score.
        best_wav = None
        best_score = float("inf")
        n_cands = max(1, int(candidates_per_chunk))
        for cand_idx in range(n_cands):
            # Deterministic-but-distinct seed per chunk/candidate.
            cand_seed = seed + (pass_num * 100000) + (idx * 100) + cand_idx
            torch.manual_seed(cand_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(cand_seed)

            wav = model.generate(
                chunk_text,
                audio_prompt_path=None,
                exaggeration=local_exag,
                cfg_weight=cfg_weight,
                temperature=local_temp,
                apply_watermark=False,
            )
            score = _artifact_score(wav, model.sr)
            if score < best_score:
                best_score = score
                best_wav = wav

        if best_wav is None:
            raise RuntimeError("Failed to generate candidate chunk")

        chunk_path = os.path.join("temp", f"asmr_chunk_{pass_num:02d}_{idx:04d}.wav")
        wav_to_save = best_wav if best_wav.ndim == 2 else best_wav.unsqueeze(0)
        torchaudio.save(chunk_path, wav_to_save.cpu(), model.sr)
        generated_chunk_paths.append(chunk_path)
        if clean_mode:
            print(f"[ASMR][clean] chunk {pass_num:02d}/{idx:04d} selected score={best_score:.4f} ({n_cands} cands)")

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

    if clean_mode:
        _apply_post_clean_filter_if_available(output_path)

    # Always clean temp chunk files created by this run.
    for p in generated_chunk_paths:
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass

    print(f"[ASMR] Saved WAV: {output_path}")

    if export_mp3:
        mp3_path = output_path.rsplit(".", 1)[0] + ".mp3"
        assembled.export(mp3_path, format="mp3", bitrate="320k")
        print(f"[ASMR] Saved MP3: {mp3_path}")

    print(f"[ASMR] Final duration: {len(assembled) / 1000:.1f}s")
    return output_path


def batch_render(args) -> None:
    """
    Discover every .txt file in --scripts-dir and render each one using the
    shared locked voice profile. Already-rendered outputs are skipped so the
    run is safely resumable.

    Output files are written to --output-dir (default: output/batch/) using the
    same stem as the script file, e.g. scripts/ep01_rain.txt → output/batch/ep01_rain.wav
    """
    scripts_dir = args.scripts_dir
    output_dir = args.output_dir or os.path.join("output", "batch")
    os.makedirs(output_dir, exist_ok=True)

    script_files = sorted(
        p for p in (
            os.path.join(scripts_dir, f)
            for f in os.listdir(scripts_dir)
            if f.lower().endswith(".txt")
        )
        if os.path.isfile(p)
    )

    if not script_files:
        raise ValueError(f"No .txt files found in: {scripts_dir}")

    print(f"[batch] Found {len(script_files)} script(s) in {scripts_dir}")

    results: list[tuple[str, str, str]] = []  # (script, output, status)

    for script_path in script_files:
        stem = os.path.splitext(os.path.basename(script_path))[0]
        out_wav = os.path.join(output_dir, f"{stem}.wav")
        out_mp3 = os.path.join(output_dir, f"{stem}.mp3")

        # Skip if already rendered (wav or mp3 present)
        if os.path.isfile(out_wav) or os.path.isfile(out_mp3):
            print(f"[batch] SKIP (already exists): {stem}")
            results.append((script_path, out_wav, "skipped"))
            continue

        print(f"\n[batch] ── Rendering: {stem} ──")
        with open(script_path, "r", encoding="utf-8") as fh:
            text = fh.read()

        try:
            render_asmr(
                text=text,
                reference_audio=args.reference_audio,
                output_path=out_wav,
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
                voice_profile_out=None,  # only save profile once, from first run
                candidates_per_chunk=args.candidates_per_chunk,
                clean_mode=args.clean_mode,
            )
            results.append((script_path, out_wav, "ok"))
        except Exception as exc:
            print(f"[batch] ERROR rendering {stem}: {exc}")
            results.append((script_path, out_wav, f"error: {exc}"))

    # Summary table
    print("\n╔══ Batch summary " + "═" * 52 + "╗")
    ok = sum(1 for _, _, s in results if s == "ok")
    skip = sum(1 for _, _, s in results if s == "skipped")
    err = sum(1 for _, _, s in results if s.startswith("error"))
    print(f"  Total: {len(results)}  ✓ ok: {ok}  ⏭ skipped: {skip}  ✗ errors: {err}")
    print("─" * 70)
    for script, out, status in results:
        tag = "✓" if status == "ok" else ("⏭" if status == "skipped" else "✗")
        print(f"  {tag} {os.path.basename(script):<40} → {os.path.basename(out)}")
    print("╚" + "═" * 69 + "╝\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-form ASMR generator (10-25 min) for Chatterbox")
    # ── Bulk mode ──────────────────────────────────────────────────────────
    parser.add_argument(
        "--scripts-dir", type=str, default=None,
        help="Folder of .txt scripts to render in bulk (one output per file)."
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Destination folder for bulk output (default: output/batch/). "
             "Only used with --scripts-dir."
    )
    # ── Single-file / inline mode ──────────────────────────────────────────
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
    parser.add_argument("--candidates-per-chunk", type=int, default=1, help="Generate N candidates per chunk and keep the cleanest")
    parser.add_argument("--clean-mode", action="store_true", help="Enable artifact-safe defaults + post-clean filter")

    args = parser.parse_args()

    if args.clean_mode:
        # Conservative defaults to reduce wind/gasp artifacts.
        args.temperature = min(args.temperature, 0.36)
        args.exaggeration = min(args.exaggeration, 0.22)
        args.cfg_weight = max(args.cfg_weight, 0.50)
        args.temp_drift = 0.0
        args.exaggeration_drift = 0.0

        args.pause_min_ms = max(args.pause_min_ms, 600)
        args.pause_max_ms = max(args.pause_max_ms, 1300)
        args.crossfade_ms = max(args.crossfade_ms, 90)

        args.min_chunk_chars = max(args.min_chunk_chars, 90)
        args.max_chunk_chars = min(args.max_chunk_chars, 170)
        if args.max_chunk_chars <= args.min_chunk_chars:
            args.max_chunk_chars = args.min_chunk_chars + 40

        if args.candidates_per_chunk < 2:
            args.candidates_per_chunk = 3

        print("[ASMR] Clean mode enabled")
        print(
            "[ASMR] Clean params: "
            f"temp={args.temperature}, exag={args.exaggeration}, cfg={args.cfg_weight}, "
            f"cands/chunk={args.candidates_per_chunk}, crossfade={args.crossfade_ms}"
        )

    # ── Route to batch or single-file mode ───────────────────────────────
    if args.scripts_dir:
        if not os.path.isdir(args.scripts_dir):
            raise NotADirectoryError(f"--scripts-dir not found: {args.scripts_dir}")
        batch_render(args)
        return

    if not args.text_file and not args.text:
        raise ValueError("Provide --scripts-dir, --text-file, or --text")

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
        candidates_per_chunk=args.candidates_per_chunk,
        clean_mode=args.clean_mode,
    )


if __name__ == "__main__":
    main()
