import queue, json, sounddevice as sd
from pathlib import Path
from vosk import Model, KaldiRecognizer

q = queue.Queue()
model_path = Path(__file__).resolve().parent / "models" / "hi"
model = Model(str(model_path))
rec = KaldiRecognizer(model, 16000)

def callback(indata, frames, time, status):
    q.put(bytes(indata))

with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                       channels=1, callback=callback):
    print("Speak now (Ctrl+C to stop)...")
    while True:
        data = q.get()
        if rec.AcceptWaveform(data):
            print(json.loads(rec.Result())["text"])
        else:
            partial = json.loads(rec.PartialResult())["partial"]
            if partial:
                print(partial, end="\r")
