import random
import numpy as np
import torch
import os
import re
import datetime
import torchaudio
import gradio as gr
import spaces
from chatterbox.src.chatterbox.tts import ChatterboxTTS

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"🚀 Running on device: {DEVICE}")

# Global model object
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

def split_into_sentences(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]

@spaces.GPU
def generate_batch_tts(
    text: str,
    text_file,
    audio_prompt_path_input,
    exaggeration_input: float,
    temperature_input: float,
    seed_num_input: int,
    cfgw_input: float,
) -> str:
    model = get_or_load_model()

    # Use file input if available
    if text_file is not None:
        with open(text_file.name, "r", encoding="utf-8") as f:
            text = f.read()

    if not text or len(text.strip()) == 0:
        raise ValueError("No text provided.")

    # Generate random seed if 0
    if seed_num_input == 0:
        seed_num_input = random.randint(1, 2**32 - 1)
    set_seed(int(seed_num_input))

    os.makedirs("temp", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    # Clear temp dir
    for f in os.listdir("temp"):
        os.remove(os.path.join("temp", f))

    sentences = split_into_sentences(text)
    waveform_list = []

    for idx, sentence in enumerate(sentences):
        if not sentence or len(sentence) < 2:
            continue
        if len(sentence) > 500:
            sentence = sentence[:500]
        try:
            wav = model.generate(
                sentence,
                audio_prompt_path=audio_prompt_path_input,
                exaggeration=min(exaggeration_input, 1.0),
                temperature=temperature_input,
                cfg_weight=cfgw_input
            )
            path = f"temp/chunk_{idx:03d}.wav"
            torchaudio.save(path, wav, model.sr)
            waveform_list.append(wav)
        except Exception as e:
            print(f"Error generating sentence {idx}: {e}")

    if not waveform_list:
        raise RuntimeError("No valid audio generated.")

    full_audio = torch.cat(waveform_list, dim=1)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")[:-3]
    final_output = f"output/audio_{timestamp}_seed{seed_num_input}.wav"
    torchaudio.save(final_output, full_audio, model.sr)
    return final_output

with gr.Blocks() as demo:
    gr.Markdown("# 🎙️ Chatterbox TTS Extended")
    gr.Markdown("Upload a `.txt` file or type your text. Each sentence will be processed individually and stitched together.")

    with gr.Row():
        with gr.Column():
            text_input = gr.Textbox(label="Text Input", lines=6, placeholder="Enter text here...")
            text_file_input = gr.File(label="Text File (.txt)", file_types=[".txt"])
            ref_audio_input = gr.Audio(
                sources=["upload", "microphone"],
                type="filepath",
                label="Reference Audio (Optional)"
            )
            exaggeration_slider = gr.Slider(0.0, 2.0, value=0.5, step=0.1, label="Emotion Exaggeration")
            cfg_weight_slider = gr.Slider(0.0, 1.0, value=0.5, step=0.05, label="CFG Weight")
            temp_slider = gr.Slider(0.05, 5.0, value=0.8, step=0.05, label="Temperature")
            seed_input = gr.Number(value=0, label="Random Seed (0 for random)")
            run_button = gr.Button("Generate")

        with gr.Column():
            output_audio = gr.Audio(label="Final Audio", type="filepath")

    run_button.click(
        fn=generate_batch_tts,
        inputs=[text_input, text_file_input, ref_audio_input, exaggeration_slider, temp_slider, seed_input, cfg_weight_slider],
        outputs=output_audio
    )

demo.launch()
