import random
import numpy as np
import torch
import os
import re
import datetime
import torchaudio
import gradio as gr
import spaces
import subprocess
from pydub import AudioSegment
import ffmpeg
from chatterbox.src.chatterbox.tts import ChatterboxTTS

os.environ["CUDA_LAUNCH_BLOCKING"] = "1"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🚀 Running on device: {DEVICE}")

MODEL = None

def get_or_load_model():
    global MODEL
    if MODEL is None:
        print("Model not loaded, initializing...")
        MODEL = ChatterboxTTS.from_pretrained(DEVICE)
        if hasattr(MODEL, 'to') and str(MODEL.device) != DEVICE:
            MODEL.to(DEVICE)
        print(f"Model loaded on device: {getattr(MODEL, 'device', 'unknown')}")
    return MODEL

try:
    get_or_load_model()
except Exception as e:
    print(f"CRITICAL: Failed to load model. Error: {e}")

def set_seed(seed: int):
    torch.manual_seed(seed)
    if DEVICE == "cuda":
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    random.seed(seed)
    np.random.seed(seed)

def normalize_whitespace(text: str) -> str:
    return re.sub(r'\s{2,}', ' ', text.strip())

def replace_letter_period_sequences(text: str) -> str:
    def replacer(match):
        cleaned = match.group(0).rstrip('.')
        letters = cleaned.split('.')
        return ' '.join(letters)
    return re.sub(r'\b(?:[A-Za-z]\.){2,}', replacer, text)

def split_into_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]

def group_sentences(sentences, max_chars=300):
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        if not sentence:
            print(f"[DEBUG] Skipping empty sentence")
            continue
        sentence = sentence.strip()
        sentence_len = len(sentence)

        print(f"[DEBUG] Processing sentence: len={sentence_len}, content='{sentence[:80]}...'")

        if sentence_len > 500:
            print(f"[DEBUG] Truncating sentence from {sentence_len} to 500 chars")
            sentence = sentence[:500]
            sentence_len = 500

        if sentence_len > max_chars:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                print(f"[DEBUG] Finalized chunk: {' '.join(current_chunk)[:80]}...")
            chunks.append(sentence)
            print(f"[DEBUG] Added long sentence as chunk: {sentence[:80]}...")
            current_chunk = []
            current_length = 0
        elif current_length + sentence_len + (1 if current_chunk else 0) <= max_chars:
            current_chunk.append(sentence)
            current_length += sentence_len + (1 if current_chunk else 0)
            print(f"[DEBUG] Adding sentence to chunk: {sentence[:80]}...")
        else:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                print(f"[DEBUG] Finalized chunk: {' '.join(current_chunk)[:80]}...")
            current_chunk = [sentence]
            current_length = sentence_len
            print(f"[DEBUG] Starting new chunk with: {sentence[:80]}...")

    if current_chunk:
        chunks.append(" ".join(current_chunk))
        print(f"[DEBUG] Finalized final chunk: {' '.join(current_chunk)[:80]}...")

    print(f"[DEBUG] Total chunks created: {len(chunks)}")
    for i, chunk in enumerate(chunks):
        print(f"[DEBUG] Chunk {i}: len={len(chunk)}, content='{chunk[:80]}...'")

    return chunks

def smart_append_short_sentences(sentences, max_chars=300):
    new_groups = []
    i = 0
    while i < len(sentences):
        current = sentences[i].strip()
        if len(current) >= 20:
            new_groups.append(current)
            i += 1
        else:
            appended = False
            if i + 1 < len(sentences):
                next_sentence = sentences[i + 1].strip()
                if len(current + " " + next_sentence) <= max_chars:
                    new_groups.append(current + " " + next_sentence)
                    i += 2
                    appended = True
            if not appended and new_groups:
                if len(new_groups[-1] + " " + current) <= max_chars:
                    new_groups[-1] += " " + current
                    i += 1
                    appended = True
            if not appended:
                new_groups.append(current)
                i += 1
    return new_groups

def normalize_with_ffmpeg(input_wav, output_wav, method="ebu", i=-24, tp=-2, lra=7):
    if method == "ebu":
        loudnorm = f"loudnorm=I={i}:TP={tp}:LRA={lra}"
        (
            ffmpeg
            .input(input_wav)
            .output(output_wav, af=loudnorm)
            .overwrite_output()
            .run(quiet=True)
        )
    elif method == "peak":
        (
            ffmpeg
            .input(input_wav)
            .output(output_wav, af="dynaudnorm")
            .overwrite_output()
            .run(quiet=True)
        )
    else:
        raise ValueError("Unknown normalization method.")
    os.replace(output_wav, input_wav)

@spaces.GPU
def generate_batch_tts(
    text: str,
    text_file,
    audio_prompt_path_input,
    exaggeration_input: float,
    temperature_input: float,
    seed_num_input: int,
    cfgw_input: float,
    use_auto_editor: bool,
    ae_threshold: float,
    ae_margin: float,
    export_format: str,
    enable_batching: bool,
    to_lowercase: bool,
    normalize_spacing: bool,
    fix_dot_letters: bool,
    keep_original_wav: bool,
    smart_batch_short_sentences: bool,
    disable_watermark: bool,
    num_generations: int,
    normalize_audio: bool,
    normalize_method: str,
    normalize_level: float,
    normalize_tp: float,
    normalize_lra: float,  # <-- Added for LRA (for EBU only)
) -> str:
    model = get_or_load_model()

    if text_file is not None:
        with open(text_file.name, "r", encoding="utf-8") as f:
            text = f.read()

    if not text or len(text.strip()) == 0:
        raise ValueError("No text provided.")

    if to_lowercase:
        text = text.lower()
    if normalize_spacing:
        text = normalize_whitespace(text)
    if fix_dot_letters:
        text = replace_letter_period_sequences(text)

    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    for f in os.listdir("temp"):
        os.remove(os.path.join("temp", f))

    sentences = split_into_sentences(text)
    if enable_batching:
        sentence_groups = group_sentences(sentences, max_chars=300)
    elif smart_batch_short_sentences:
        sentence_groups = smart_append_short_sentences(sentences)
    else:
        sentence_groups = sentences

    output_paths = []
    for gen_index in range(num_generations):
        # Set a unique seed for each generation
        if seed_num_input == 0:
            this_seed = random.randint(1, 2**32 - 1)
        else:
            this_seed = int(seed_num_input) + gen_index
        set_seed(this_seed)

        waveform_list = []
        print(f"[DEBUG] Starting generation {gen_index+1}/{num_generations} with seed {this_seed}")
        for idx, sentence_group in enumerate(sentence_groups):
            if not sentence_group.strip():
                print(f"[DEBUG] Skipping empty sentence group at index {idx}")
                continue
            if len(sentence_group) > 1000:
                print(f"[DEBUG] Skipping suspiciously long sentence group at index {idx} (len={len(sentence_group)})")
                continue
            print(f"[DEBUG] Processing group {idx}: len={len(sentence_group)} preview='{sentence_group[:80]}...'")
            try:
                wav = model.generate(
                    sentence_group,
                    audio_prompt_path=audio_prompt_path_input,
                    exaggeration=min(exaggeration_input, 1.0),
                    temperature=temperature_input,
                    cfg_weight=cfgw_input,
                    apply_watermark=not disable_watermark
                )
                path = f"temp/gen{gen_index+1}_chunk_{idx:03d}.wav"
                torchaudio.save(path, wav, model.sr)
                waveform_list.append(wav)
            except Exception as e:
                print(f"[ERROR] Failed generating chunk {idx}: {e}")

        if not waveform_list:
            print(f"[WARNING] No audio generated in generation {gen_index+1}")
            continue

        full_audio = torch.cat(waveform_list, dim=1)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:-3]
        filename_suffix = f"{timestamp}_gen{gen_index+1}_seed{this_seed}"
        wav_output = f"output/audio_{filename_suffix}.wav"
        torchaudio.save(wav_output, full_audio, model.sr)

        # --- AUTO-EDITOR for artifact removal (if selected) ---
        if use_auto_editor:
            try:
                cleaned_output = wav_output.replace(".wav", "_cleaned.wav")
                if keep_original_wav:
                    backup_path = wav_output.replace(".wav", "_original.wav")
                    os.rename(wav_output, backup_path)
                    auto_editor_input = backup_path
                else:
                    auto_editor_input = wav_output

                auto_editor_cmd = [
                    "auto-editor",
                    "--edit", f"audio:threshold={ae_threshold}",
                    "--margin", f"{ae_margin}s",
                    "--export", "audio",
                    auto_editor_input,
                    "-o", cleaned_output
                ]

                subprocess.run(auto_editor_cmd, check=True)

                if os.path.exists(cleaned_output):
                    os.replace(cleaned_output, wav_output)
                    print(f"[DEBUG] Post-processed with auto-editor: {wav_output}")
            except Exception as e:
                print(f"[ERROR] Auto-editor post-processing failed: {e}")

        # --- ffmpeg-python for normalization (if selected) ---
        if normalize_audio:
            try:
                norm_temp = wav_output.replace(".wav", "_norm.wav")
                normalize_with_ffmpeg(
                    wav_output,
                    norm_temp,
                    method=normalize_method,
                    i=normalize_level,
                    tp=normalize_tp,
                    lra=normalize_lra,
                )
                print(f"[DEBUG] Post-processed with ffmpeg normalization: {wav_output}")
            except Exception as e:
                print(f"[ERROR] ffmpeg normalization failed: {e}")

        if export_format.lower() != "wav":
            audio = AudioSegment.from_wav(wav_output)
            final_output = wav_output.replace(".wav", f".{export_format}")
            export_kwargs = {"bitrate": "320k"} if export_format.lower() == "mp3" else {}
            audio.export(final_output, format=export_format, **export_kwargs)
            os.remove(wav_output)
            output_paths.append(final_output)
        else:
            output_paths.append(wav_output)

    return "\n".join(output_paths)

with gr.Blocks() as demo:
    gr.Markdown("# 🎧 Chatterbox TTS Extended")
    with gr.Row():
        with gr.Column():
            text_input = gr.Textbox(label="Text Input", lines=6)
            text_file_input = gr.File(label="Text File (.txt)", file_types=[".txt"])
            ref_audio_input = gr.Audio(sources=["upload", "microphone"], type="filepath", label="Reference Audio (Optional)")
            exaggeration_slider = gr.Slider(0.0, 2.0, value=0.5, step=0.1, label="Emotion Exaggeration")
            cfg_weight_slider = gr.Slider(0.0, 1.0, value=0.5, step=0.05, label="CFG Weight")
            temp_slider = gr.Slider(0.01, 5.0, value=0.8, step=0.05, label="Temperature")
            seed_input = gr.Number(value=0, label="Random Seed (0 for random)")
            enable_batching_checkbox = gr.Checkbox(label="Enable Sentence Batching (Max 300 chars)", value=False)
            smart_batch_short_sentences_checkbox = gr.Checkbox(label="Smart-append short sentences (if batching is off)", value=True)
            to_lowercase_checkbox = gr.Checkbox(label="Convert input text to lowercase", value=True)
            normalize_spacing_checkbox = gr.Checkbox(label="Normalize spacing (remove extra newlines and spaces)", value=True)
            fix_dot_letters_checkbox = gr.Checkbox(label="Convert 'J.R.R.' style input to 'J R R'", value=True)
            use_auto_editor_checkbox = gr.Checkbox(label="Post-process with Auto-Editor", value=False)
            keep_original_checkbox = gr.Checkbox(label="Keep original WAV (before Auto-Editor)", value=False)
            threshold_slider = gr.Slider(0.01, 0.5, value=0.02, step=0.01, label="Auto-Editor Volume Threshold")
            margin_slider = gr.Slider(0.0, 2.0, value=0.2, step=0.1, label="Auto-Editor Margin (seconds)")

            # === ffmpeg-python NORMALIZE OPTIONS ===
            normalize_audio_checkbox = gr.Checkbox(label="Normalize with ffmpeg (loudness/peak)", value=False)
            normalize_method_dropdown = gr.Dropdown(
                choices=["ebu", "peak"], value="ebu", label="Normalization Method"
            )
            normalize_level_slider = gr.Slider(
                -70, -5, value=-24, step=1, label="EBU Target Integrated Loudness (I, dB, ebu only)"
            )
            normalize_tp_slider = gr.Slider(
                -9, 0, value=-2, step=1, label="EBU True Peak (TP, dB, ebu only)"
            )
            normalize_lra_slider = gr.Slider(
                1, 50, value=7, step=1, label="EBU Loudness Range (LRA, ebu only)"
            )
            # ================

            export_format_dropdown = gr.Dropdown(choices=["wav", "mp3", "flac"], value="wav", label="Export Format")
            disable_watermark_checkbox = gr.Checkbox(label="Disable Perth Watermark", value=False)
            num_generations_input = gr.Number(value=1, precision=0, label="Number of Generations")
            run_button = gr.Button("Generate")
        with gr.Column():
            output_audio = gr.Textbox(label="Final Audio Files")

    run_button.click(
        fn=generate_batch_tts,
        inputs=[
            text_input, text_file_input, ref_audio_input,
            exaggeration_slider, temp_slider, seed_input, cfg_weight_slider,
            use_auto_editor_checkbox, threshold_slider, margin_slider,
            export_format_dropdown, enable_batching_checkbox,
            to_lowercase_checkbox, normalize_spacing_checkbox, fix_dot_letters_checkbox,
            keep_original_checkbox, smart_batch_short_sentences_checkbox,
            disable_watermark_checkbox, num_generations_input,
            # === ffmpeg-python NORMALIZE OPTIONS ===
            normalize_audio_checkbox,
            normalize_method_dropdown,
            normalize_level_slider,
            normalize_tp_slider,
            normalize_lra_slider,
            # ================
        ],
        outputs=output_audio
    )

    demo.launch()
