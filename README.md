# Hindi Vosk transcription API

## Run locally

Install FFmpeg, then install the Python dependencies and start the API:

```bash
brew install ffmpeg
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app:app --reload
```

Open <http://127.0.0.1:8000>, or call the API directly:

```bash
curl -X POST http://127.0.0.1:8000/transcribe \
  -F "file=@audio.wav"
```

The response has this shape:

```json
{"text": "नमस्ते दुनिया"}
```

## Deploy on Render

Push this directory to a Git repository. In Render, create a **Blueprint**, connect
the repository, and select its `render.yaml`. The included Dockerfile installs
FFmpeg and starts the API automatically.

The Vosk model directory must be committed with the application. If the Git host
rejects an individual model file because of its size, store that file with Git LFS.
