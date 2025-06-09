# 🚀 Chatterbox-TTS-Extended — Features & Technical Explanations

Chatterbox-TTS-Extended is a *highly advanced*, power-user interface for batch and single text-to-speech (TTS) generation. It extends [Chatterbox-TTS](https://github.com/resemble-ai/chatterbox) with rich support for **multi-file input, candidate selection, artifact reduction, audio validation, auto-processing, parallelism, and workflow automation**. Every option from the script is exposed—making it one of the most customizable TTS pipelines available.

---

## 📋 Table of Contents

- [Text Input & File Handling](#text-input--file-handling)
- [Reference Audio](#reference-audio)
- [Voice/Emotion/Synthesis Controls](#voiceemotionsynthesis-controls)
- [Batching & Chunking Features](#batching--chunking-features)
- [Sound Word Replacement & Removal](#sound-word-replacement--removal)
- [Candidate Generation & Validation Logic](#candidate-generation--validation-logic)
- [Audio Post-Processing](#audio-post-processing)
- [Export & Output Options](#export--output-options)
- [Whisper Sync & Validation](#whisper-sync--validation)
- [Parallel Processing & Performance](#parallel-processing--performance)
- [Persistent Settings](#persistent-settings)
- [Tips & Troubleshooting](#tips--troubleshooting)
- [Installation](#-installation)

---
### **Feature Coverage Table**

| Feature                           | UI Exposed? | Script Logic   |
|------------------------------------|-------------|---------------|
| Text input (box + multi-file)      | ✔           | Yes           |
| Reference audio                    | ✔           | Yes           |
| Separate/merge file output         | ✔           | Yes           |
| Emotion, CFG, temperature, seed    | ✔           | Yes           |
| Batch/smart-append                 | ✔           | Yes           |
| Sound word remove/replace          | ✔           | Yes           |
| Auto-Editor post-processing        | ✔           | Yes           |
| FFmpeg normalization (EBU/peak)    | ✔           | Yes           |
| WAV/MP3/FLAC export                | ✔           | Yes           |
| Watermark disable                  | ✔           | Yes           |
| Candidates per chunk, retries      | ✔           | Yes           |
| Parallelism (workers)              | ✔           | Yes           |
| Whisper/faster-whisper backend     | ✔           | Yes           |
| Persistent settings (JSON)         | ✔           | Yes           |
| Help/Instructions                  | ✔ (Accordion) | Yes         |
| Audio preview & download           | ✔           | Yes           |

---

## Text Input & File Handling

### **Flexible Input**
- **Text Box:** Enter any text for speech synthesis directly into the interface.
- **Multi-File Upload:** Drag and drop **multiple `.txt` files**. All text is processed—either merged into a single file or as separate jobs.
- **Combine or Separate Output:** Choose whether to synthesize each text file to its own audio, or merge all inputs alphabetically into one audio file.

### **Input Preprocessing**
- **Automatic Lowercasing:** Ensures consistent pronunciation by normalizing to lowercase.
- **Whitespace Normalization:** Removes excessive spaces, newlines, and cleans the input.
- **Abbreviation Correction:** Automatically transforms e.g. `"J.R.R."` ➔ `"J R R"` for correct pronunciation of initials.

---

## Reference Audio

- **Voice Prompt:** Upload or record an audio file (microphone or file) as a reference. The model will attempt to mimic the style or identity of this voice.
- Handles missing or invalid reference audio gracefully (auto-detects and disables if not usable).

---

## Voice/Emotion/Synthesis Controls

### **Emotion Exaggeration**
- Controls how strongly emotional cues are emphasized in speech.
- Range: `0.0` (monotone/neutral), `1.0` (normal), up to `2.0` (extremely expressive).

### **Classifier-Free Guidance (CFG) Weight / Pace**
- **Controls both strictness and pacing.** Higher values make the model follow the input text more literally and **speak at a steadier, more deliberate pace** (less natural variation, slower/more monotone). Lower values allow the output to be more natural and expressive, often resulting in a slightly **quicker and more dynamic delivery**.
- Range: `0.1` (free, fast, expressive) to `1.0` (strict, steady, literal).
- (You may see this labeled as “CFG Weight / Pace” in some UIs.)

### **Temperature**
- Sets the level of randomness/creativity in speech patterns.
- Lower = deterministic and stable; higher = more variation and risk.

### **Random Seed**
- `0` = fully random on every run.
- Any other value = repeatable output for debugging and AB testing.

---

## Batching & Chunking Features

### **Sentence Batching**
- **Batch Mode:** Groups sentences up to 400 characters (customizable in code) for more natural phrasing and efficient parallel processing.
- **Smart-Append:** If not batching, intelligently combines short sentences so speech doesn’t sound choppy.

### **Chunking**
- Every batch or group of sentences (a "chunk") is processed individually, enabling fine control over validation and parallelism.

---

## Sound Word Replacement & Removal

### **Pre-Synthesis Replacement**
- Supply a list of "problematic" or unwanted words/phrases to remove or substitute before speech synthesis.
- **Format:**
  - Remove: `sss, ss, hmm`
  - Replace: `Baggins=>Gomberg`
- Handles possessives, quotes, and standalone word occurrences.

---

## Candidate Generation & Validation Logic

### **Multiple Generations**
- Choose how many complete, unique audio outputs to generate in one go ("takes" or "generations").
- Each generation gets a unique or incremented seed, ensuring variety.

### **Candidates Per Chunk**
- For each chunk, generate several candidates (variants).
- **Validation:** Each candidate is transcribed by Whisper (speech-to-text), and the best match (highest similarity) is selected for the final audio.

### **Max Attempts Per Candidate**
- Each candidate may be retried multiple times if it fails validation—minimizing artifacts or errors.

### **Bypass Whisper Checking**
- **OFF (default):** All candidates undergo Whisper validation.
- **ON:** Skips Whisper validation for speed—simply picks the shortest audio (can risk more artifacts).

### **Fallback When All Candidates Fail**
- If every candidate for a chunk fails Whisper validation, you can choose:
  - Use the one with the **longest transcript** (most text captured)
  - Or, use the **highest similarity score** (default).

---

## Audio Post-Processing

### **Auto-Editor Integration**
- [auto-editor](https://github.com/WyattBlue/auto-editor) is used to remove silence, stutters, and TTS artifacts.
- **Volume Threshold:** Minimum loudness (0.01–0.5) considered speech.
- **Margin:** Time buffer (seconds) before/after speech to avoid cutting off words.
- **Keep Original:** Option to save the raw WAV file in addition to the cleaned-up output.

### **FFmpeg Normalization**
- **EBU R128 Loudness Normalization:** Ensures target perceived loudness, true peak, and dynamic range.
- **Peak Normalization:** Simple normalization to avoid clipping.
- **All settings exposed:** Integrated Loudness (I), True Peak (TP), and Loudness Range (LRA).

---

## Export & Output Options

### **Export Format**
- Output audio as WAV, MP3 (320k high quality), FLAC—or all at once.
- All conversions are automatic, and temp files are cleaned up as needed.

### **Filename Convention**
- Output filenames include base name, timestamp, generation number, and random seed, for easy sorting and reproducibility.

### **Batch Export**
- If multiple text files and "separate files" is selected, all are processed in sequence with their own outputs.

---

## Whisper Sync & Validation

### **Flexible Whisper Backend**
- **OpenAI Whisper:** Classic, accurate but uses more VRAM.
- **faster-whisper (SYSTRAN):** Reimplementation, almost as accurate, much faster and dramatically less VRAM.
- User selects which backend and model size in the UI.

### **Whisper Model VRAM/Speed Info**
- Model size and VRAM requirements are shown, with both OpenAI and faster-whisper numbers.
- Automatically disables Whisper checking if not needed, or if bypass is enabled.

### **Whisper-Based Candidate Selection**
- Each chunk's candidates are transcribed, and the one that most closely matches the input text (via fuzzy match/sequence similarity) is chosen.
- If Whisper is bypassed, shortest duration candidate is chosen.

### **Advanced Fallbacks**
- If all candidates fail, can use longest transcript or highest fuzzy score per user preference.

---

## Parallel Processing & Performance

- **Full Parallelism:** Generate multiple chunks in parallel (configurable worker count, default 4).
- **Worker Control:** Users can reduce workers to 1 for sequential/low-VRAM processing or increase for maximum throughput on large GPUs.
- **Cleans up GPU memory after Whisper validation to avoid VRAM leaks.**

---

## Persistent Settings

- **JSON Settings Save/Load:** All UI choices are persisted to `settings.json` on every run/change, restoring your last-used configuration automatically.

---

## Tips & Troubleshooting

- **Out of VRAM or slow?**
  - Reduce parallel workers
  - Use a smaller or faster-whisper model
  - Lower the number of candidates
- **Artifacts/Errors?**
  - Increase candidates and retries
  - Tweak auto-editor margin/threshold
  - Refine sound word replacements
- **Audio choppy?**
  - Raise auto-editor margin or lower threshold
- **Reproducibility**
  - Use a non-zero random seed to repeat identical results

---

## 📝 Installation

I'm running this in a Python 3.10.6 virtual environment. I do not know what other versions work.

Clone the repo
`git clone https://github.com/petermg/Chatterbox-TTS-Extended`

Then install via
`pip install --force-reinstall -r requirements.txt`  

<sup> if for some reason the install doesn't run try doing </sup> `pip install --force-reinstall -r requirements.base.with.versions.txt`, 
<sup> and if that still doesn't work then do </sup> `pip install --force-reinstall -r requirements_frozen.txt`

Then run via
`python Chatter.py`

[FFMPEG](https://ffmpeg.org/download.html) is required. If you don't have it installed in your system path, put it in the same directory as the Chatter.py script.

---

## 📣 Feedback & Contributions

Open an issue or pull request with suggestions, bug reports, or improvements!

---
