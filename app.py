import json
import gc
import os
import subprocess
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from vosk import KaldiRecognizer, Model, SetLogLevel


BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = Path(os.getenv("VOSK_MODELS_DIR", BASE_DIR / "models")).resolve()
LANGUAGES_FILE = Path(os.getenv("VOSK_LANGUAGES_FILE", BASE_DIR / "languages.json"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

with LANGUAGES_FILE.open(encoding="utf-8") as languages_file:
    LANGUAGE_CONFIG = json.load(languages_file)


def model_path(language: str) -> Path:
    config = LANGUAGE_CONFIG.get(language)
    if not config:
        raise ValueError(f"Unsupported language: {language}")
    path = (MODELS_DIR / config["path"]).resolve()
    if MODELS_DIR not in path.parents or not (path / "am" / "final.mdl").is_file():
        raise ValueError(f"Model for '{language}' is not installed")
    return path


def installed_languages() -> list[dict[str, str]]:
    installed = []
    for code, config in LANGUAGE_CONFIG.items():
        try:
            model_path(code)
        except ValueError:
            continue
        installed.append({"code": code, "name": config["name"]})
    return installed

SetLogLevel(-1)
app = FastAPI(title="Multilingual Speech-to-Text API", version="2.0.0")

# The free Render instance has limited RAM. Keep only one model loaded, and
# serialize recognition so a language switch cannot unload a model in use.
model_lock = threading.Lock()
active_model: Model | None = None
active_language: str | None = None


def get_model(language: str) -> Model:
    global active_model, active_language
    if active_model is None or active_language != language:
        active_model = None
        active_language = None
        gc.collect()
        active_model = Model(str(model_path(language)))
        active_language = language
    return active_model


def transcribe_audio(upload: bytes, suffix: str, language: str) -> str:
    """Convert an uploaded audio file to PCM and transcribe it with Vosk."""
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / f"input{suffix}"
        input_path.write_bytes(upload)

        command = [
            "ffmpeg", "-v", "error", "-i", str(input_path),
            "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "-",
        ]
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as exc:
            raise RuntimeError("FFmpeg is not installed on the server") from exc

        with model_lock:
            recognizer = KaldiRecognizer(get_model(language), 16000)
            assert process.stdout is not None
            while chunk := process.stdout.read(8000):
                recognizer.AcceptWaveform(chunk)

        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        if process.wait() != 0:
            raise ValueError(stderr.strip() or "The uploaded file is not valid audio")

        return json.loads(recognizer.FinalResult()).get("text", "")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/languages")
def languages() -> dict[str, list[dict[str, str]]]:
    return {"languages": installed_languages()}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...), language: str = "hi") -> dict[str, str]:
    audio = await file.read(MAX_UPLOAD_BYTES + 1)
    if not audio:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(audio) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Maximum upload size is 25 MB")

    suffix = Path(file.filename or "audio.bin").suffix[:10] or ".bin"
    try:
        model_path(language)
        text = await run_in_threadpool(transcribe_audio, audio, suffix, language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"language": language, "text": text}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Multilingual Speech to Text</title>
<style>
body{font-family:system-ui;max-width:680px;margin:60px auto;padding:0 20px;color:#222}
button,input,select{font:inherit;margin:8px 6px 8px 0;padding:10px 14px}#result{white-space:pre-wrap;background:#f5f5f5;padding:18px;min-height:50px}
</style></head><body>
<h1>Multilingual Speech to Text</h1>
<p>Record from your microphone or choose an audio file.</p>
<label for="language">Language:</label><select id="language"></select><br>
<button id="record">Start recording</button><button id="stop" disabled>Stop & transcribe</button><br>
<input id="file" type="file" accept="audio/*"><button id="upload">Transcribe file</button>
<p id="status"></p><div id="result"></div>
<script>
let recorder, chunks=[];
const status=document.querySelector('#status'), result=document.querySelector('#result');
const language=document.querySelector('#language');
async function loadLanguages(){const r=await fetch('/languages');const data=await r.json();for(const item of data.languages){const option=document.createElement('option');option.value=item.code;option.textContent=item.name;language.appendChild(option);}if(!data.languages.length)status.textContent='No language models are installed.';}
async function send(file){status.textContent='Transcribing…';result.textContent='';const body=new FormData();body.append('file',file);
try{const r=await fetch('/transcribe?language='+encodeURIComponent(language.value),{method:'POST',body});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Request failed');result.textContent=data.text||'(No speech recognized)';status.textContent='Done';}
catch(e){status.textContent='Error: '+e.message;}}
document.querySelector('#record').onclick=async(e)=>{const stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];recorder=new MediaRecorder(stream);recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{stream.getTracks().forEach(t=>t.stop());send(new Blob(chunks,{type:recorder.mimeType}));};recorder.start();e.target.disabled=true;document.querySelector('#stop').disabled=false;status.textContent='Recording…';};
document.querySelector('#stop').onclick=(e)=>{recorder.stop();e.target.disabled=true;document.querySelector('#record').disabled=false;};
document.querySelector('#upload').onclick=()=>{const f=document.querySelector('#file').files[0];if(f)send(f);else status.textContent='Choose an audio file first.';};
loadLanguages();
</script></body></html>"""
