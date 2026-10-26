import os
import json
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(PROJECT_DIR, "recordings")
METADATA_FILE = os.path.join(RECORDINGS_DIR, "metadata.json")

def get_recordings_history():
    """
    Loads all recorded audio metadata. Also scans recordings/ directory for any WAV/audio files 
    that might be missing from metadata.json, guaranteeing zero lost recordings.
    Returns list of dicts ordered by newest first.
    """
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    metadata = []
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            metadata = []

    existing_paths = {entry.get("file_path"): entry for entry in metadata if entry.get("file_path")}

    changed = False
    for filename in os.listdir(RECORDINGS_DIR):
        if filename.lower().endswith((".wav", ".mp3", ".m4a", ".flac")):
            full_path = os.path.join(RECORDINGS_DIR, filename)
            if full_path not in existing_paths:
                mtime = os.path.getmtime(full_path)
                dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                new_entry = {
                    "id": os.path.splitext(filename)[0],
                    "filename": filename,
                    "file_path": full_path,
                    "timestamp": dt_str,
                    "status": "Recorded",
                    "transcription": "",
                    "mode": "todo"
                }
                metadata.append(new_entry)
                existing_paths[full_path] = new_entry
                changed = True

    if changed:
        save_metadata(metadata)

    metadata.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return metadata

def save_metadata(metadata):
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    try:
        with open(METADATA_FILE, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving recordings metadata: {e}")

def add_or_update_recording(file_path, transcription=None, mode=None, status=None):
    history = get_recordings_history()
    filename = os.path.basename(file_path)
    found = False
    
    for entry in history:
        if entry.get("file_path") == file_path or entry.get("filename") == filename:
            found = True
            if transcription is not None:
                entry["transcription"] = transcription
            if mode is not None:
                entry["mode"] = mode
            if status is not None:
                entry["status"] = status
            break
            
    if not found:
        mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else datetime.now().timestamp()
        dt_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        new_entry = {
            "id": os.path.splitext(filename)[0],
            "filename": filename,
            "file_path": file_path,
            "timestamp": dt_str,
            "status": status or ("Transcribed" if transcription else "Recorded"),
            "transcription": transcription or "",
            "mode": mode or "todo"
        }
        history.append(new_entry)

    save_metadata(history)
    return history

def save_transcription(file_path, transcription_text):
    return add_or_update_recording(file_path, transcription=transcription_text, status="Transcribed")

def delete_recording(file_path, delete_file=False):
    history = get_recordings_history()
    filename = os.path.basename(file_path)
    new_history = [e for e in history if e.get("file_path") != file_path and e.get("filename") != filename]
    save_metadata(new_history)
    if delete_file and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Error deleting recording file {file_path}: {e}")
