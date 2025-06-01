# This is a modified version of [Chatterbox TTS](https://huggingface.co/ResembleAI/chatterbox).

This fork has the following modifications:
1. Accepts text files as inputs.
2. Each sentence is processed separately, written to a temp folder, then after all sentences have been written, they are concatenated into a single audio file.
3. Outputs audio files to "outputs" folder.
NEW to this latest update and post:
4. Option to disable watermark.
5. Output format option (wav, mp3, flac).
6. Cut out extended silence or low parts (which is usually where artifacts hide) using auto-editor, with the option to keep the original un-cut wav file as well.
7. Sanitize input text, such as:
         Convert 'J.R.R.' style input to 'J R R'
         Convert input text to lowercase
         Normalize spacing (remove extra newlines and spaces)
8. Normalize with ffmpeg (loudness/peak) with two method available and configurable such as `ebu` and `peak`
9. Multi-generational output. This is useful if you're looking for a good seed. For example use a few sentences and tell it to output 25 generations using random seeds. Listen to each one to find the seed that you like the most-it saves the audio files with the seed number at the end.
10. Enable sentence batching up to 300 Characters.
11. Smart-append short sentences (for when above batching is disabled)
12. Added a method where after the temp audio chunk is generated, it is transcribed to validate if the words in the audio match the original text. If they do not match, the chunk is generated again. This is tried 3 times.
13. Added the method where user can set number of samples to generate per chunk (3 by default) and then pick the one that is shortest and passed the above transcription test.
14. Option to bypass the transcription test.
15. Bypass generating multiple samples per chunk by setting `Number of Candidates Per Sentence` to 1.

Clone the repo
`git clone https://github.com/petermg/Chatterbox-TTS-Extended`

Then install via
`pip install -r requirements.txt`  

<sup> if for some reason the install doesn't run try doing </sup> `pip install -r requirements.base.with.versions.txt`, 
<sup> and if that still doesn't work then do </sup> `pip install -r requirements_frozen.txt`

Then run via
`python Chatter.py`


FFMPEG is required. If you don't have it installed in your system path, put it in the same directory as the Chatter.py script.
