"""
reddit_shorts/script_writer.py — turn a raw Reddit post into a narration-ready script.

Psychology principles baked in:
  • Open-loop hook  — tease the twist/verdict FIRST so viewers can't leave
  • Pattern interrupt — start with the most surprising element
  • Social proof      — mention the upvote count and community verdict
  • Micro-cliffhangers — "but wait, it gets worse..." type transitions
  • CTA at the end   — follow + comment prompt
"""

import random
import re
import textwrap
from dataclasses import dataclass

from reddit_shorts.scraper import RedditPost


# ── Hook templates ─────────────────────────────────────────────────────────
# Designed to grab attention in the first 2–3 seconds. Reference the verdict
# so viewers must watch to understand WHY.

_NTA_HOOKS = [
    "The internet unanimously sided with them. But you need to hear the full story first.",
    "Over {upvotes:,} people said they were completely in the right. Here's what happened.",
    "Everyone agreed — not the asshole. But wait until you hear what they actually did.",
    "This one had the entire comment section losing their minds — and they were actually innocent.",
    "They thought they were wrong. The internet had other ideas. Settle in.",
    "Not. The. Asshole. But this situation? Absolutely wild. Let me tell you.",
    "With {upvotes:,} upvotes, this story broke the internet — and honestly? I get it.",
]

_YTA_HOOKS = [
    "The internet gave them a reality check they did NOT expect.",
    "Over {upvotes:,} people agreed — yeah, they were the asshole. But hear this out.",
    "This one is rough. And somehow... they didn't see it coming.",
    "The comment section was brutal. And honestly? Rightfully so.",
    "They went online looking for support. They got a mirror held up instead.",
    "Everyone agreed they were in the wrong. The story is even wilder than the verdict.",
]

_ESH_HOOKS = [
    "Nobody came out of this looking good. {upvotes:,} people agreed.",
    "The verdict? Everyone sucks here. And honestly — same.",
    "The internet said they were all wrong. Let me take you through why.",
]

_NAH_HOOKS = [
    "No villains here — just a situation that got messy. {upvotes:,} people felt it.",
    "Nobody was the bad guy. And somehow, that makes it even more heartbreaking.",
    "The internet ruled: no assholes. But the story? Genuinely emotional.",
]

_GENERIC_HOOKS = [
    "I had to pause everything to read this one. Just... hear me out.",
    "This story has been living in my head rent-free. Let me put it in yours.",
    "Sometimes you read something and you genuinely don't know what to think.",
    "The comment section was absolutely FERAL over this. And I understand why.",
    "I read this twice to make sure it was real. It is. Somehow.",
    "This popped up on Reddit and I've been thinking about it ever since.",
    "Okay. Deep breath. Because this one is a lot.",
    "Close your eyes... just kidding, you need to see this post. Listen though.",
]

# ── Micro-cliffhanger transitions (inserted mid-story for retention) ────────
_TRANSITIONS = [
    "And here's where it gets interesting.",
    "But wait — it gets so much worse.",
    "And then? Things escalated.",
    "Now, this is the part that got people talking.",
    "Okay, so at this point you might think that's bad. You'd be right. But there's more.",
    "And here is the part the comment section could not stop screaming about.",
]

# ── Comment intro phrases ───────────────────────────────────────────────────
_COMMENT_INTROS = [
    "And here's what the top comments had to say.",
    "The internet weighed in. Here are the top reactions.",
    "People in the comments were not holding back.",
    "Here's what people thought.",
]

# ── CTAs (call to action — last thing heard) ────────────────────────────────
_CTAS = [
    "What do you think — were they in the right? Drop it in the comments. And follow for more stories like this.",
    "NTA or YTA? Let me know. And if you want more, follow — I post these every day.",
    "Let me know your verdict in the comments. And hit follow — new stories every single day.",
    "Tell me what you think below. And follow so you never miss one of these.",
    "Comment your verdict. Follow for daily Reddit stories. I'll see you in the next one.",
]


@dataclass
class NarrationScript:
    hook: str           # First 2–3 sentences — the attention grabber
    body: str           # Main story narration
    comment_section: str  # Top comments read aloud (may be empty)
    cta: str            # Final engagement prompt
    full_text: str      # Concatenated full narration for TTS


def _pick_hook(post: RedditPost) -> str:
    flair = (post.flair or "").lower()
    upvotes = post.upvotes

    if "not the a-hole" in flair or "nta" in flair:
        template = random.choice(_NTA_HOOKS)
    elif "asshole" in flair and "not" not in flair:
        template = random.choice(_YTA_HOOKS)
    elif "everyone sucks" in flair or "esh" in flair:
        template = random.choice(_ESH_HOOKS)
    elif "no a-holes" in flair or "nah" in flair:
        template = random.choice(_NAH_HOOKS)
    else:
        template = random.choice(_GENERIC_HOOKS)

    try:
        return template.format(upvotes=upvotes)
    except KeyError:
        return template


def _insert_transition(text: str) -> str:
    """Insert a micro-cliffhanger roughly in the middle of the story."""
    # Find a paragraph break near the midpoint
    mid = len(text) // 2
    # Look for a newline within ±300 chars of midpoint
    search_start = max(0, mid - 300)
    search_end = min(len(text), mid + 300)
    chunk = text[search_start:search_end]
    nl_pos = chunk.rfind("\n\n")
    if nl_pos == -1:
        nl_pos = chunk.rfind(". ")
    if nl_pos != -1:
        insert_at = search_start + nl_pos + 2
        transition = "\n\n" + random.choice(_TRANSITIONS) + "\n\n"
        return text[:insert_at] + transition + text[insert_at:]
    return text


def _format_body(post: RedditPost) -> str:
    """Clean and lightly format the body for spoken narration."""
    body = post.body

    # Replace written-out formatting with spoken equivalents
    body = re.sub(r"\n{2,}", "\n\n", body)        # normalise paragraphs
    body = body.replace("AITA", "Am I the asshole")
    body = body.replace("WIBTA", "Would I be the asshole")
    body = body.replace("NTA", "not the asshole")
    body = body.replace("YTA", "you're the asshole")
    body = body.replace("ESH", "everyone sucks here")
    body = body.replace("NAH", "no assholes here")
    body = re.sub(r"\bIMO\b", "in my opinion", body)
    body = re.sub(r"\bIMHO\b", "in my honest opinion", body)
    body = re.sub(r"\bSO\b(?=\s)", "my partner", body)   # "SO" = Significant Other in AITA context
    body = re.sub(r"\bBF\b(?=\s)", "my boyfriend", body)
    body = re.sub(r"\bGF\b(?=\s)", "my girlfriend", body)
    body = re.sub(r"\bMIL\b(?=\s)", "my mother-in-law", body)
    body = re.sub(r"\bFIL\b(?=\s)", "my father-in-law", body)
    body = re.sub(r"\bSIL\b(?=\s)", "my sister-in-law", body)
    body = re.sub(r"\bBIL\b(?=\s)", "my brother-in-law", body)
    # Remove reddit username mentions (u/someone)
    body = re.sub(r"u/\w+", "someone", body)
    # Remove subreddit mentions
    body = re.sub(r"r/\w+", "the subreddit", body)
    # Remove markdown
    body = re.sub(r"\*+([^*]+)\*+", r"\1", body)
    body = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", body)
    body = re.sub(r"#+\s*", "", body)
    body = re.sub(r"`[^`]+`", "", body)
    # Normalise whitespace
    body = re.sub(r"[ \t]{2,}", " ", body)
    body = body.strip()
    return body


def _format_comments(comments: list[str]) -> str:
    if not comments:
        return ""
    intro = random.choice(_COMMENT_INTROS)
    lines = [intro + "\n"]
    for i, comment in enumerate(comments, 1):
        # Clean comment text
        c = re.sub(r"\*+([^*]+)\*+", r"\1", comment)
        c = c.replace("NTA", "not the asshole").replace("YTA", "you're the asshole")
        c = re.sub(r"[ \t]{2,}", " ", c).strip()
        lines.append(f'Comment {i}: "{c}"')
    return "\n\n".join(lines)


def generate_script(post: RedditPost) -> NarrationScript:
    """
    Build a full TikTok-optimised narration script for the given post.

    Structure (proven for Shorts retention):
    1. Hook       — verdict + teaser (3–5 s) — viewer can't leave without knowing why
    2. Attribution — "Posted to r/AmItheAsshole by u/..."
    3. Body       — the story, with a mid-story pattern interrupt
    4. Comments   — top community reactions (social proof)
    5. CTA        — follow + comment prompt
    """
    hook = _pick_hook(post)

    # Attribution line
    attribution = (
        f'This was posted to r/{post.subreddit} by user {post.author}, '
        f'with {post.upvotes:,} upvotes.'
    )

    # Story body
    body = _format_body(post)
    body = _insert_transition(body)

    # Comment section
    comment_text = _format_comments(post.top_comments)

    # CTA
    cta = random.choice(_CTAS)

    # Assemble full text for TTS (double newlines = audible pause between chunks)
    parts = [hook, "\n\n", attribution, "\n\n", body]
    if comment_text:
        parts += ["\n\n", comment_text]
    parts += ["\n\n", cta]

    full_text = "".join(parts)

    return NarrationScript(
        hook=hook,
        body=body,
        comment_section=comment_text,
        cta=cta,
        full_text=full_text,
    )
