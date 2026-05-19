"""
reddit_shorts/post_renderer.py — render a Reddit post as a dark-mode PNG card.

The card image is taller than the video viewport; the video_composer will
apply a scrolling crop so the card pans upward as the narrator speaks.

Design: Reddit dark mode palette, clean typography, flair badge, upvote row.
"""

import textwrap
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from reddit_shorts import config as cfg
from reddit_shorts.scraper import RedditPost


# ── Font loading ────────────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        # PIL built-in fallback (fixed size, not ideal but won't crash)
        return ImageFont.load_default()


def _fonts():
    """Return cached font dict. Call once per render."""
    return {
        "sub_name":    _load_font(cfg.FONT_BOLD,    28),   # r/subreddit name
        "meta":        _load_font(cfg.FONT_REGULAR,  20),   # posted by / date
        "flair":       _load_font(cfg.FONT_BOLD,     21),   # flair badge
        "title":       _load_font(cfg.FONT_BOLD,     34),   # post title
        "body":        _load_font(cfg.FONT_REGULAR,  25),   # body text
        "footer":      _load_font(cfg.FONT_REGULAR,  21),   # upvotes / comments
        "footer_bold": _load_font(cfg.FONT_BOLD,     21),
    }


# ── Drawing helpers ─────────────────────────────────────────────────────────

def _text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]


def _multiline_height(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    line_spacing: int = 6,
) -> Tuple[list[str], int]:
    """Wrap text and return (lines, total_height)."""
    avg_char_w = draw.textlength("a", font=font)
    chars_per_line = max(1, int(max_width / avg_char_w))
    lines = textwrap.wrap(text, width=chars_per_line, break_long_words=True)
    if not lines:
        lines = [""]
    lh = _text_height(draw, "Ag", font)
    total = len(lines) * (lh + line_spacing) - line_spacing
    return lines, total


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int, int, int],
    radius: int,
    fill: Tuple,
    outline: Optional[Tuple] = None,
    outline_width: int = 1,
) -> None:
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=outline_width)
    else:
        draw.rectangle(xy, fill=fill, outline=outline, width=outline_width)


def _draw_flair_badge(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    flair_text: str,
    font: ImageFont.FreeTypeFont,
) -> int:
    """Draw a coloured pill-shaped flair badge. Returns the width used."""
    color = cfg.FLAIR_DEFAULT_COLOR
    for key, val in cfg.FLAIR_COLORS.items():
        if key.lower() in flair_text.lower():
            color = val
            break

    pad_h, pad_v = 10, 5
    text_w = int(draw.textlength(flair_text, font=font))
    badge_w = text_w + 2 * pad_h
    badge_h = _text_height(draw, flair_text, font) + 2 * pad_v

    _draw_rounded_rect(
        draw,
        (x, y, x + badge_w, y + badge_h),
        radius=badge_h // 2,
        fill=(*color, 255),
    )
    draw.text((x + pad_h, y + pad_v), flair_text, font=font, fill=cfg.COLOR_WHITE)
    return badge_w


def _format_count(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


# ── Main renderer ───────────────────────────────────────────────────────────

def render_post_card(post: RedditPost, output_path: Path) -> int:
    """
    Render the Reddit post as a dark-mode card PNG and save it.

    Returns the card height in pixels (needed by video_composer for scroll math).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    W = cfg.CARD_WIDTH
    P = cfg.CARD_PADDING          # inner padding
    content_w = W - 2 * P

    # ── First pass: measure all sections to compute total card height ───────
    # Use a small scratch image to measure text
    scratch = Image.new("RGBA", (W, 100), cfg.COLOR_CARD)
    draw = ImageDraw.Draw(scratch)
    fonts = _fonts()

    # Header: subreddit name row
    header_h = 34   # subreddit name
    header_h += 10  # gap

    # Flair badge (if present)
    flair_h = 0
    if post.flair:
        flair_h = 36 + 10   # badge height + gap

    # Meta: "Posted by u/..."
    meta_h = _text_height(draw, "Ag", fonts["meta"]) + 12

    # Title
    title_lines, title_h = _multiline_height(draw, post.title, fonts["title"], content_w, line_spacing=8)
    title_h += 16  # gap below

    # Separator
    sep_h = 2 + 14

    # Body
    body_lines, body_h = _multiline_height(draw, post.body, fonts["body"], content_w, line_spacing=7)
    body_h += 20  # gap

    # Footer: upvotes / comments
    footer_h = 30 + 16

    # Total height
    total_h = (
        P                          # top padding
        + header_h
        + flair_h
        + meta_h
        + title_h
        + sep_h
        + body_h
        + footer_h
        + P                        # bottom padding
    )
    # Avoid forcing the card to viewport height; that creates large empty blocks
    # on shorter posts and flattens visual pacing.
    total_h = max(total_h, 860)

    # ── Second pass: draw everything ─────────────────────────────────────────
    img = Image.new("RGBA", (W, total_h), cfg.COLOR_CARD)
    draw = ImageDraw.Draw(img)

    # Card outer border
    _draw_rounded_rect(
        draw,
        (0, 0, W - 1, total_h - 1),
        radius=cfg.CARD_CORNER_RADIUS,
        fill=cfg.COLOR_CARD,
        outline=cfg.COLOR_BORDER,
        outline_width=2,
    )

    cy = P  # current y cursor

    # ── Subreddit name ────────────────────────────────────────────────────
    sub_text = f"r/{post.subreddit}"
    draw.text((P, cy), sub_text, font=fonts["sub_name"], fill=cfg.COLOR_ACCENT)
    cy += _text_height(draw, sub_text, fonts["sub_name"]) + 10

    # ── Flair badge ───────────────────────────────────────────────────────
    if post.flair:
        badge_w = _draw_flair_badge(draw, P, cy, post.flair, fonts["flair"])
        cy += 36 + 10

    # ── Meta line: posted by ─────────────────────────────────────────────
    meta_text = f"Posted by u/{post.author}  ·  {_format_count(post.upvotes)} upvotes"
    draw.text((P, cy), meta_text, font=fonts["meta"], fill=cfg.COLOR_META)
    cy += _text_height(draw, meta_text, fonts["meta"]) + 12

    # ── Title ─────────────────────────────────────────────────────────────
    lh_title = _text_height(draw, "Ag", fonts["title"]) + 8
    for line in title_lines:
        draw.text((P, cy), line, font=fonts["title"], fill=cfg.COLOR_TITLE)
        cy += lh_title
    cy += 16

    # ── Separator ─────────────────────────────────────────────────────────
    draw.rectangle((P, cy, W - P, cy + 1), fill=cfg.COLOR_BORDER)
    cy += 2 + 14

    # ── Body text ─────────────────────────────────────────────────────────
    lh_body = _text_height(draw, "Ag", fonts["body"]) + 7
    for line in body_lines:
        draw.text((P, cy), line, font=fonts["body"], fill=cfg.COLOR_BODY)
        cy += lh_body
    cy += 20

    # ── Footer: upvotes and comments ──────────────────────────────────────
    upvote_str = _format_count(post.upvotes)
    comment_str = _format_count(post.num_comments)

    # Upvote count
    draw.text((P, cy), "▲", font=fonts["footer_bold"], fill=cfg.COLOR_UPVOTE)
    arrow_w = int(draw.textlength("▲ ", font=fonts["footer_bold"]))
    draw.text((P + arrow_w, cy), upvote_str, font=fonts["footer_bold"], fill=cfg.COLOR_UPVOTE)

    up_w = arrow_w + int(draw.textlength(upvote_str, font=fonts["footer_bold"]))

    # Comment count
    gap = 28
    draw.text((P + up_w + gap, cy), "•", font=fonts["footer"], fill=cfg.COLOR_META)
    em_w = int(draw.textlength("• ", font=fonts["footer"]))
    draw.text((P + up_w + gap + em_w, cy), f"{comment_str} comments", font=fonts["footer"], fill=cfg.COLOR_META)

    # Paste the card onto a matching background
    final = img.convert("RGB")
    final.save(str(output_path), format="PNG", optimize=False)

    print(f"[renderer] Card saved: {output_path}  ({W}×{total_h})")
    return total_h


def render_hook_overlay(hook_text: str, output_path: Path) -> None:
    """
    Render a full-frame semi-transparent hook overlay shown for the first ~3 s.

    This sits on top of the blurred gameplay before the Reddit card appears.
    Saved as RGBA PNG (transparency preserved for FFmpeg overlay).
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark gradient background
    for y in range(H):
        alpha = int(180 * (1 - abs(y - H // 2) / (H // 2)))
        draw.line((0, y, W, y), fill=(0, 0, 0, alpha))

    # Wrap the hook text
    hook_font = _load_font(cfg.FONT_BOLD, 62)
    content_w = W - 120
    avg_char_w = draw.textlength("a", hook_font)
    chars_per_line = max(1, int(content_w / avg_char_w))
    lines = textwrap.wrap(hook_text, width=chars_per_line, break_long_words=True)

    lh = _text_height(draw, "Ag", hook_font) + 12
    block_h = len(lines) * lh
    start_y = (H - block_h) // 2

    for i, line in enumerate(lines):
        tw = int(draw.textlength(line, font=hook_font))
        x = (W - tw) // 2
        y = start_y + i * lh
        # Shadow
        draw.text((x + 3, y + 3), line, font=hook_font, fill=(0, 0, 0, 200))
        # Text
        draw.text((x, y), line, font=hook_font, fill=(255, 255, 255, 255))

    # Subreddit badge strip at top
    badge_font = _load_font(cfg.FONT_BOLD, 30)
    badge_text = f"r/{cfg.SUBREDDIT}  ·  ASMR"
    bw = int(draw.textlength(badge_text, font=badge_font))
    bx = (W - bw) // 2
    draw.text((bx + 2, 58), badge_text, font=badge_font, fill=(0, 0, 0, 180))
    draw.text((bx, 56), badge_text, font=badge_font, fill=(*cfg.COLOR_ACCENT, 255))

    img.save(str(output_path), format="PNG")
    print(f"[renderer] Hook overlay saved: {output_path}")
