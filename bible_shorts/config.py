"""
bible_shorts/config.py — central configuration for the Bible Shorts pipeline.

Warm, cinematic, premium design. Think Apple meets YouVersion.
All tunables live here so the rest of the code stays free of magic numbers.
"""

import sys
import os
from pathlib import Path

# ── Root paths ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUTPUT_DIR = ROOT / "output" / "shorts" / "bible"
FINAL_VIDEOS_DIR = ROOT / "output" / "videos" / "bible"
BACKGROUND_DIR = ROOT / "video_clips" / "cinematic"
MUSIC_DIR = ROOT / "audio" / "music"
AMBIENCE_DIR = ROOT / "audio" / "ambience"
VOICE_PROFILES_DIR = ROOT / "voice_profiles"
DONE_VERSES_FILE = OUTPUT_DIR / "done_verses.txt"
# Use the dedicated Bible voice profile if it exists; otherwise fall back
# to the existing Reddit shorts voice profile.
_BIBLE_PROFILE = VOICE_PROFILES_DIR / "bible_calm.pt"
_FALLBACK_PROFILE = VOICE_PROFILES_DIR / "ginny_ultrasoft_locked.pt"
BIBLE_VOICE_PROFILE = _BIBLE_PROFILE if _BIBLE_PROFILE.is_file() else (_FALLBACK_PROFILE if _FALLBACK_PROFILE.is_file() else None)
CACHE_DIR = ROOT / "output" / "cache" / "bible"

# ── Content selection ──────────────────────────────────────────────────────
# Categories map to verse groupings in content.py
DEFAULT_CATEGORIES = [
    "peace",
    "hope",
    "strength",
    "faith",
    "love",
    "wisdom",
    "encouragement",
    "forgiveness",
    "anxiety",
    "psalms",
    "proverbs",
    "gospel",
]

# Maximum verse length (characters) — keep it short for Shorts
MAX_VERSE_CHARS = 350
MIN_VERSE_CHARS = 40

# ── Script structure ───────────────────────────────────────────────────────
# All durations approximate; final pacing is determined by TTS
HOOK_MAX_CHARS = 120          # Hook should be 2-4 seconds spoken
REFLECTION_MAX_CHARS = 250    # AI reflection after the verse
CTA_MAX_CHARS = 100           # Soft call to action

# ── Video ──────────────────────────────────────────────────────────────────
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_CRF = 20                 # Higher quality for premium look
VIDEO_PRESET = "slower"        # Prioritise quality over speed
VIDEO_AUDIO_BITRATE = "192k"

# Maximum video duration (seconds)
MAX_VIDEO_DURATION_S = 90      # Bible Shorts should be shorter — ~45-75s ideal
MIN_VIDEO_DURATION_S = 25

# ── Background video ───────────────────────────────────────────────────────
# Cinematic looping footage — processing settings
BACKGROUND_BLUR_RADIUS = 3     # Very subtle blur — keep scenery visible
BACKGROUND_DARKEN = 0.50       # Gentle darken so text pops
BACKGROUND_INTERMEDIATE_CRF = 18
BACKGROUND_INTERMEDIATE_PRESET = "medium"

# yt-dlp search queries for cinematic footage (CC-licensed / royalty-free)
CINEMATIC_SEARCH_QUERIES = [
    "cinematic nature sunrise 4K no people slow pan CC",
    "peaceful forest stream 4K slow motion royalty free",
    "calming ocean waves sunset 4K no text cinematic",
    "gentle waterfall nature 4K slow pan copyright free",
    "mountains clouds timelapse peaceful 4K no people",
    "starlight night sky slow pan 4K royalty free",
    "golden hour fields wheat slow motion 4K cinematic",
    "candlelight warm gentle 4K closeup no text",
    "church interior stained glass peaceful 4K slow pan",
    "rolling hills sunlight 4K aerial slow cinematic",
    "olive trees gentle breeze 4K nature peaceful",
    "desert sunrise warm tones 4K cinematic slow pan",
    "soft rain window ambient 4K no people calming",
    "clouds drifting blue sky 4K slow motion peaceful",
]

BACKGROUND_MAX_DURATION_S = 900  # Download clips up to 15 min for looping

# ── Scripture card geometry ────────────────────────────────────────────────
CARD_WIDTH = 860                # Premium width with breathing room
CARD_X = (VIDEO_WIDTH - CARD_WIDTH) // 2
CARD_PADDING_H = 48             # Horizontal inner padding
CARD_PADDING_V = 40             # Vertical inner padding
CARD_CORNER_RADIUS = 28         # Smooth rounded corners

# Vertical position of the card viewport
CARD_VIEWPORT_TOP = 200
CARD_VIEWPORT_BOTTOM = 1580
CARD_VIEWPORT_H = CARD_VIEWPORT_BOTTOM - CARD_VIEWPORT_TOP

# Scroll / motion timing
HOOK_DURATION_S = 2.8           # Hook card display before verse card
CARD_SCROLL_START_S = 3.8
CARD_SCROLL_END_MARGIN_S = 2.5
CARD_IDLE_BOB_PX = 8            # Very subtle idle motion
CARD_IDLE_SWAY_PX = 3
CARD_IDLE_PERIOD_S = 9.0

# ── Subtitle zone ──────────────────────────────────────────────────────────
SUBTITLE_ZONE_TOP = 1620
SUBTITLE_ZONE_BOTTOM = 1870
SUBTITLE_FONT_SIZE = 64         # Large, readable
SUBTITLE_FONT_NAME = "Arial"    # Clean sans-serif

# Bible subtitle colours (ASS format: &HAABBGGRR)
# Warm white primary with dark outline
SUBTITLE_PRIMARY_COLOR = "&H00F5F0E6"     # warm cream
SUBTITLE_OUTLINE_COLOR = "&H001A1A2E"     # deep navy outline
SUBTITLE_BACK_COLOR = "&H60000000"        # semi-transparent black shadow
SUBTITLE_OUTLINE_SIZE = 3.5
SUBTITLE_SHADOW_SIZE = 0.6
SUBTITLE_LINE_MARGIN_V = 200

# Word highlighting for key theological terms
HIGHLIGHT_COLOR = "&H00B4D4FF"            # warm gold
HIGHLIGHT_WORDS = [
    "LORD", "Lord", "God", "Jesus", "Christ", "Spirit",
    "grace", "mercy", "love", "peace", "hope", "faith",
    "salvation", "righteousness", "glory", "eternal",
    "goodness", "faithfulness", "strength", "refuge",
    "shepherd", "father", "savior", "redeemer",
    "holy", "blessed", "amen", "hallelujah",
]

SUBTITLE_TRANSCRIBE_MODEL = "tiny"
SUBTITLE_TRANSCRIBE_BACKEND = "openai-whisper"
SUBTITLE_TRANSCRIBE_LANGUAGE = "en"

# ── Progress bar ───────────────────────────────────────────────────────────
PROGRESS_BAR_Y = 1895
PROGRESS_BAR_H = 8
PROGRESS_BAR_COLOR = "D4AF37"   # Gold instead of Reddit orange

# ── Branding ───────────────────────────────────────────────────────────────
BRANDING_TEXT = "Daily Scripture  ·  Bible Shorts"
BRANDING_FONT_SIZE = 26
BRANDING_Y = 48
WATERMARK_TEXT = "Bible Shorts"
WATERMARK_OPACITY = 0.35

# ── Colours (Warm premium palette) ─────────────────────────────────────────
# Card: frosted glass over warm neutrals
COLOR_BG_CREAM = (245, 240, 230)        # #F5F0E6 warm cream
COLOR_BG_SOFT = (250, 247, 240)         # slightly lighter
COLOR_CARD_SURFACE = (255, 252, 245, 200)  # frosted glass — very light with alpha
COLOR_CARD_BORDER = (210, 190, 150, 80)    # subtle gold-tinted border
COLOR_GOLD_ACCENT = (212, 175, 55)       # #D4AF37 gold
COLOR_GOLD_LIGHT = (232, 210, 130)       # lighter gold
COLOR_DEEP_BLUE = (26, 26, 46)           # #1A1A2E deep navy
COLOR_DEEP_BLUE_LIGHT = (40, 40, 70)     # slightly lighter navy
COLOR_TEXT_PRIMARY = (30, 30, 50)         # near-black with warm undertone
COLOR_TEXT_SECONDARY = (90, 85, 75)       # warm grey
COLOR_TEXT_VERSE = (35, 30, 45)           # deep warm dark for Scripture
COLOR_TEXT_REFERENCE = (140, 120, 80)     # gold-brown for book/chapter/verse
COLOR_TEXT_LIGHT = (240, 235, 225)        # light warm for dark backgrounds
COLOR_WHITE = (255, 255, 255)
COLOR_SOFT_GREEN = (120, 150, 120)       # muted sage
COLOR_SOFT_GREEN_LIGHT = (180, 200, 175)

# Gradient stops for card background (top to bottom)
CARD_GRADIENT_TOP = (255, 250, 240, 220)
CARD_GRADIENT_BOTTOM = (245, 238, 220, 200)

# Decorative elements
DECORATIVE_LINE_COLOR = (200, 175, 110, 120)  # subtle gold divider
DECORATIVE_ICON_COLOR = (190, 160, 100)       # cross / ornament color

# ── Typography ─────────────────────────────────────────────────────────────
# Elegant serif for Scripture, clean sans-serif for captions
if sys.platform == "win32":
    _FONT_ROOT = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    FONT_SERIF = str(_FONT_ROOT / "georgia.ttf")          # Elegant serif
    FONT_SERIF_BOLD = str(_FONT_ROOT / "georgiab.ttf")    # Bold serif
    FONT_SANS = str(_FONT_ROOT / "arial.ttf")              # Clean sans-serif
    FONT_SANS_BOLD = str(_FONT_ROOT / "arialbd.ttf")
    FONT_SANS_LIGHT = str(_FONT_ROOT / "arial.ttf")        # Fallback
elif sys.platform == "darwin":
    FONT_SERIF = "/Library/Fonts/Georgia.ttf"
    FONT_SERIF_BOLD = "/Library/Fonts/Georgia Bold.ttf"
    FONT_SANS = "/Library/Fonts/Arial.ttf"
    FONT_SANS_BOLD = "/Library/Fonts/Arial Bold.ttf"
    FONT_SANS_LIGHT = "/Library/Fonts/Arial.ttf"
else:
    FONT_SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
    FONT_SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
    FONT_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    FONT_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    FONT_SANS_LIGHT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Legacy aliases for shared renderer compatibility
FONT_BOLD = FONT_SERIF_BOLD
FONT_REGULAR = FONT_SERIF

# ── Font sizes for Scripture card ──────────────────────────────────────────
FONT_SIZE_REFERENCE = 28        # "Psalm 23:1" book/chapter/verse
FONT_SIZE_VERSE = 38            # The Scripture text itself
FONT_SIZE_HOOK = 34             # Hook text on overlay
FONT_SIZE_REFLECTION = 26       # Reflection text
FONT_SIZE_CTA = 28              # Call to action
FONT_SIZE_BRANDING = 20         # Small footer branding
FONT_SIZE_WATERMARK = 18

# ── TTS / Audio ────────────────────────────────────────────────────────────
# Bible voice: calm, trustworthy, warm, reflective
# Slightly slower pacing than Reddit videos
TTS_EXAGGERATION = 0.08         # Less emotion variation — peaceful
TTS_TEMPERATURE = 0.22          # Lower = more stable, consistent
TTS_CFG_WEIGHT = 0.35
TTS_SEED = 20260428
TTS_CANDIDATES_PER_CHUNK = 1
TTS_CANDIDATES_PER_CHUNK_CPU = 1
TTS_MIN_CHUNK_CHARS = 50
TTS_MAX_CHUNK_CHARS = 160       # Slightly smaller chunks for Bible pacing
TTS_CPU_MAX_CHUNK_CHARS = 200
TTS_PAUSE_MIN_MS = 60           # Longer pauses — reflective pace
TTS_PAUSE_MAX_MS = 180
TTS_CROSSFADE_MS = 200
TTS_RESUME_PARTIALS = True

# Bible narration pace — slower than Reddit (~95 wpm vs ~105 wpm)
BIBLE_WORDS_PER_MINUTE = 95

# Loudness normalisation
TTS_NORMALIZE_LUFS = -18.0      # Slightly quieter than Reddit for calm feel
TTS_NORMALIZE_TP = -1.5
TTS_NORMALIZE_LRA = 9.0

# Pause after meaningful sentences (seconds)
PAUSE_AFTER_VERSE_S = 0.8       # Breathe after Scripture
PAUSE_AFTER_REFLECTION_S = 0.6
PAUSE_AFTER_HOOK_S = 0.4

# ── Music ──────────────────────────────────────────────────────────────────
MUSIC_VOLUME_DB = -18.0         # Background music level (relative to voice)
MUSIC_DUCKING_DB = -8.0         # How much to reduce music during narration
MUSIC_DUCKING_ATTACK_S = 0.15   # Smooth ducking attack
MUSIC_DUCKING_RELEASE_S = 0.4   # Gentle release
MUSIC_FADE_IN_S = 1.5
MUSIC_FADE_OUT_S = 3.0
MUSIC_SWELL_PAUSE_DB = -6.0     # Music swells during pauses between sentences

# Ambient effects
AMBIENCE_VOLUME_DB = -30.0      # Extremely subtle
AMBIENCE_TYPES = [
    "soft_wind",
    "distant_birds",
    "gentle_rain",
    "church_ambience",
    "night_crickets",
    "flowing_water",
]

# ── Motion design ──────────────────────────────────────────────────────────
SLOW_ZOOM_SPEED = 1.003          # Very subtle Ken Burns zoom (scale factor per second)
PARALLAX_STRENGTH = 4            # Subtle parallax pixels
VIGNETTE_STRENGTH = 0.3          # Soft dark vignette
GLOW_RADIUS = 12                 # Gentle text glow radius

# ── Performance ────────────────────────────────────────────────────────────
MAX_PARALLEL_POSTS = 2           # Bible videos are higher quality — fewer parallel
BACKGROUND_ENABLE_CACHE = True
BACKGROUND_CACHE_DIR = ROOT / "video_clips" / "processed" / "cinematic"

# ── Outro / closing screen ─────────────────────────────────────────────────
CLOSING_SCREEN_DURATION_S = 2.5
OUTRO_MESSAGES = [
    "God bless you.",
    "Follow for daily Scripture.",
    "See you tomorrow.",
    "Peace be with you.",
    "Stay in the Word.",
]
