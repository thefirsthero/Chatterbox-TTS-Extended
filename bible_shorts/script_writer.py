"""
bible_shorts/script_writer.py — generate Bible narration scripts.

Structure (proven for Shorts retention):
  1. Hook        — 2-4 sec emotional grab (e.g. "Feeling overwhelmed today?")
  2. Verse       — The Scripture text, read slowly
  3. Reflection  — AI-style practical meaning in modern language (1-2 sentences)
  4. CTA         — Soft call to action (e.g. "Save this for later.")

The script is assembled as a single full_text string for TTS narration,
with the verse reference included as a spoken attribution before the verse.
"""

from dataclasses import dataclass

from bible_shorts import config as cfg
from bible_shorts.content import (
    BibleVerse,
    get_cta,
    get_hook,
    get_reflection,
)


@dataclass
class BibleScript:
    """A complete Bible Shorts narration script ready for TTS."""
    hook: str               # Attention-grabbing opening (2-4 sec)
    verse_ref: str          # e.g. "Psalm 23, verse 1."
    verse_text: str         # The Scripture text
    reflection: str         # 1-2 sentences of practical meaning
    cta: str                # Soft call to action
    full_text: str          # Concatenated full narration for TTS
    category: str           # Content category for rendering choices
    verse: BibleVerse       # Source verse data


def _format_verse_ref(verse: BibleVerse) -> str:
    """Format the verse reference for spoken narration.

    Example: "Psalm 23 verse 1" instead of "Psalm 23:1"
    """
    return f"{verse.book} chapter {verse.chapter}, verse {verse.verse}."


def generate_script(verse: BibleVerse) -> BibleScript:
    """Build a complete Bible Shorts narration script.

    Parameters
    ----------
    verse : BibleVerse
        The verse to build a script around.

    Returns
    -------
    BibleScript
        The assembled script ready for TTS narration.
    """
    category = verse.category

    hook = get_hook(category)
    verse_ref = _format_verse_ref(verse)
    verse_text = verse.text
    reflection = get_reflection(category)
    cta = get_cta()

    # Assemble full text with double newlines as audible pauses between sections.
    # The TTS chunker respects double newlines as natural break points.
    parts = [
        hook,
        "",
        verse_ref + " " + verse_text,
        "",
        reflection,
        "",
        cta,
    ]
    full_text = "\n\n".join(p for p in parts if p)

    return BibleScript(
        hook=hook,
        verse_ref=verse_ref,
        verse_text=verse_text,
        reflection=reflection,
        cta=cta,
        full_text=full_text,
        category=category,
        verse=verse,
    )


def generate_script_for_category(category: str) -> BibleScript | None:
    """Generate a script for a random verse in the given category.

    Returns None if no verses exist for that category.
    """
    from bible_shorts.content import get_provider

    provider = get_provider()
    verse = provider.get_random_verse(category)
    if verse is None:
        return None
    return generate_script(verse)


def generate_script_for_reference(reference: str) -> BibleScript | None:
    """Generate a script for a specific verse reference.

    Returns None if the reference is not found.
    """
    from bible_shorts.content import get_provider

    provider = get_provider()
    verse = provider.get_verse_by_reference(reference)
    if verse is None:
        return None
    return generate_script(verse)
