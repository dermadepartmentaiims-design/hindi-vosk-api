import json
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from vosk import KaldiRecognizer, Model, SetLogLevel


BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = Path(os.getenv("VOSK_MODEL_PATH", BASE_DIR / "vosk-model-small-hi-0.22"))
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

if not MODEL_PATH.is_dir():
    raise RuntimeError(f"Vosk model directory was not found: {MODEL_PATH}")

SetLogLevel(-1)
model = Model(str(MODEL_PATH))
app = FastAPI(title="Hindi Speech-to-Text API", version="1.0.0")


def transcribe_audio(upload: bytes, suffix: str) -> str:
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

        recognizer = KaldiRecognizer(model, 16000)
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


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict[str, str]:
    audio = await file.read(MAX_UPLOAD_BYTES + 1)
    if not audio:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(audio) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Maximum upload size is 25 MB")

    suffix = Path(file.filename or "audio.bin").suffix[:10] or ".bin"
    try:
        text = await run_in_threadpool(transcribe_audio, audio, suffix)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"text": text}


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Hindi Speech to Text</title>
<style>
body{font-family:system-ui;max-width:680px;margin:60px auto;padding:0 20px;color:#222}
button,input{font:inherit;margin:8px 6px 8px 0;padding:10px 14px}#result{white-space:pre-wrap;background:#f5f5f5;padding:18px;min-height:50px}
</style></head><body>
<h1>Hindi Speech to Text</h1>
<p>Record from your microphone or choose an audio file.</p>
<button id="record">Start recording</button><button id="stop" disabled>Stop & transcribe</button><br>
<input id="file" type="file" accept="audio/*"><button id="upload">Transcribe file</button>
<p id="status"></p><div id="result"></div>
<script>
let recorder, chunks=[];
const status=document.querySelector('#status'), result=document.querySelector('#result');
async function send(file){status.textContent='Transcribing…';result.textContent='';const body=new FormData();body.append('file',file);
try{const r=await fetch('/transcribe',{method:'POST',body});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Request failed');result.textContent=data.text||'(No speech recognized)';status.textContent='Done';}
catch(e){status.textContent='Error: '+e.message;}}
document.querySelector('#record').onclick=async(e)=>{const stream=await navigator.mediaDevices.getUserMedia({audio:true});chunks=[];recorder=new MediaRecorder(stream);recorder.ondataavailable=e=>chunks.push(e.data);recorder.onstop=()=>{stream.getTracks().forEach(t=>t.stop());send(new Blob(chunks,{type:recorder.mimeType}));};recorder.start();e.target.disabled=true;document.querySelector('#stop').disabled=false;status.textContent='Recording…';};
document.querySelector('#stop').onclick=(e)=>{recorder.stop();e.target.disabled=true;document.querySelector('#record').disabled=false;};
document.querySelector('#upload').onclick=()=>{const f=document.querySelector('#file').files[0];if(f)send(f);else status.textContent='Choose an audio file first.';};
</script></body></html>"""
