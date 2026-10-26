# Thread-safe audio recorder using sounddevice and standard wave module
import wave
import threading
import numpy as np
import os
import atexit
from datetime import datetime

class Recorder:
    def __init__(self, filename="output.wav", samplerate=44100, channels=1):
        self.filename = filename
        self.samplerate = samplerate
        self.channels = channels
        self.recording = False
        self.frames = []
        self.temp_filename = None
        self._record_thread_handle = None
        self._lock = threading.Lock()

        # Register exit hook to handle sudden interpreter terminations
        atexit.register(self.cleanup_on_exit)

    def start(self):
        with self._lock:
            if self.recording:
                return
            self.recording = True
            self.frames = []

            try:
                project_dir = os.path.dirname(os.path.abspath(__file__))
                recordings_dir = os.path.join(project_dir, "recordings")
                os.makedirs(recordings_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                self.temp_filename = os.path.join(recordings_dir, f"recording_{timestamp}.wav")
            except Exception as e:
                print(f"Error setting up recording path: {e}")
                self.temp_filename = "output.wav"

        self._record_thread_handle = threading.Thread(target=self._record_thread, daemon=True)
        self._record_thread_handle.start()

    def _record_thread(self):
        try:
            import sounddevice as sd
            with sd.InputStream(samplerate=self.samplerate, channels=self.channels, callback=self._callback):
                while self.recording:
                    sd.sleep(50)
        except Exception as e:
            print(f"Error in recording stream: {e}")
            self.recording = False

    def _callback(self, indata, frames_count, time, status):
        if status:
            pass  # Suppress non-critical buffer status warnings
        if self.recording:
            self.frames.append(indata.copy())

    def stop(self):
        if not self.recording and not self.frames:
            return None

        # Signal recording thread to stop and wait for clean PortAudio stream shutdown
        self.recording = False
        if self._record_thread_handle and self._record_thread_handle.is_alive():
            self._record_thread_handle.join(timeout=1.0)

        with self._lock:
            if not self.frames:
                print("No audio frames recorded.")
                return None

            try:
                # Concatenate all recorded chunks and convert to 16-bit PCM
                audio_data = np.concatenate(self.frames, axis=0)
                audio_int16 = (audio_data * 32767).clip(-32768, 32767).astype(np.int16)

                with wave.open(self.temp_filename, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(self.samplerate)
                    wf.writeframes(audio_int16.tobytes())

                print(f"Audio file finalized and saved to {self.temp_filename}")
                return self.temp_filename
            except Exception as e:
                print(f"Error writing wave file: {e}")
                return None

    def cleanup_on_exit(self):
        """Standard exit handler triggered automatically on interpreter exit."""
        if self.recording:
            print("Process shutdown detected! Actively saving recording progress...")
            self.stop()
