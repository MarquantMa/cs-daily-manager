import os
import subprocess
import threading
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                             QPushButton, QLabel, QTextEdit, QMessageBox, QWidget, QSplitter, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from recording_history import get_recordings_history, save_transcription, delete_recording
from transcriber_module import transcribe

class TranscribeWorkerSignals(QObject):
    finished = pyqtSignal(str, str) # file_path, text
    error = pyqtSignal(str)

class RecordingHistoryDialog(QDialog):
    process_transcription_requested = pyqtSignal(str, str) # text, file_path

    def __init__(self, parent=None, is_dark_mode=True):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.recordings = []
        self.current_recording = None
        self.signals = TranscribeWorkerSignals()
        self.signals.finished.connect(self.on_transcription_finished)
        self.signals.error.connect(self.on_transcription_error)
        
        self.setWindowTitle("Audio Recording History")
        self.setMinimumSize(920, 600)
        self.apply_theme()
        self.init_ui()
        self.load_history()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #0f0f1b;
                    color: #ffffff;
                }
                QListWidget {
                    background-color: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    color: #ffffff;
                    padding: 10px;
                    font-size: 15px;
                }
                QListWidget::item {
                    padding: 12px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 8px;
                    font-size: 15px;
                }
                QListWidget::item:selected {
                    background-color: rgba(0, 122, 255, 0.3);
                    color: #ffffff;
                }
                QTextEdit {
                    background-color: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 12px;
                    color: #ffffff;
                    padding: 12px;
                    font-size: 15px;
                }
                QLabel {
                    color: #e2e8f0;
                    font-size: 15px;
                }
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.06);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 8px;
                    color: #ffffff;
                    padding: 10px 18px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.12);
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #f3f4f6;
                    color: #1f2937;
                }
                QListWidget {
                    background-color: rgba(255, 255, 255, 0.8);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 12px;
                    color: #1f2937;
                    padding: 10px;
                    font-size: 15px;
                }
                QListWidget::item {
                    padding: 12px;
                    border-bottom: 1px solid rgba(0, 0, 0, 0.05);
                    border-radius: 8px;
                    font-size: 15px;
                }
                QListWidget::item:selected {
                    background-color: rgba(0, 122, 255, 0.2);
                    color: #0f172a;
                }
                QTextEdit {
                    background-color: rgba(255, 255, 255, 0.9);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 12px;
                    color: #1f2937;
                    padding: 12px;
                    font-size: 15px;
                }
                QLabel {
                    color: #374151;
                    font-size: 15px;
                }
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.8);
                    border: 1px solid rgba(0, 0, 0, 0.1);
                    border-radius: 8px;
                    color: #1f2937;
                    padding: 10px 18px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background-color: #ffffff;
                }
            """)

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(18)

        title_lbl = QLabel("Recording History & Stored Transcriptions")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #38BDF8;" if self.is_dark_mode else "font-size: 22px; font-weight: bold; color: #0284c7;")
        main_layout.addWidget(title_lbl)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: List of recordings
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_lbl = QLabel("Saved Audio Files:")
        left_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")
        left_layout.addWidget(left_lbl)
        
        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self.on_recording_selected)
        left_layout.addWidget(self.list_widget)

        # Right: Details & Transcription
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.file_info_lbl = QLabel("Select a recording from the list")
        self.file_info_lbl.setWordWrap(True)
        self.file_info_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")
        right_layout.addWidget(self.file_info_lbl)

        stored_lbl = QLabel("Stored Transcription Text:")
        stored_lbl.setStyleSheet("font-weight: bold; font-size: 15px;")
        right_layout.addWidget(stored_lbl)
        self.transcription_edit = QTextEdit()
        self.transcription_edit.setPlaceholderText("Stored transcription will appear here. You can also edit it before processing.")
        right_layout.addWidget(self.transcription_edit)

        # Button Controls
        btn_layout1 = QHBoxLayout()
        self.play_btn = QPushButton("Play Audio")
        self.play_btn.clicked.connect(self.play_audio)
        
        self.transcribe_btn = QPushButton("Transcribe / Re-Transcribe")
        self.transcribe_btn.setStyleSheet("background-color: #007AFF; color: white; font-size: 14px; font-weight: bold; padding: 10px 18px;")
        self.transcribe_btn.clicked.connect(self.start_transcription)

        btn_layout1.addWidget(self.play_btn)
        btn_layout1.addWidget(self.transcribe_btn)
        right_layout.addLayout(btn_layout1)

        btn_layout2 = QHBoxLayout()
        self.process_btn = QPushButton("Extract & Add Events / Reminders")
        self.process_btn.setStyleSheet("background-color: #34C759; color: white; font-size: 14px; font-weight: bold; padding: 10px 18px;")
        self.process_btn.clicked.connect(self.process_events)

        self.delete_btn = QPushButton("Delete Recording")
        self.delete_btn.setStyleSheet("background-color: rgba(255, 59, 48, 0.2); color: #FF3B30; border: 1px solid #FF3B30; font-size: 14px; font-weight: bold; padding: 10px 18px;")
        self.delete_btn.clicked.connect(self.delete_selected)

        btn_layout2.addWidget(self.process_btn)
        btn_layout2.addWidget(self.delete_btn)
        right_layout.addLayout(btn_layout2)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([340, 560])

        main_layout.addWidget(splitter)

    def load_history(self):
        self.list_widget.clear()
        self.recordings = get_recordings_history()
        
        if not self.recordings:
            item = QListWidgetItem("No audio recordings found")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(item)
            self.transcription_edit.clear()
            self.file_info_lbl.setText("No recordings available")
            return

        for rec in self.recordings:
            filename = rec.get("filename", "Unknown")
            timestamp = rec.get("timestamp", "")
            has_tx = bool(rec.get("transcription", "").strip())
            status_tag = "Transcribed" if has_tx else "Recorded"
            
            display_text = f"{filename}\n   {timestamp} | [{status_tag}]"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, rec)
            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(0)

    def on_recording_selected(self, current, previous):
        if not current:
            return
        rec = current.data(Qt.ItemDataRole.UserRole)
        if not rec:
            return

        self.current_recording = rec
        filename = rec.get("filename", "")
        file_path = rec.get("file_path", "")
        timestamp = rec.get("timestamp", "")
        transcription = rec.get("transcription", "")

        file_size = "Unknown size"
        if os.path.exists(file_path):
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            file_size = f"{size_mb:.2f} MB"

        self.file_info_lbl.setText(f"File: {filename}\nPath: {file_path}\nRecorded: {timestamp} | Size: {file_size}")
        self.transcription_edit.setText(transcription)

    def play_audio(self):
        if not self.current_recording:
            return
        file_path = self.current_recording.get("file_path", "")
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Missing File", f"Audio file not found at:\n{file_path}")
            return
        try:
            # Play in background using macOS built-in afplay audio player
            subprocess.Popen(["afplay", file_path])
        except Exception as e:
            QMessageBox.critical(self, "Playback Error", f"Could not play audio: {e}")

    def start_transcription(self):
        if not self.current_recording:
            return
        file_path = self.current_recording.get("file_path", "")
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Missing File", f"Audio file not found at:\n{file_path}")
            return

        self.transcribe_btn.setEnabled(False)
        self.transcribe_btn.setText("Transcribing audio (CPU)...")
        self.transcription_edit.setPlaceholderText("Transcribing audio using Whisper model... Please wait.")

        def run_tx():
            try:
                txt = transcribe(file_path)
                self.signals.finished.emit(file_path, txt)
            except Exception as e:
                self.signals.error.emit(str(e))

        threading.Thread(target=run_tx, daemon=True).start()

    def on_transcription_finished(self, file_path, text):
        self.transcribe_btn.setEnabled(True)
        self.transcribe_btn.setText("Transcribe / Re-Transcribe")
        self.transcription_edit.setText(text)
        
        # Permanently store transcription in metadata.json!
        save_transcription(file_path, text)
        QMessageBox.information(self, "Transcription Saved", "Transcription completed and permanently saved to history!")
        self.load_history()

    def on_transcription_error(self, error_msg):
        self.transcribe_btn.setEnabled(True)
        self.transcribe_btn.setText("Transcribe / Re-Transcribe")
        QMessageBox.critical(self, "Transcription Error", f"Failed to transcribe audio:\n{error_msg}")

    def process_events(self):
        if not self.current_recording:
            return
        text = self.transcription_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Empty Transcription", "Please transcribe the audio first or enter text before extracting events.")
            return

        file_path = self.current_recording.get("file_path", "")
        # Save any manually edited text back to metadata
        save_transcription(file_path, text)
        
        # Emit signal to parent ManagerApp to process events
        self.process_transcription_requested.emit(text, file_path)
        self.accept()

    def delete_selected(self):
        if not self.current_recording:
            return
        file_path = self.current_recording.get("file_path", "")
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete this recording entry?\n\n{os.path.basename(file_path)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            delete_recording(file_path, delete_file=True)
            self.load_history()
