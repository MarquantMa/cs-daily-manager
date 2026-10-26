import os
import threading

# Ensure Homebrew and standard bin paths are in PATH for tools like ffmpeg
for p in ["/opt/homebrew/bin", "/usr/local/bin"]:
    if os.path.exists(p) and p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{p}:{os.environ.get('PATH', '')}"

_model = None
_model_lock = threading.RLock()

def get_model():
    global _model
    with _model_lock:
        if _model is None:
            import torch
            try:
                torch.set_num_threads(2)
            except Exception:
                pass

            import whisper
            device = "cpu"
            print(f"Loading Whisper model (small) on {device}...")
            _model = whisper.load_model("small", device=device)
        return _model

def transcribe(file_path):
    if not os.path.exists(file_path):
        return "Error: File not found."

    with _model_lock:
        try:
            model = get_model()
            result = model.transcribe(file_path, fp16=False)
            return result["text"].strip()
        except Exception as e:
            print(f"Error during Whisper transcription: {e}")
            return f"Error: {e}"
