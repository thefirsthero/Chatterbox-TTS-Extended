"""
reddit_shorts/transcription.py - lightweight Whisper word-timestamp helpers.

Used by the Shorts pipeline to build subtitle timings from the actual narration
audio instead of estimating timings from text length.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reddit_shorts import config as cfg


@dataclass
class TimedWord:
    word: str
    start_s: float
    end_s: float


def _normalize_word(word: str) -> str:
    cleaned = (word or "").strip()
    return cleaned.replace("{", "").replace("}", "")


def _match_script_words(timed_words: list[TimedWord], expected_text: Optional[str]) -> list[TimedWord]:
    if not timed_words or not expected_text:
        return timed_words

    expected_words = [word for word in expected_text.split() if word.strip()]
    if not expected_words:
        return timed_words

    pair_count = min(len(expected_words), len(timed_words))
    coverage = pair_count / max(1, len(expected_words))
    if coverage < 0.55:
        return timed_words

    return [
        TimedWord(
            word=expected_words[index],
            start_s=timed_words[index].start_s,
            end_s=timed_words[index].end_s,
        )
        for index in range(pair_count)
    ]


def _transcribe_openai(audio_path: Path, model_name: str, expected_text: Optional[str]) -> list[TimedWord]:
    import whisper

    model = whisper.load_model(model_name, device="cpu")
    result = model.transcribe(
        str(audio_path),
        language=cfg.SUBTITLE_TRANSCRIBE_LANGUAGE,
        word_timestamps=True,
        fp16=False,
        condition_on_previous_text=False,
    )

    words: list[TimedWord] = []
    for segment in result.get("segments", []):
        for word_info in segment.get("words", []):
            word = _normalize_word(word_info.get("word", ""))
            start_s = float(word_info.get("start", 0.0))
            end_s = float(word_info.get("end", start_s))
            if not word or end_s <= start_s:
                continue
            words.append(TimedWord(word=word, start_s=start_s, end_s=end_s))
    return words


def _transcribe_faster(audio_path: Path, model_name: str, expected_text: Optional[str]) -> list[TimedWord]:
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(
        str(audio_path),
        language=cfg.SUBTITLE_TRANSCRIBE_LANGUAGE,
        word_timestamps=True,
        beam_size=1,
        best_of=1,
        condition_on_previous_text=False,
    )

    words: list[TimedWord] = []
    for segment in segments:
        for word_info in getattr(segment, "words", []) or []:
            word = _normalize_word(getattr(word_info, "word", ""))
            start_s = float(getattr(word_info, "start", 0.0) or 0.0)
            end_s = float(getattr(word_info, "end", start_s) or start_s)
            if not word or end_s <= start_s:
                continue
            words.append(TimedWord(word=word, start_s=start_s, end_s=end_s))
    return words


def transcribe_word_timestamps(audio_path: Path, expected_text: Optional[str] = None) -> list[TimedWord]:
    """Return word timestamps for *audio_path*, falling back between backends."""
    audio_path = Path(audio_path)
    backends = []
    if cfg.SUBTITLE_TRANSCRIBE_BACKEND == "faster-whisper":
        backends = ["faster-whisper", "openai-whisper"]
    else:
        backends = ["openai-whisper", "faster-whisper"]

    last_error: Optional[Exception] = None
    for backend in backends:
        try:
            if backend == "faster-whisper":
                words = _transcribe_faster(audio_path, cfg.SUBTITLE_TRANSCRIBE_MODEL, expected_text)
            else:
                words = _transcribe_openai(audio_path, cfg.SUBTITLE_TRANSCRIBE_MODEL, expected_text)
            if words:
                print(f"[transcribe] {backend} produced {len(words)} timed words")
                return words
        except Exception as exc:
            last_error = exc
            print(f"[transcribe] {backend} failed: {exc}")

    if last_error:
        print(f"[transcribe] Falling back to heuristic subtitles: {last_error}")
    return []