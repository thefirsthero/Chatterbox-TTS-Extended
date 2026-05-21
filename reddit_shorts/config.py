"""
reddit_shorts/config.py — central configuration for the Reddit Shorts pipeline.

All tunables live here so the rest of the code stays free of magic numbers.
"""

from pathlib import Path

# ── Root paths ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output" / "shorts"
GAMEPLAY_DIR = ROOT / "video_clips" / "raw"
PROCESSED_GAMEPLAY_DIR = ROOT / "video_clips" / "processed"
TEMP_DIR = ROOT / "temp" / "shorts"
VOICE_PROFILE = ROOT / "output" / "voice_profiles" / "ginny_ultrasoft_locked.pt"
DONE_POSTS_FILE = OUTPUT_DIR / "done_posts.txt"

# ── Reddit scraping ────────────────────────────────────────────────────────
SUBREDDIT = "AmItheAsshole"

# Only include posts that are popular, resolved, and substantial enough to narrate
POST_LIMIT_FETCH = 75          # How many hot/top posts to pull before filtering
MIN_UPVOTES = 2_000            # Minimum score
MIN_BODY_CHARS = 450           # Too short = boring short
MAX_BODY_CHARS = 2_800         # ~70–150 s of ASMR narration at ~110 WPM

# Only process posts with one of these resolved flairs (None = no filter)
FLAIR_WHITELIST = [
    "Not the A-hole",
    "Asshole",
    "Everyone Sucks",
    "No A-holes here",
]

# How many top comments to pull (read aloud at the end)
TOP_COMMENTS_COUNT = 3
MAX_COMMENT_CHARS = 220        # Trim comments longer than this

# ── Platform safety filters ───────────────────────────────────────────────
# Posts containing these terms are skipped before TTS/video generation.
# Keep terms lowercase; matching is case-insensitive.
SAFETY_BLOCKED_TERMS = [
    "suicide",
    "self-harm",
    "kill myself",
    "sexual assault",
    "rape",
    "molest",
    "minor",
    "underage",
    "incest",
    "bestiality",
    "graphic violence",
    "beheading",
    "terrorist",
]

# Regex patterns for evasive variants/obfuscated spellings.
# Keep these conservative to reduce false positives.
SAFETY_BLOCKED_REGEX_PATTERNS = [
    r"\bk\W*i\W*l\W*l\W*\s*m\W*y\W*s\W*e\W*l\W*f\b",
    r"\bs\W*e\W*l\W*f\W*[-_ ]?\W*h\W*a\W*r\W*m\b",
    r"\br\W*a\W*p\W*e\b",
    r"\bs\W*u\W*i\W*c\W*i\W*d\W*e\b",
    r"\bu\W*n\W*d\W*e\W*r\W*a\W*g\W*e\b",
]

# ── TTS / audio ───────────────────────────────────────────────────────────
TTS_EXAGGERATION = 0.22
TTS_TEMPERATURE = 0.36
TTS_CFG_WEIGHT = 0.3
TTS_SEED = 20260430
TTS_CANDIDATES_PER_CHUNK = 3   # Generate N candidates and keep the best
TTS_CANDIDATES_PER_CHUNK_CPU = 2
TTS_MIN_CHUNK_CHARS = 60
TTS_MAX_CHUNK_CHARS = 175
TTS_CPU_MAX_CHUNK_CHARS = 140
TTS_PAUSE_MIN_MS = 180         # Silence between chunks
TTS_PAUSE_MAX_MS = 420
TTS_CROSSFADE_MS = 280         # Longer crossfade hides chunk seams better
TTS_RESUME_PARTIALS = True

# Loudness normalisation (EBU R128)
# Shorts playback targets are typically much louder than long-form podcasts.
TTS_NORMALIZE_LUFS = -17.0
TTS_NORMALIZE_TP = -1.5
TTS_NORMALIZE_LRA = 9.0

# ── Video ──────────────────────────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_CRF = 24                 # H.264 quality (lower = better, larger file)
VIDEO_PRESET = "medium"
VIDEO_AUDIO_BITRATE = "128k"
GAMEPLAY_INTERMEDIATE_CRF = 30
GAMEPLAY_INTERMEDIATE_PRESET = "veryfast"

# Gameplay background
GAMEPLAY_BLUR_RADIUS = 5       # Soften the background without smearing details
GAMEPLAY_DARKEN = 0.60         # Multiplier applied to all colour channels (0–1)

# Reddit card geometry (pixels)
CARD_WIDTH = 900               # Narrower card gives more visible gameplay context
CARD_X = (VIDEO_WIDTH - CARD_WIDTH) // 2
CARD_PADDING = 34              # Inner padding on all sides
CARD_CORNER_RADIUS = 18

# Vertical bounds of the "viewport" through which the card is visible
CARD_VIEWPORT_TOP = 140        # Where the card starts appearing
CARD_VIEWPORT_BOTTOM = 1600    # Where the card stops (below = subtitle zone)
CARD_VIEWPORT_H = CARD_VIEWPORT_BOTTOM - CARD_VIEWPORT_TOP

# Scroll timing
HOOK_DURATION_S = 3.2          # How long the hook splash is displayed
CARD_SCROLL_START_S = 4.5      # Seconds before scrolling begins
CARD_SCROLL_END_MARGIN_S = 2.0 # Stop scrolling this many seconds before audio ends
CARD_IDLE_BOB_PX = 14          # Gentle motion when the card does not need to scroll
CARD_IDLE_SWAY_PX = 6
CARD_IDLE_PERIOD_S = 7.5

# Subtitle zone
SUBTITLE_ZONE_TOP = 1620       # Top of subtitle band
SUBTITLE_ZONE_BOTTOM = 1870    # Bottom of subtitle band (progress bar below)
SUBTITLE_FONT_SIZE = 62        # Large but less overpowering in 9:16
SUBTITLE_FONT_NAME = "Comic Sans MS"  # Bubbly fun font for short-form video
# ── Subtitle colours (ASS uses BGR hex: &HAABBGGRR, AA=00 = fully opaque) ──
# Yellow primary  : RGB(255,255,0)  → BGR 0x00FFFF  → &H0000FFFF
# Black outline   : RGB(0,0,0)      → BGR 0x000000  → &H00000000
# Dark back shadow: 50% opaque black                → &H80000000
SUBTITLE_PRIMARY_COLOR = "&H0000FFFF"      # yellow
SUBTITLE_OUTLINE_COLOR = "&H00000000"      # black
SUBTITLE_BACK_COLOR    = "&H80000000"      # semi-transparent black shadow
SUBTITLE_OUTLINE_SIZE  = 4.0              # thicker outline for TikTok look
SUBTITLE_SHADOW_SIZE   = 0.8
SUBTITLE_LINE_MARGIN_V = 230   # Keep captions higher above the progress bar
SUBTITLE_TRANSCRIBE_MODEL = "tiny"
SUBTITLE_TRANSCRIBE_BACKEND = "openai-whisper"
SUBTITLE_TRANSCRIBE_LANGUAGE = "en"

# Progress bar
PROGRESS_BAR_Y = 1892          # Top of the bar
PROGRESS_BAR_H = 12
PROGRESS_BAR_COLOR = "ff4500"  # Reddit orange

# Branding strip (very top of frame)
BRANDING_TEXT = f"r/{SUBREDDIT}  ·  ASMR Stories"
BRANDING_FONT_SIZE = 30
BRANDING_Y = 52

# ── Colours (Reddit dark mode palette) ────────────────────────────────────
COLOR_BG = (26, 26, 27)            # #1A1A1B outer background
COLOR_CARD = (39, 39, 41)          # #272729 card surface
COLOR_BORDER = (62, 62, 64)        # subtle border
COLOR_ACCENT = (255, 69, 0)        # #FF4500 Reddit orange
COLOR_TITLE = (215, 218, 220)      # almost-white title
COLOR_BODY = (155, 158, 160)       # muted body text
COLOR_META = (120, 124, 126)       # timestamps / "posted by"
COLOR_UPVOTE = (255, 69, 0)        # orange upvote arrow
COLOR_WHITE = (255, 255, 255)

# Flair badge backgrounds
FLAIR_COLORS = {
    "Not the A-hole": (0, 135, 90),       # green
    "Asshole": (198, 40, 40),             # red
    "Everyone Sucks": (210, 105, 30),     # orange-brown
    "No A-holes here": (30, 144, 255),    # blue
}
FLAIR_DEFAULT_COLOR = (100, 100, 110)

# ── Windows font paths (fallback to built-in PIL default) ─────────────────
import sys, os
if sys.platform == "win32":
    _FONT_ROOT = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    FONT_BOLD = str(_FONT_ROOT / "arialbd.ttf")
    FONT_REGULAR = str(_FONT_ROOT / "arial.ttf")
    FONT_ITALIC = str(_FONT_ROOT / "ariali.ttf")
elif sys.platform == "darwin":
    FONT_BOLD = "/Library/Fonts/Arial Bold.ttf"
    FONT_REGULAR = "/Library/Fonts/Arial.ttf"
    FONT_ITALIC = "/Library/Fonts/Arial Italic.ttf"
else:
    # Linux
    FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    FONT_ITALIC = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"

# ── yt-dlp gameplay download defaults ────────────────────────────────────
# These YouTube videos are marked CC-BY (Creative Commons Attribution).
# Always verify the licence on the video page before commercial use.
DEFAULT_GAMEPLAY_QUERIES = [
    "minecraft peaceful survival gameplay no commentary CC",
    "minecraft relaxing gameplay 1080p no copyright",
    "minecraft parkour smooth gameplay background 60fps",
]
GAMEPLAY_YTDLP_FORMAT = "bestvideo[height<=1080][ext=mp4]+bestaudio/best[height<=1080][ext=mp4]/best"
GAMEPLAY_MAX_DURATION_S = 600   # Don't download videos longer than 10 min
