"""
reddit_shorts/subtitle_gen.py — generate ASS subtitle files from a narration script.

Word-by-word subtitle timing is estimated from character counts, then scaled
to the actual audio duration.  This keeps the reading experience synchronised
with the ASMR pace without requiring a Whisper transcription pass.

ASS format is used because it supports:
 - Per-event positioning (hook vs. body subtitles)
 - Bold / colour tags inline
 - Shadow and outline rendering for readability over any background
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reddit_shorts import config as cfg
from reddit_shorts.transcription import TimedWord


def _norm_word(word: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", (word or "").lower())


def _find_body_offset(timed_words: list[TimedWord], script_words: list[str], hook_end_s: float) -> int:
    """Find the best timed-word offset where a target phrase likely begins."""
    if not timed_words or not script_words:
        return 0

    probe = [_norm_word(word) for word in script_words[:12] if _norm_word(word)]
    if not probe:
        return 0

    max_offset = max(0, len(timed_words) - len(probe))
    best_offset = 0
    best_score = -1.0

    for offset in range(max_offset + 1):
        if timed_words[offset].start_s < hook_end_s - 0.15:
            continue
        matched = 0
        compared = 0
        for idx, expected in enumerate(probe):
            timed_norm = _norm_word(timed_words[offset + idx].word)
            if not timed_norm:
                continue
            compared += 1
            if timed_norm == expected:
                matched += 1
        if compared == 0:
            continue
        score = matched / compared
        if score > best_score:
            best_score = score
            best_offset = offset

    return best_offset


# ── Timing estimation ────────────────────────────────────────────────────────

def _word_duration_est(word: str) -> float:
    """Estimate how many seconds it takes to say *word* in ASMR pace."""
    stripped = re.sub(r"[^\w]", "", word)
    n = len(stripped)
    if n == 0:
        return 0.12
    if n <= 2:
        return 0.22
    if n <= 4:
        return 0.32
    if n <= 7:
        return 0.44
    return 0.56


def _punctuation_pause(word: str) -> float:
    """Extra silence after punctuation."""
    if word.endswith((".", "!", "?")):
        return 0.38
    if word.endswith((",", ";", ":")):
        return 0.18
    if word.endswith(("—", "–", "...")):
        return 0.22
    return 0.0


def estimate_word_timings(words: list[str]) -> list[tuple[float, float]]:
    """
    Return list of (start_s, end_s) tuples for each word.
    Timings are *unscaled* — caller must scale to actual audio duration.
    """
    timings: list[tuple[float, float]] = []
    t = 0.0
    for word in words:
        dur = _word_duration_est(word)
        timings.append((t, t + dur))
        t += dur + _punctuation_pause(word)
    return timings


def scale_timings(
    timings: list[tuple[float, float]],
    audio_duration_s: float,
    lead_in_s: float = 3.0,    # Subtitle starts after the hook overlay
) -> list[tuple[float, float]]:
    """
    Scale raw timings so they span from *lead_in_s* to *audio_duration_s*.
    """
    if not timings:
        return []
    raw_total = timings[-1][1]
    if raw_total == 0:
        return timings
    available = audio_duration_s - lead_in_s
    scale = available / raw_total
    return [(lead_in_s + s * scale, lead_in_s + e * scale) for s, e in timings]


# ── ASS formatting helpers ────────────────────────────────────────────────

def _ts(seconds: float) -> str:
    """Convert seconds to ASS timestamp format H:MM:SS.cs"""
    cs = int(round(seconds * 100))
    h = cs // 360000
    cs %= 360000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _build_ass_header() -> str:
    return (
        "[Script Info]\n"
        "Title: Reddit Short\n"
        "ScriptType: v4.00+\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n"
        f"PlayResX: {cfg.VIDEO_WIDTH}\n"
        f"PlayResY: {cfg.VIDEO_HEIGHT}\n"
        "YCbCr Matrix: TV.601\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        # Default style — body subtitles, bottom-centre, white with thick black outline
        # Default style — body subtitles, bottom-centre, yellow TikTok-style
        f"Style: Default,{cfg.SUBTITLE_FONT_NAME},{cfg.SUBTITLE_FONT_SIZE},"
        f"{cfg.SUBTITLE_PRIMARY_COLOR},&H000000FF,"
        f"{cfg.SUBTITLE_OUTLINE_COLOR},{cfg.SUBTITLE_BACK_COLOR},"
        f"-1,0,0,0,100,100,0.3,0,1,"
        f"{cfg.SUBTITLE_OUTLINE_SIZE},{cfg.SUBTITLE_SHADOW_SIZE},"
        f"2,60,60,{cfg.SUBTITLE_LINE_MARGIN_V},1\n"
        # Hook style — large, centred in the screen, yellow with dark outline
        f"Style: Hook,{cfg.SUBTITLE_FONT_NAME},78,"
        f"{cfg.SUBTITLE_PRIMARY_COLOR},&H000000FF,"
        f"{cfg.SUBTITLE_OUTLINE_COLOR},{cfg.SUBTITLE_BACK_COLOR},"
        f"-1,0,0,0,100,100,0,0,1,"
        f"{cfg.SUBTITLE_OUTLINE_SIZE + 0.5},{cfg.SUBTITLE_SHADOW_SIZE},"
        "5,80,80,0,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


# ── Public API ────────────────────────────────────────────────────────────

@dataclass
class SubtitleSpec:
    """Carry everything needed to generate an ASS file."""
    hook_text: str
    body_text: str               # Full narration (hook already excluded)
    audio_duration_s: float
    hook_duration_s: float = cfg.HOOK_DURATION_S  # How long to show the hook splash
    timed_words: Optional[list[TimedWord]] = None


def generate_ass(spec: SubtitleSpec, output_path: Path) -> Path:
    """
    Build and save an ASS subtitle file.

    Returns the path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [_build_ass_header()]

    # ── Hook subtitle (first N seconds, large, centre-top positioning) ─────
    hook_clean = re.sub(r"\s+", " ", spec.hook_text).strip()
    # Replace long hook with shorter version if needed
    if len(hook_clean) > 120:
        hook_clean = hook_clean[:117].rsplit(" ", 1)[0] + "\u2026"
    # End the hook subtitle 0.6 s BEFORE the card appears so the two
    # never coexist on screen even at frame-boundary precision.
    hook_end_s = max(0.5, spec.hook_duration_s - 0.6)

    # ── Body subtitles (word-by-word groups of 3–4 words) ─────────────────
    # Split body into words
    timed_words = list(spec.timed_words or [])
    raw_words = spec.body_text.split()
    body_entries: list[tuple[float, float, str]] = []

    if timed_words:
        # Keep bottom subtitles locked to the real spoken words from the start
        # of audio. This avoids delayed starts when script matching drifts.
        timed_body = timed_words
        slot_count = len(timed_body)
        if slot_count <= 0:
            timed_body = []

        GROUP_SIZE = 4
        for i in range(0, slot_count, GROUP_SIZE):
            group_slots = timed_body[i : i + GROUP_SIZE]
            if not group_slots:
                continue
            t_start = max(0.05, group_slots[0].start_s)
            t_end = max(t_start + 0.1, group_slots[-1].end_s)
            if t_end - t_start < 0.45:
                t_end = min(spec.audio_duration_s, t_start + 0.45)
            safe = " ".join((slot.word or "").strip() for slot in group_slots)
            safe = re.sub(r"\s+", " ", safe).strip()
            if not safe:
                continue
            body_entries.append((t_start, t_end, safe))
    elif not raw_words:
        pass
    else:
        # Group words into short phrases (4 words at a time to reduce flicker).
        GROUP_SIZE = 4
        groups: list[str] = []
        for i in range(0, len(raw_words), GROUP_SIZE):
            groups.append(" ".join(raw_words[i : i + GROUP_SIZE]))

        # Estimate individual word timings then group them
        raw_word_timings = estimate_word_timings(raw_words)
        # Scale so subtitles span from hook_end to audio_end
        scaled_timings = scale_timings(
            raw_word_timings,
            spec.audio_duration_s,
            lead_in_s=spec.hook_duration_s + 0.3,
        )

        # Build group timings
        for i, group_text in enumerate(groups):
            word_start_idx = i * GROUP_SIZE
            word_end_idx = min(word_start_idx + GROUP_SIZE - 1, len(scaled_timings) - 1)
            if word_start_idx >= len(scaled_timings):
                break
            t_start = scaled_timings[word_start_idx][0]
            t_end = scaled_timings[word_end_idx][1]

            # Keep subtitles long enough to read comfortably.
            min_dur = 0.45
            if t_end - t_start < min_dur:
                t_end = min(spec.audio_duration_s, t_start + min_dur)

            # Clean text for ASS
            safe = group_text.replace("{", "").replace("}", "").replace("\n", " ")

            body_entries.append((t_start, t_end, safe))

    lines.append(
        f"Dialogue: 0,{_ts(0.0)},{_ts(hook_end_s)},Hook,,0,0,0,,"
        + hook_clean.replace("\n", "\\N")
        + "\n"
    )

    for t_start, t_end, safe in body_entries:
        lines.append(
            f"Dialogue: 0,{_ts(t_start)},{_ts(t_end)},Default,,0,0,0,,"
            + safe
            + "\n"
        )

    content = "".join(lines)
    output_path.write_text(content, encoding="utf-8-sig")  # BOM for compatibility
    print(f"[subtitles] ASS saved: {output_path}")
    return output_path
