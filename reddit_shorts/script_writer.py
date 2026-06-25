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

# ── TrueOffMyChest hook templates ───────────────────────────────────────────
# Emotional, confessional, vulnerable tone — grab attention through empathy.

_TOMC_HOOKS = [
    "They carried this secret for years. And when they finally told someone, everything changed.",
    "This confession has {upvotes:,} upvotes for a reason. It's genuinely heartbreaking.",
    "They needed to get this off their chest. And after hearing it, you'll understand why.",
    "Some stories stay with you. This is one of them. Listen closely.",
    "This person has been holding something in for way too long. Here's what happened.",
    "The weight of this secret was crushing them. Then they told Reddit. And wow.",
    "Grab a tissue. Because this confession? It's heavy. {upvotes:,} people felt it too.",
    "You know those moments where someone just needs to be heard? This is one of them.",
    "They never thought they'd tell anyone this. But here we are. And it's a lot.",
    "Sometimes the bravest thing you can do is just... say it out loud. They did.",
]

# ── TIFU hook templates ─────────────────────────────────────────────────────
# Comedic, light-hearted, embarrassing — hook through curiosity and humour.

_TIFU_HOOKS = [
    "Today they messed up. And by messed up, I mean EPICALLY. You have to hear this.",
    "{upvotes:,} people are laughing at this absolute disaster. And honestly? I get it.",
    "They thought it was a normal day. They were WRONG. So very, very wrong.",
    "This person made one tiny mistake. And the consequences? Absolutely hilarious.",
    "Some days you just shouldn't get out of bed. This was one of those days.",
    "The title says TIFU. But honestly? This is the funniest thing I've read all week.",
    "You know that feeling when you realize you've made a HUGE mistake? They felt it.",
    "This story starts with a simple decision and ends in absolute chaos. Settle in.",
    "They're never going to live this one down. {upvotes:,} people are making sure of it.",
    "I laughed so hard at this I almost cried. And you're about to understand why.",
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

# AITAH CTAs — verdict/judgment focused (preserved exactly as before)
_AITAH_CTAS = [
    "What do you think — were they in the right? Drop it in the comments. And follow for more stories like this.",
    "NTA or YTA? Let me know. And if you want more, follow — I post these every day.",
    "Let me know your verdict in the comments. And hit follow — new stories every single day.",
    "Tell me what you think below. And follow so you never miss one of these.",
    "Comment your verdict. Follow for daily Reddit stories. I'll see you in the next one.",
]

# TrueOffMyChest CTAs — empathetic, supportive tone
_TOMC_CTAS = [
    "If this story hit you the way it hit me, let them know in the comments. And follow for more.",
    "Some stories just need to be heard. Drop a supportive comment. And follow for more like this.",
    "What would you say to this person? Let me know below. And follow — new stories every day.",
    "If this resonated with you, you're not alone. Comment your thoughts and follow for more.",
    "Share your support in the comments. And follow so you never miss a story like this.",
]

# TIFU CTAs — playful, fun, engagement-focused
_TIFU_CTAS = [
    "What's the funniest thing YOU'VE ever done? Tell me in the comments. And follow for more.",
    "Rate this disaster from 1 to 10 in the comments. And follow — I post these every day.",
    "Have you ever messed up THIS badly? Let me know. And follow for daily laughs.",
    "Tell me your most embarrassing moment below. And follow so you never miss a story.",
    "Drop a laugh emoji if this made your day. Follow for more stories like this.",
]

# Generic fallback CTAs (used when subreddit has no custom templates)
_GENERIC_CTAS = [
    "What do you think? Drop it in the comments. And follow for more stories like this.",
    "Let me know your thoughts below. And if you want more, follow — I post these every day.",
    "Comment your take. And hit follow — new stories every single day.",
    "Tell me what you think. And follow so you never miss one of these.",
]


@dataclass
class NarrationScript:
    hook: str           # First 2–3 sentences — the attention grabber
    body: str           # Main story narration
    comment_section: str  # Top comments read aloud (may be empty)
    cta: str            # Final engagement prompt
    full_text: str      # Concatenated full narration for TTS


def _pick_hook(post: RedditPost) -> str:
    """Select a retention hook based on subreddit category and (for AITAH) flair."""
    upvotes = post.upvotes
    sub = (post.subreddit or "").lower()

    # ── AITAH: preserve existing flair-based hook selection EXACTLY ────────
    if sub in ("amitheasshole", "aitah", "aita"):
        flair = (post.flair or "").lower()
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
    # ── TrueOffMyChest: emotional / confessional hooks ────────────────────
    elif sub in ("trueoffmychest", "offmychest"):
        template = random.choice(_TOMC_HOOKS)
    # ── TIFU: comedic / embarrassing hooks ────────────────────────────────
    elif sub in ("tifu"):
        template = random.choice(_TIFU_HOOKS)
    # ── Unknown / future subreddits: generic hooks ─────────────────────────
    else:
        template = random.choice(_GENERIC_HOOKS)

    try:
        return template.format(upvotes=upvotes)
    except KeyError:
        return template


def _pick_cta(post: RedditPost) -> str:
    """Select a CTA based on subreddit category."""
    sub = (post.subreddit or "").lower()

    if sub in ("amitheasshole", "aitah", "aita"):
        return random.choice(_AITAH_CTAS)
    elif sub in ("trueoffmychest", "offmychest"):
        return random.choice(_TOMC_CTAS)
    elif sub in ("tifu"):
        return random.choice(_TIFU_CTAS)
    else:
        return random.choice(_GENERIC_CTAS)


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
    cta = _pick_cta(post)

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
