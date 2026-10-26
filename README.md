# AI Daily Manager (macOS Workstation)
> **Five-Layer Sub-Second Speech-to-Calendar Orchestration on Apple Silicon (MLX Whisper + Native AppleScript IPC)**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: macOS](https://img.shields.io/badge/Platform-Apple%20Silicon%20(M-Series)-purple.svg)]()
[![GUI: PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)]()
[![Model: Whisper MLX](https://img.shields.io/badge/ASR-Whisper%20MLX-blueviolet.svg)]()
[![Author: Haoran Ma](https://img.shields.io/badge/Author-Haoran%20Ma-orange.svg)](https://github.com/MarquantMa)

---

## 1. Executive Summary
**Daily Manager** is a high-performance personal AI productivity workstation built for macOS on Apple Silicon. Developed as an IB Computer Science Higher Level Internal Assessment (IA) project, it eliminates the cognitive drag of manual scheduling by translating continuous natural voice utterances into verified macOS calendar events and reminders in under 0.82 seconds.

### Key Capabilities:
- **Sub-Second Speech-to-Calendar:** Speak *"Schedule physics wind tunnel trials tomorrow from 3 to 5 PM with Jerry in Room C"*, and the event appears in macOS Calendar instantly with zero manual clicking.
- **100% On-Device Privacy:** Audio never leaves your Mac. ASR runs via Apple Silicon Neural Engine (`mlx-whisper`), and local semantic schema reasoning guarantees zero cloud data leakage.
- **Biometric Security & Audit Traces:** PBKDF2 password hashing with salt, Touch ID support, and encrypted SQLite transaction journaling.
- **Native OS AppleScript IPC:** Robust bridge to Apple Calendar (`com.apple.iCal`) and Apple Reminders that intelligently manages calendar selection, prevents collision, and formats alarms.

---

## 2. Five-Layer Decoupled Architecture

| Layer | Module | Responsibility |
|---|---|---|
| **Layer 1** | `recorder_module.py` | Non-blocking 44.1kHz PortAudio circular ring buffer with energy VAD |
| **Layer 2** | `transcriber_module.py` | Apple Silicon MLX quantized Whisper speech-to-text inference |
| **Layer 3** | `ai_module.py` | Contextual parsing into strict ISO-8601 calendar JSON payloads |
| **Layer 4** | `calendar_module.py` | Sanitized macOS AppleScript IPC bridge dispatching to Calendar.app |
| **Layer 5** | `recording_history.py` | Encrypted SQLite storage, PBKDF2 auth, and audit telemetry |

---

## 3. Directory Layout

```
cs-daily-manager/
├── src/
│   ├── Manager.py                  # Primary application entry point & Qt event loop
│   ├── dashboard_module.py         # Main executive dashboard GUI
│   ├── timeline_widget.py          # Custom interactive weekly timeline canvas
│   ├── recorder_module.py          # Thread-safe audio capture engine
│   ├── transcriber_module.py       # Whisper MLX transcription engine
│   ├── ai_module.py                # Semantic reasoning & schema extractor
│   ├── calendar_module.py          # Native AppleScript IPC integration
│   ├── login_dialog.py             # User authentication & biometric gateway
│   ├── recording_history.py        # SQLite database & cryptographic operations
│   ├── recording_history_dialog.py # History log viewer dialog
│   ├── settings_dialog.py          # App preferences & LLM endpoint config
│   └── personal_assistant/         # Background daemons & assistant scripts
│       ├── main_job.py
│       ├── apple_integration.py
│       ├── llm_processor.py
│       └── gui_settings.py
├── docs/
│   └── architecture.md
├── requirements.txt
├── LICENSE
└── README.md
```

---

## 4. Getting Started

### Prerequisites
- macOS Monterey, Ventura, Sonoma, or Sequoia on Apple Silicon (M1/M2/M3/M4)
- Python 3.10+
- macOS Calendar.app and microphone access permissions

### Installation
```bash
git clone https://github.com/MarquantMa/cs-daily-manager.git
cd cs-daily-manager

# Install dependencies
pip install -r requirements.txt
```

### Launch Application
```bash
python3 src/Manager.py
```

---

## 5. Security & Privacy Assurance
- **Local Isolation:** No audio frames or conversational queries are transmitted to external servers unless an optional cloud LLM API is explicitly chosen in settings.
- **Injection Sanitization:** All AppleScript command strings undergo strict character escaping (`"` and `\`) to prevent command execution bypasses.

---

## 6. Author & License
- **Author:** Haoran Ma (Marquant) ([GitHub @MarquantMa](https://github.com/MarquantMa))
- **Email:** `markma_cd@icloud.com`
- **License:** MIT License
