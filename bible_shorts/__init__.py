# bible_shorts — automated Bible Scripture → TikTok/Shorts pipeline
#
# Architecture:
#   Content layer:   content.py — verse database + category-driven selection
#   Script layer:    script_writer.py — Hook → Verse → Reflection → CTA
#   Visual layer:    bible_renderer.py — premium Scripture card (frosted glass etc)
#   Audio layer:     (reuses reddit_shorts.tts_narrator for ChatterboxTTS)
#   Background:      background.py — calming cinematic looping footage
#   Music:           music.py — background music + ducking
#   Mixing:          audio_mixer.py — voice + music + ambient blend
#   Composition:     (reuses reddit_shorts.video_composer for FFmpeg assembly)
#   Pipeline:        pipeline.py — orchestration
#
# The rendering engine (video_composer, tts_narrator, subtitle_gen, transcription)
# is shared with reddit_shorts via direct import. Bible-specific logic lives
# entirely within this package.
