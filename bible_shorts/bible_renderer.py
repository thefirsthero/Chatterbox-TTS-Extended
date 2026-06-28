"""
bible_shorts/bible_renderer.py — render a premium Scripture display card.

Design: Modern Bible app aesthetic
  • Semi-transparent frosted glass card with rounded corners
  • Elegant serif typography for Scripture
  • Warm cream / gold / deep blue palette
  • Book name + chapter + verse reference in gold
  • Subtle decorative gold divider
  • Soft drop shadow
  • Faint parchment texture at very low opacity (when available)

The card PNG is taller than the video viewport; the video_composer will
apply a gentle scrolling crop for a "reading along" feel.
"""

import textwrap
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

from bible_shorts import config as cfg
from bible_shorts.content import BibleVerse


# ── Font loading ────────────────────────────────────────────────────────────

def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font with graceful fallback."""
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        return ImageFont.load_default()


def _fonts():
    """Return cached font dict for Scripture card rendering."""
    return {
        "reference": _load_font(cfg.FONT_SANS_BOLD, cfg.FONT_SIZE_REFERENCE),
        "verse":     _load_font(cfg.FONT_SERIF, cfg.FONT_SIZE_VERSE),
        "reflection": _load_font(cfg.FONT_SERIF, cfg.FONT_SIZE_REFLECTION),
        "hook":      _load_font(cfg.FONT_SANS_BOLD, cfg.FONT_SIZE_HOOK),
        "branding":  _load_font(cfg.FONT_SANS, cfg.FONT_SIZE_BRANDING),
        "divider":   _load_font(cfg.FONT_SERIF, 22),
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
    line_spacing: int = 8,
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
    """Draw a rounded rectangle. Uses PIL's native rounded_rectangle if available."""
    if hasattr(draw, "rounded_rectangle"):
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=outline_width)
    else:
        # Fallback: draw regular rect with small corner circles
        draw.rectangle(xy, fill=fill, outline=outline, width=outline_width)


def _create_frosted_glass_bg(
    width: int,
    height: int,
) -> Image.Image:
    """Create a frosted glass background with warm gradient and subtle noise.

    Returns an RGBA image ready for compositing.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Warm cream-to-soft gradient
    for y in range(height):
        ratio = y / max(1, height)
        r = int(cfg.CARD_GRADIENT_TOP[0] + (cfg.CARD_GRADIENT_BOTTOM[0] - cfg.CARD_GRADIENT_TOP[0]) * ratio)
        g = int(cfg.CARD_GRADIENT_TOP[1] + (cfg.CARD_GRADIENT_BOTTOM[1] - cfg.CARD_GRADIENT_TOP[1]) * ratio)
        b = int(cfg.CARD_GRADIENT_TOP[2] + (cfg.CARD_GRADIENT_BOTTOM[2] - cfg.CARD_GRADIENT_TOP[2]) * ratio)
        a = int(cfg.CARD_GRADIENT_TOP[3] + (cfg.CARD_GRADIENT_BOTTOM[3] - cfg.CARD_GRADIENT_TOP[3]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, a))

    # Subtle noise for frosted glass effect
    import random as _random
    _rng = _random.Random(42)
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            noise = _rng.randint(-4, 4)
            pixels[x, y] = (
                max(0, min(255, r + noise)),
                max(0, min(255, g + noise)),
                max(0, min(255, b + noise)),
                a,
            )

    return img


def _draw_decorative_divider(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
) -> None:
    """Draw a subtle decorative gold divider line with small ornament."""
    color = cfg.DECORATIVE_LINE_COLOR
    # Thin line
    draw.line([(x, y), (x + width, y)], fill=color, width=1)

    # Small diamond/cross ornament in center
    cx = x + width // 2
    size = 4
    draw.line([(cx, y - size), (cx, y + size)], fill=color, width=1)
    draw.line([(cx - size, y), (cx + size, y)], fill=color, width=1)


def _draw_drop_shadow(
    base_img: Image.Image,
    shadow_offset: int = 6,
    shadow_blur: int = 12,
    shadow_opacity: int = 60,
) -> Image.Image:
    """Create a new image with the card content plus a soft drop shadow behind it."""
    shadow_w = base_img.width + shadow_blur * 2
    shadow_h = base_img.height + shadow_blur * 2

    # Shadow layer
    shadow = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    _draw_rounded_rect(
        shadow_draw,
        (shadow_blur, shadow_blur, shadow_w - shadow_blur, shadow_h - shadow_blur),
        cfg.CARD_CORNER_RADIUS + shadow_blur,
        fill=(0, 0, 0, shadow_opacity),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur))

    # Composite: shadow then card on top
    result = Image.new("RGBA", (shadow_w, shadow_h), (0, 0, 0, 0))
    result.paste(shadow, (0, 0), shadow)
    result.paste(base_img, (shadow_blur - shadow_offset, shadow_blur - shadow_offset), base_img)

    return result


# ── Main card rendering ─────────────────────────────────────────────────────

def render_scripture_card(
    verse: BibleVerse,
    output_path: Path,
    reflection: Optional[str] = None,
    card_width: int = cfg.CARD_WIDTH,
) -> int:
    """Render a premium Scripture display card as a PNG.

    Parameters
    ----------
    verse : BibleVerse
        The verse to display.
    output_path : Path
        Where to save the PNG.
    reflection : str, optional
        A reflection text to include below the verse.
    card_width : int
        Width of the card in pixels (height grows with content).

    Returns
    -------
    int
        Total card height in pixels (so the compositor knows scroll distance).
    """
    fonts = _fonts()
    pad_h = cfg.CARD_PADDING_H
    pad_v = cfg.CARD_PADDING_V
    inner_w = card_width - pad_h * 2

    # ── Measure content heights ─────────────────────────────────────────
    draw_temp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))

    # Reference line: "Psalm 23:1"
    ref_text = verse.reference
    ref_h = _text_height(draw_temp, ref_text, fonts["reference"])

    # Verse text (multiline)
    verse_lines, verse_h = _multiline_height(
        draw_temp, verse.text, fonts["verse"], inner_w,
        line_spacing=10,
    )
    # If verse is very short, still give it minimum space
    verse_h = max(verse_h, 40)

    # Reflection text (multiline, if provided)
    ref_lines: list[str] = []
    refl_h = 0
    if reflection:
        ref_lines, refl_h = _multiline_height(
            draw_temp, reflection, fonts["reflection"], inner_w,
            line_spacing=8,
        )

    # Divider space
    divider_space = 30  # spacing + line

    # Translation badge
    translation_text = verse.translation
    translation_h = _text_height(draw_temp, translation_text, fonts["branding"])

    # ── Calculate total card height ─────────────────────────────────────
    content_h = (
        pad_v                     # top padding
        + ref_h                   # reference
        + 14                      # gap
        + divider_space           # decorative divider
        + 18                      # gap
        + verse_h                 # Scripture text
        + (18 + refl_h if reflection else 0)  # reflection
        + 20                      # gap
        + translation_h           # translation
        + pad_v                   # bottom padding
    )

    card_height = content_h

    # ── Build the card ──────────────────────────────────────────────────
    # Create frosted glass background
    card_img = _create_frosted_glass_bg(card_width, card_height)

    # Draw rounded rectangle border
    border_draw = ImageDraw.Draw(card_img)
    _draw_rounded_rect(
        border_draw,
        (0, 0, card_width - 1, card_height - 1),
        cfg.CARD_CORNER_RADIUS,
        fill=None,
        outline=cfg.CARD_CARD_BORDER if hasattr(cfg, 'CARD_CARD_BORDER') else cfg.DECORATIVE_LINE_COLOR,
        outline_width=1,
    )

    # Create layer for text
    text_layer = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)

    y = pad_v

    # ── Reference (Book Chapter:Verse) ──────────────────────────────────
    _draw_rounded_rect(
        draw,
        (pad_h, y - 2, pad_h + int(draw.textlength(ref_text, font=fonts["reference"])) + 16, y + ref_h + 4),
        radius=8,
        fill=(*cfg.COLOR_GOLD_ACCENT, 25),
    )
    draw.text(
        (pad_h + 8, y),
        ref_text,
        font=fonts["reference"],
        fill=cfg.COLOR_TEXT_REFERENCE,
    )
    y += ref_h + 14

    # ── Decorative divider ──────────────────────────────────────────────
    _draw_decorative_divider(draw, pad_h + 20, y + 8, inner_w - 40)
    y += divider_space

    # ── Scripture text ──────────────────────────────────────────────────
    for line in verse_lines:
        draw.text((pad_h, y), line, font=fonts["verse"], fill=cfg.COLOR_TEXT_VERSE)
        y += _text_height(draw, line, fonts["verse"]) + 10

    # ── Reflection ──────────────────────────────────────────────────────
    if reflection and ref_lines:
        y += 8
        for line in ref_lines:
            draw.text((pad_h, y), line, font=fonts["reflection"],
                      fill=cfg.COLOR_TEXT_SECONDARY)
            y += _text_height(draw, line, fonts["reflection"]) + 8

    # ── Translation badge ───────────────────────────────────────────────
    y += 4
    badge_text = translation_text
    badge_w = int(draw.textlength(badge_text, font=fonts["branding"])) + 16
    badge_h = translation_h + 8
    _draw_rounded_rect(
        draw,
        (pad_h, y, pad_h + badge_w, y + badge_h),
        radius=6,
        fill=(*cfg.COLOR_SOFT_GREEN_LIGHT, 180),
    )
    draw.text(
        (pad_h + 8, y + 4),
        badge_text,
        font=fonts["branding"],
        fill=cfg.COLOR_SOFT_GREEN,
    )

    # ── Composite text onto card ────────────────────────────────────────
    card_img = Image.alpha_composite(card_img, text_layer)

    # ── Apply drop shadow ───────────────────────────────────────────────
    final_img = _draw_drop_shadow(
        card_img,
        shadow_offset=4,
        shadow_blur=10,
        shadow_opacity=50,
    )

    # ── Save ────────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(str(output_path), "PNG")

    return card_height


def render_hook_overlay(
    hook_text: str,
    output_path: Path,
    width: int = cfg.VIDEO_WIDTH,
    height: int = cfg.VIDEO_HEIGHT,
) -> Path:
    """Render a full-screen hook overlay with warm, elegant typography.

    This is displayed for the first ~3 seconds before the Scripture card
    fades in. Design: centered text on a transparent background with a
    subtle warm glow.
    """
    fonts = _fonts()
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Warm semi-transparent overlay at bottom-center for readability
    overlay_h = 200
    overlay_y = height - overlay_h - 160
    for y in range(overlay_h):
        alpha = int(80 * (1.0 - abs((y - overlay_h / 2) / (overlay_h / 2))))
        draw.line(
            [(0, overlay_y + y), (width, overlay_y + y)],
            fill=(*cfg.COLOR_DEEP_BLUE, alpha),
        )

    # Hook text — centered
    max_text_w = width - 120
    lines, _ = _multiline_height(draw, hook_text, fonts["hook"], max_text_w)
    line_h = _text_height(draw, "Ag", fonts["hook"])
    total_text_h = len(lines) * (line_h + 8)
    text_y = height // 2 - total_text_h // 2 - 60

    # Draw subtle glow behind text
    glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    for line in lines:
        lw = int(glow_draw.textlength(line, font=fonts["hook"]))
        lx = (width - lw) // 2
        glow_draw.text(
            (lx + 2, text_y + 2),
            line,
            font=fonts["hook"],
            fill=(*cfg.COLOR_GOLD_LIGHT, 40),
        )
        text_y += line_h + 8
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(6))
    img = Image.alpha_composite(img, glow_layer)

    # Draw actual text
    text_y = height // 2 - total_text_h // 2 - 60
    for line in lines:
        lw = int(draw.textlength(line, font=fonts["hook"]))
        lx = (width - lw) // 2
        # Shadow
        draw.text(
            (lx + 3, text_y + 3),
            line,
            font=fonts["hook"],
            fill=(0, 0, 0, 120),
        )
        # Main text: warm cream white
        draw.text(
            (lx, text_y),
            line,
            font=fonts["hook"],
            fill=(*cfg.COLOR_TEXT_LIGHT, 240),
        )
        text_y += line_h + 8

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path


def render_closing_screen(
    outro_text: str,
    output_path: Path,
    width: int = cfg.VIDEO_WIDTH,
    height: int = cfg.VIDEO_HEIGHT,
) -> Path:
    """Render a calm closing screen / outro card.

    Features:
    - Warm dark gradient background
    - Centered text with gold accent
    - Subtle branding
    - Gentle fade-ready
    """
    fonts = _fonts()

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Warm dark gradient background
    for y in range(height):
        ratio = y / max(1, height)
        r = int(cfg.COLOR_DEEP_BLUE[0] + (30 - cfg.COLOR_DEEP_BLUE[0]) * ratio)
        g = int(cfg.COLOR_DEEP_BLUE[1] + (25 - cfg.COLOR_DEEP_BLUE[1]) * ratio)
        b = int(cfg.COLOR_DEEP_BLUE[2] + (40 - cfg.COLOR_DEEP_BLUE[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 230))

    # Soft gold glow in center
    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    cx, cy = width // 2, height // 2 - 40
    for r in range(120, 0, -1):
        alpha = int(15 * (r / 120))
        glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                          fill=(*cfg.COLOR_GOLD_ACCENT, alpha))
    img = Image.alpha_composite(img, glow)

    # Outro text
    outro_font = _load_font(cfg.FONT_SERIF, 42)
    lw = int(draw.textlength(outro_text, font=outro_font))
    lx = (width - lw) // 2
    draw.text((lx + 2, cy + 2), outro_text, font=outro_font, fill=(0, 0, 0, 100))
    draw.text((lx, cy), outro_text, font=outro_font, fill=(*cfg.COLOR_GOLD_LIGHT, 220))

    # Small branding at bottom
    brand_font = _load_font(cfg.FONT_SANS, 18)
    brand = cfg.WATERMARK_TEXT
    bw = int(draw.textlength(brand, font=brand_font))
    bx = (width - bw) // 2
    draw.text((bx, height - 60), brand, font=brand_font,
              fill=(255, 255, 255, int(255 * cfg.WATERMARK_OPACITY)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), "PNG")
    return output_path
