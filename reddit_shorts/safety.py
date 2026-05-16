"""
reddit_shorts/safety.py — lightweight content safety checks.

This module blocks risky posts before narration/video generation by scanning
for blocked keywords in title/body/comments.
"""

import re
from dataclasses import dataclass

from reddit_shorts import config as cfg
from reddit_shorts.scraper import RedditPost


@dataclass
class SafetyDecision:
    blocked: bool
    matched_terms: list[str]


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _combined_post_text(post: RedditPost) -> str:
    parts = [post.title or "", post.body or ""]
    if post.top_comments:
        parts.extend(post.top_comments)
    return _normalise("\n".join(parts))


def _compact(text: str) -> str:
    """Lowercase and strip non-alphanumeric chars for obfuscation matching."""
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def evaluate_post(
    post: RedditPost,
    blocked_terms: list[str],
    blocked_patterns: list[str] | None = None,
) -> SafetyDecision:
    """Return a safety decision for a post based on keyword/pattern matches."""
    haystack = _combined_post_text(post)
    haystack_compact = _compact(haystack)
    matched: list[str] = []

    for term in blocked_terms:
        t = _normalise(term)
        if not t:
            continue
        t_compact = _compact(t)

        # Use word-boundary style matching for single words; substring for phrases.
        if " " in t or "-" in t:
            if t in haystack:
                matched.append(term)
        else:
            if re.search(rf"\b{re.escape(t)}\b", haystack):
                matched.append(term)

        # Obfuscation-resistant fallback: compare compacted strings.
        if t_compact and t_compact in haystack_compact:
            matched.append(term)

    patterns = blocked_patterns if blocked_patterns is not None else cfg.SAFETY_BLOCKED_REGEX_PATTERNS
    for pattern in patterns:
        p = (pattern or "").strip()
        if not p:
            continue
        try:
            if re.search(p, haystack, flags=re.IGNORECASE):
                matched.append(f"regex:{p}")
        except re.error:
            # Ignore invalid user-provided patterns instead of breaking runs.
            continue

    # Preserve order while removing duplicates.
    seen = set()
    unique = [m for m in matched if not (m in seen or seen.add(m))]
    return SafetyDecision(blocked=bool(unique), matched_terms=unique)
