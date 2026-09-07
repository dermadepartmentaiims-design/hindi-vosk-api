# Multilingual Vosk transcription API

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
curl -X POST "http://127.0.0.1:8000/transcribe?language=hi" \
  -F "file=@audio.wav"
```

The response has this shape:

```json
{"language": "hi", "text": "नमस्ते दुनिया"}
```

## Add a language

Create a folder under `models` named with a short language code. The extracted
model files must be directly inside it, for example:

```text
models/
├── hi/am/final.mdl
├── hi/conf/model.conf
└── en/am/final.mdl
```

Then add the language to `languages.json`:

```json
{
  "hi": {"name": "Hindi", "path": "hi"},
  "en": {"name": "Indian English", "path": "en"}
}
```

Restart the application. `GET /languages` lists only configured models that are
actually installed. The server keeps one model in memory at a time to fit within
the Render free instance's memory limit.

## Deploy on Render

Push this directory to a Git repository. In Render, create a **Blueprint**, connect
the repository, and select its `render.yaml`. The included Dockerfile installs
FFmpeg and starts the API automatically.

The Vosk model directory must be committed with the application. If the Git host
rejects an individual model file because of its size, store that file with Git LFS.
