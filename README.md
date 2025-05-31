# This is a modified version of [Chatterbox TTS](https://huggingface.co/ResembleAI/chatterbox).

This fork has the following modifications:
1. Accepts a text file as input.
2. Each sentence is processed separately, written to a temp folder, then after all sentences have been written, they are concatenated into a single audio file.
3. Outputs audio files to "outputs" folder.

Clone the repo
`git clone https://github.com/petermg/Chatterbox-TTS-Extended`

Then install via
`pip install -r requirements.txt`

Then run via
`python Chatter.py`
