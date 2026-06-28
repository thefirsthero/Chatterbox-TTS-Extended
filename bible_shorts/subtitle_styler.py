"""
bible_shorts/subtitle_styler.py — Bible-optimized ASS subtitle generation.

Builds on the reddit_shorts subtitle infrastructure but applies:
  - Warm cream / gold colour palette
  - Clean sans-serif typography
  - Word highlighting for key theological terms
  - Phrase-based timing (4-7 words per caption block)
  - Smooth fade transitions
  - Vertical-safe positioning for mobile

The subtitle data (timings) comes from the shared transcription module.
This module only handles the styling and ASS file generation.
"""

import re
from pathlib import Path
from typing import Optional

from bible_shorts import config as cfg


def _norm_word(word: str) -> str:
    """Normalise a word for comparison."""
    return re.sub(r"[^a-z0-9']+", "", (word or "").lower())


def generate_bible_ass(
    script_text: str,
    audio_duration_s: float,
    output_path: Path,
    hook_text: Optional[str] = None,
) -> Path:
    """Generate a styled ASS subtitle file for Bible Shorts.

    Uses phrase-based timing (maximum 4-7 words per block) with
    word highlighting for theological keywords.

    Parameters
    ----------
    script_text : str
        The full narration text (hook + verse + reflection + CTA).
    audio_duration_s : float
        Total audio duration in seconds (for scaling).
    output_path : Path
        Where to write the .ass file.
    hook_text : str, optional
        The hook text, used to time the hook phase separately.

    Returns
    -------
    Path
        The path to the generated .ass file.
    """
    # ── Split text into phrases ─────────────────────────────────────────
    words = script_text.split()
    if not words:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("", encoding="utf-8")
        return output_path

    # Group into phrases of 4-7 words (break at natural pauses)
    phrases: list[list[str]] = []
    current: list[str] = []
    max_phrase = 7
    min_phrase = 3

    for word in words:
        current.append(word)
        # Break at natural pause points
        ends_pause = any(word.rstrip().endswith(p) for p in (".", "!", "?", ",", ";", ":", "—"))
        if ends_pause and len(current) >= min_phrase:
            phrases.append(current)
            current = []
        elif len(current) >= max_phrase:
            phrases.append(current)
            current = []

    if current:
        # Merge short trailing phrase with previous
        if len(current) < min_phrase and phrases:
            phrases[-1].extend(current)
        else:
            phrases.append(current)

    # ── Estimate timing ─────────────────────────────────────────────────
    # Distribute audio duration across phrases weighted by word count
    word_counts = [len(p) for p in phrases]
    total_words = sum(word_counts)
    if total_words == 0:
        return output_path

    # Hook offset: first ~HOOK_DURATION_S seconds reserved for hook display
    hook_offset = cfg.HOOK_DURATION_S if hook_text else 0.0
    available_duration = audio_duration_s - hook_offset - 1.0  # 1s buffer

    phrase_durations = [
        (count / total_words) * available_duration
        for count in word_counts
    ]

    # ── Build ASS file ──────────────────────────────────────────────────
    ass_lines = _build_ass_header()

    t = hook_offset
    for i, (phrase_words, dur) in enumerate(zip(phrases, phrase_durations)):
        start = t
        end = t + max(dur, 1.0)  # Minimum 1 second per phrase
        t = end + 0.05  # Small gap between phrases

        phrase_text = " ".join(phrase_words)
        styled_text = _apply_word_highlights(phrase_text)

        # ASS dialogue event
        start_ts = _secs_to_ass_time(start)
        end_ts = _secs_to_ass_time(end)

        ass_lines.append(
            f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{styled_text}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(ass_lines), encoding="utf-8")
    return output_path


def _build_ass_header() -> list[str]:
    """Build the ASS subtitle header with Bible-appropriate styling.

    Subtitle zone: y=1620 to y=1870 (progress bar below at 1895)
    """
    font_name = cfg.SUBTITLE_FONT_NAME
    font_size = cfg.SUBTITLE_FONT_SIZE

    # Center alignment, safe vertical positioning
    margin_v = cfg.SUBTITLE_LINE_MARGIN_V
    margin_h = 40

    return [
        "[Script Info]",
        "Title: Bible Shorts Subtitles",
        "ScriptType: v4.00+",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: None",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        (
            f"Style: Default,{font_name},{font_size},"
            f"{cfg.SUBTITLE_PRIMARY_COLOR},"
            f"&H00000000,"          # Secondary (unused)
            f"{cfg.SUBTITLE_OUTLINE_COLOR},"
            f"{cfg.SUBTITLE_BACK_COLOR},"
            f"1,0,0,0,100,100,0,0,1,"
            f"{cfg.SUBTITLE_OUTLINE_SIZE:.1f},"
            f"{cfg.SUBTITLE_SHADOW_SIZE:.1f},"
            f"2,{margin_h},{margin_h},{margin_v},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]


def _apply_word_highlights(text: str) -> str:
    """Wrap highlighted words in ASS override tags (gold color).

    Detects key theological terms and wraps them in {\\c&H...} tags.
    Uses a lambda replacement to avoid regex escape issues with \\c.
    """
    gold = cfg.HIGHLIGHT_COLOR
    cream = cfg.SUBTITLE_PRIMARY_COLOR

    def _build_highlight(m: re.Match) -> str:
        word = m.group(0)
        return f"{{\\c{gold}}}{word}{{\\c{cream}}}"

    result = text
    for word in cfg.HIGHLIGHT_WORDS:
        pattern = rf'\b({re.escape(word)})\b'
        result = re.sub(pattern, _build_highlight, result)

    return result


def _secs_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format: H:MM:SS.cc"""
    seconds = max(0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ── Integration with word-level timestamps ──────────────────────────────────

def generate_bible_ass_from_timed_words(
    timed_words: list,  # list[TimedWord] from reddit_shorts.transcription
    output_path: Path,
    script_text: str = "",
) -> Path:
    """Generate ASS subtitles from actual word-level timestamps (Whisper output).

    Groups words into phrases of 4-7, using actual timing data.
    """
    from reddit_shorts.subtitle_gen import _word_duration_est, _punctuation_pause

    if not timed_words:
        return generate_bible_ass(script_text, 60.0, output_path)

    # Group timed words into phrases
    phrases: list[list] = []  # list of list of TimedWord
    current: list = []
    max_phrase = 7
    min_phrase = 3

    for tw in timed_words:
        current.append(tw)
        word_text = tw.word if hasattr(tw, 'word') else str(tw)
        ends_pause = any(
            word_text.rstrip().endswith(p) for p in (".", "!", "?", ",", ";", ":", "—")
        )
        if ends_pause and len(current) >= min_phrase:
            phrases.append(current)
            current = []
        elif len(current) >= max_phrase:
            phrases.append(current)
            current = []

    if current:
        if len(current) < min_phrase and phrases:
            phrases[-1].extend(current)
        else:
            phrases.append(current)

    # Build ASS
    ass_lines = _build_ass_header()

    for phrase_words in phrases:
        phrase_text = " ".join(
            getattr(w, 'word', str(w)) for w in phrase_words
        )
        styled_text = _apply_word_highlights(phrase_text)

        start_s = getattr(phrase_words[0], 'start_s', 0.0)
        end_s = getattr(phrase_words[-1], 'end_s', start_s + 1.0)

        start_ts = _secs_to_ass_time(start_s)
        end_ts = _secs_to_ass_time(end_s)

        ass_lines.append(
            f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{styled_text}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(ass_lines), encoding="utf-8")
    return output_path
