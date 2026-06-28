#!/usr/bin/env python
"""
run_bible_shorts.py — CLI entry point for the Bible Shorts pipeline.

Produces high-engagement, calming, premium-quality Bible Shorts optimized
for TikTok, Instagram Reels, and YouTube Shorts.

Usage examples:

  # Produce up to 5 videos from random categories
  python run_bible_shorts.py

  # Produce 3 videos from a specific category
  python run_bible_shorts.py --category peace --count 3

  # Produce videos from multiple categories
  python run_bible_shorts.py --categories peace,hope,faith --count 5

  # Process a specific verse by reference
  python run_bible_shorts.py --verse "John 3:16"

  # Process a specific verse by book/chapter/verse
  python run_bible_shorts.py --book Psalm --chapter 23 --verse 1

  # Dry-run: just print what would be processed
  python run_bible_shorts.py --dry-run

  # List available categories
  python run_bible_shorts.py --list-categories

  # List verses in a category
  python run_bible_shorts.py --list-verses peace

  # Download cinematic background footage only
  python run_bible_shorts.py --download-background-only

  # Use a custom voice profile
  python run_bible_shorts.py --voice-profile voice_profiles/my_bible_voice.pt

  # Daily batch: diverse verses across all categories
  python run_bible_shorts.py --daily --count 7
"""

import argparse
import sys
from pathlib import Path


def _setup_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Bible Scripture → ASMR Shorts automated pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Content selection
    p.add_argument(
        "--category", default=None,
        help="Single category to generate from (peace, hope, strength, faith, love, wisdom, "
             "encouragement, forgiveness, anxiety, psalms, proverbs, gospel, hardship)",
    )
    p.add_argument(
        "--categories", default=None,
        help="Comma-separated list of categories for multi-category batch (overrides --category)",
    )
    p.add_argument(
        "--count", type=int, default=5, metavar="N",
        help="Maximum number of videos to produce (default: 5)",
    )
    p.add_argument(
        "--daily", action="store_true",
        help="Produce a diverse daily batch across all categories",
    )

    # Specific verse selection
    p.add_argument(
        "--verse", default=None, metavar="REF",
        help="Process a specific verse by reference (e.g. 'John 3:16')",
    )
    p.add_argument(
        "--book", default=None,
        help="Book name for a specific verse lookup (used with --chapter and --verse)",
    )
    p.add_argument(
        "--chapter", type=int, default=None,
        help="Chapter number (used with --book and --verse)",
    )
    p.add_argument(
        "--verse-num", type=int, default=None, dest="verse_num",
        help="Verse number (used with --book and --chapter)",
    )

    # Pipeline control
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without generating audio/video",
    )
    p.add_argument(
        "--no-skip-done", action="store_true",
        help="Do not skip verses already listed in done_verses.txt",
    )
    p.add_argument(
        "--voice-profile", default=None, dest="voice_profile",
        help="Path to a .pt voice profile file (overrides config.py default)",
    )

    # Background footage
    p.add_argument(
        "--download-background-only", action="store_true",
        help="Just download cinematic background clips and exit",
    )
    p.add_argument(
        "--no-background-download", action="store_true",
        help="Do not attempt to download background footage automatically",
    )

    # Info
    p.add_argument(
        "--list-categories", action="store_true",
        help="List all available verse categories and exit",
    )
    p.add_argument(
        "--list-verses", default=None, metavar="CATEGORY",
        help="List verses in a category and exit",
    )

    return p.parse_args()


def main() -> int:
    args = _setup_args()

    # ── Info commands (no processing) ────────────────────────────────────
    if args.list_categories:
        from bible_shorts.content import get_provider
        provider = get_provider()
        print("\nAvailable Bible Shorts categories:\n")
        for cat in provider.categories:
            count = len(provider.get_verses_by_category(cat))
            print(f"  {cat:<20} ({count} verses)")
        print()
        return 0

    if args.list_verses:
        from bible_shorts.content import get_provider
        provider = get_provider()
        verses = provider.get_verses_by_category(args.list_verses)
        if not verses:
            print(f"No verses found for category: {args.list_verses}")
            print(f"Available: {', '.join(provider.categories)}")
            return 1
        print(f"\nVerses in '{args.list_verses}':\n")
        for v in verses:
            print(f"  {v.reference:<20} {v.text[:80]}…")
        print(f"\n  ({len(verses)} verses total)\n")
        return 0

    # ── Background download only ─────────────────────────────────────────
    if args.download_background_only:
        from bible_shorts.background import ensure_cinematic_footage
        clips = ensure_cinematic_footage(min_clips=10)
        print(f"\nDownloaded/available: {len(clips)} cinematic background clips")
        for c in clips:
            print(f"  {c.name}")
        return 0

    # ── Voice profile override ───────────────────────────────────────────
    if args.voice_profile:
        from bible_shorts import config as cfg
        profile_path = Path(args.voice_profile)
        if not profile_path.exists():
            print(f"Error: Voice profile not found: {profile_path}")
            return 1
        cfg.BIBLE_VOICE_PROFILE = profile_path
        print(f"[bible] Using voice profile: {profile_path}")

    # ── Specific verse ───────────────────────────────────────────────────
    if args.verse:
        return _process_single_verse(args)

    if args.book:
        return _process_book_verse(args)

    # ── Category batch ───────────────────────────────────────────────────
    return _process_category_batch(args)


def _process_single_verse(args) -> int:
    """Process a single verse by reference string."""
    from bible_shorts.content import get_provider
    from bible_shorts.pipeline import process_verse

    provider = get_provider()
    verse = provider.get_verse_by_reference(args.verse)

    if verse is None:
        print(f"Error: Verse not found: {args.verse}")
        print(f"Available references include:")
        for v in provider.get_daily_batch(10):
            print(f"  {v.reference}")
        return 1

    print(f"\nVerse: {verse.reference}")
    print(f"Category: {verse.category}")
    print(f"Text: {verse.text}\n")

    if args.dry_run:
        print("[dry-run] Would process this verse. Exiting.")
        return 0

    result = process_verse(
        verse,
        skip_if_done=not args.no_skip_done,
    )

    if result:
        print(f"\n✅ Video published: {result}")
        return 0
    else:
        print("\n⚠️ Video was not produced (see above for details)")
        return 1


def _process_book_verse(args) -> int:
    """Process a verse specified by book, chapter, and verse number."""
    from bible_shorts.content import get_provider
    from bible_shorts.pipeline import process_verse

    provider = get_provider()

    # Build reference string
    book = args.book.strip()
    chapter = args.chapter or 1
    verse_num = args.verse_num or 1
    reference = f"{book} {chapter}:{verse_num}"

    verse = provider.get_verse_by_reference(reference)

    if verse is None:
        print(f"Error: Verse not found: {reference}")
        return 1

    print(f"\nVerse: {verse.reference}")
    print(f"Category: {verse.category}")
    print(f"Text: {verse.text}\n")

    if args.dry_run:
        print("[dry-run] Would process this verse. Exiting.")
        return 0

    result = process_verse(
        verse,
        skip_if_done=not args.no_skip_done,
    )

    if result:
        print(f"\n✅ Video published: {result}")
        return 0
    else:
        print("\n⚠️ Video was not produced")
        return 1


def _process_category_batch(args) -> int:
    """Process a batch of verses from one or more categories."""
    from bible_shorts.content import get_provider
    from bible_shorts.pipeline import (
        process_category,
        process_daily_batch,
        is_verse_done,
    )

    provider = get_provider()

    # Determine categories
    if args.categories:
        categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    elif args.category:
        categories = [args.category]
    else:
        # Default: use all available categories
        categories = provider.categories

    # Filter to valid categories
    valid_cats = [c for c in categories if c in provider.categories]
    invalid_cats = [c for c in categories if c not in provider.categories]
    if invalid_cats:
        print(f"Warning: Unknown categories: {', '.join(invalid_cats)}")

    if not valid_cats:
        print("Error: No valid categories specified.")
        print(f"Available: {', '.join(provider.categories)}")
        return 1

    print(f"\nCategories: {', '.join(valid_cats)}")
    print(f"Target count: {args.count}")
    print()

    # ── Dry run ───────────────────────────────────────────────────────
    if args.dry_run:
        if args.daily:
            verses = provider.get_daily_batch(args.count)
        else:
            import random
            verses = []
            for cat in valid_cats:
                cat_verses = provider.get_verses_by_category(cat)
                available = [v for v in cat_verses if not is_verse_done(v.reference)]
                random.shuffle(available)
                verses.extend(available[:max(1, args.count // len(valid_cats))])

        print(f"[dry-run] Would process {len(verses)} verse(s):\n")
        for v in verses:
            status = "✓ already done" if is_verse_done(v.reference) else "→ would process"
            print(f"  {v.reference:<20} [{v.category}]  {status}")
        print()
        return 0

    # ── Process ───────────────────────────────────────────────────────
    if args.daily:
        print("[bible] Running daily batch…")
        results = process_daily_batch(count=args.count)
    else:
        # Distribute --count across categories but cap total
        results = []
        remaining = args.count
        for cat in valid_cats:
            if remaining <= 0:
                break
            per_cat = min(remaining, max(1, 1))
            cat_results = process_category(cat, count=per_cat)
            results.extend(cat_results)
            remaining -= len(cat_results)

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"[bible] Batch complete!")
    print(f"[bible] Produced: {len(results)} video(s)")
    for r in results:
        print(f"  ✅ {r}")
    print(f"{'=' * 60}\n")

    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
