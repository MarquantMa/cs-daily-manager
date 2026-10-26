# Daily Manager: 5-Layer Decoupled Architecture

```
+-------------------------------------------------------------+
| Layer 1: Audio Capture & Signal Ingestion                   |
| - PortAudio 44.1 kHz non-blocking circular PCM ring buffer  |
| - Dynamic energy VAD (Voice Activity Detection)             |
+------------------------------+------------------------------+
                               | PCM Frame Stream
                               v
+-------------------------------------------------------------+
| Layer 2: Quantized Neural Speech Recognition                |
| - OpenAI Whisper ASR on Apple Silicon Neural Engine (MLX)   |
| - Sub-800ms end-to-end transcription latency                |
+------------------------------+------------------------------+
                               | Raw Spoken Transcript
                               v
+-------------------------------------------------------------+
| Layer 3: Semantic Schema Reasoning & Extraction             |
| - Local LLM parses intent into strict ISO-8601 JSON payload  |
| - Regex fallback & calendar slot conflict detection         |
+------------------------------+------------------------------+
                               | Validated JSON Intent
                               v
+-------------------------------------------------------------+
| Layer 4: Native macOS AppleScript IPC Integration           |
| - Sanitized AppleScript subprocess pipe execution           |
| - Calendar.app & Reminders.app bidirectional synchronization|
+------------------------------+------------------------------+
                               | Audit Log Event
                               v
+-------------------------------------------------------------+
| Layer 5: Audit & Cryptographic Storage                      |
| - PBKDF2 local cryptographic password & Touch ID audit      |
| - Offline SQLite trace logs (Zero Cloud Leaks)              |
+-------------------------------------------------------------+
```
