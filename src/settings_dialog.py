import os
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QRadioButton, QButtonGroup, QFileDialog,
    QFrame, QMessageBox, QGroupBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImageReader

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

class SettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)

    def __init__(self, parent=None, is_dark_mode=True, current_model="Smart Auto-Select", bg_image_path=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        self.is_dark_mode = is_dark_mode
        self.current_model = current_model
        self.bg_image_path = bg_image_path
        
        self.load_current_settings()
        self.init_ui()
        self.apply_theme()

    def load_current_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    if "model" in data:
                        self.current_model = data["model"]
                    if "dark_mode" in data:
                        self.is_dark_mode = data["dark_mode"]
                    if "bg_image" in data:
                        self.bg_image_path = data["bg_image"]
            except Exception as e:
                print("Error reading settings.json:", e)

    def save_to_file(self):
        settings_data = {
            "model": self.model_combo.currentText(),
            "dark_mode": self.dark_radio.isChecked(),
            "bg_image": self.bg_image_path
        }
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings_data, f, indent=2)
        except Exception as e:
            print("Error saving settings.json:", e)
        return settings_data

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(26, 26, 26, 26)
        main_layout.setSpacing(22)

        # Title
        title_label = QLabel("Application Settings")
        title_label.setObjectName("settings_title")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        main_layout.addWidget(title_label)

        # 1. AI Model Selection Group
        model_group = QGroupBox("AI Model Configuration")
        model_layout = QVBoxLayout(model_group)
        model_layout.setSpacing(12)

        model_desc = QLabel("Select the LLM inference engine for calendar parsing and daily advice:")
        model_desc.setWordWrap(True)
        model_desc.setStyleSheet("color: #94A3B8; font-size: 14px;")
        model_layout.addWidget(model_desc)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "Smart Auto-Select",
            "Qwen 2.5 7B (Mac Native MLX)",
            "Qwen 2.5 3B (Mac Native MLX)",
            "SiliconFlow (Qwen 2.5 Cloud)",
            "Deepseek V4 flash",
            "V4 Pro (cloud)",
            "Localhost / Ollama (http://localhost:11434/v1)"
        ])
        if self.current_model in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
            self.model_combo.setCurrentText(self.current_model)
        else:
            self.model_combo.setCurrentText("Smart Auto-Select")
        self.model_combo.setStyleSheet("padding: 10px 14px; font-size: 15px; border-radius: 8px;")
        model_layout.addWidget(self.model_combo)
        main_layout.addWidget(model_group)

        # 2. Appearance & Theme Group
        theme_group = QGroupBox("Appearance & Theme")
        theme_layout = QVBoxLayout(theme_group)
        theme_layout.setSpacing(12)

        theme_btn_layout = QHBoxLayout()
        self.dark_radio = QRadioButton("Dark Mode")
        self.light_radio = QRadioButton("Light Mode")
        self.theme_btn_group = QButtonGroup(self)
        self.theme_btn_group.addButton(self.dark_radio)
        self.theme_btn_group.addButton(self.light_radio)

        if self.is_dark_mode:
            self.dark_radio.setChecked(True)
        else:
            self.light_radio.setChecked(True)

        theme_btn_layout.addWidget(self.dark_radio)
        theme_btn_layout.addWidget(self.light_radio)
        theme_btn_layout.addStretch()
        theme_layout.addLayout(theme_btn_layout)
        main_layout.addWidget(theme_group)

        # 3. Wallpaper / Background Group
        bg_group = QGroupBox("Custom Wallpaper")
        bg_layout = QVBoxLayout(bg_group)
        bg_layout.setSpacing(12)

        self.bg_status_label = QLabel(
            f"Current: {os.path.basename(self.bg_image_path)}" if self.bg_image_path and os.path.exists(self.bg_image_path) else "Current: Default Gradient"
        )
        self.bg_status_label.setStyleSheet("color: #94A3B8; font-size: 14px;")
        bg_layout.addWidget(self.bg_status_label)

        bg_btn_layout = QHBoxLayout()
        self.choose_bg_btn = QPushButton("Choose Wallpaper...")
        self.choose_bg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.choose_bg_btn.clicked.connect(self.browse_wallpaper)

        self.reset_bg_btn = QPushButton("Reset to Default")
        self.reset_bg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_bg_btn.clicked.connect(self.reset_wallpaper)

        bg_btn_layout.addWidget(self.choose_bg_btn)
        bg_btn_layout.addWidget(self.reset_bg_btn)
        bg_btn_layout.addStretch()
        bg_layout.addLayout(bg_btn_layout)
        main_layout.addWidget(bg_group)

        # 4. Action Buttons (Save / Cancel)
        actions_layout = QHBoxLayout()
        actions_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                font-size: 15px;
                padding: 10px 18px;
                font-weight: bold;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #38BDF8;
                color: #0F172A;
                font-weight: bold;
                font-size: 15px;
                padding: 10px 22px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #0EA5E9;
            }
        """)
        self.save_btn.clicked.connect(self.apply_and_save)

        actions_layout.addWidget(self.cancel_btn)
        actions_layout.addWidget(self.save_btn)
        main_layout.addLayout(actions_layout)

    def browse_wallpaper(self):
        filter_str = (
            "All Supported Images (*.png *.jpg *.jpeg *.webp *.heic *.heif *.bmp *.gif *.tiff *.svg "
            "*.PNG *.JPG *.JPEG *.WEBP *.HEIC *.HEIF *.BMP *.GIF *.TIFF);;"
            "PNG Images (*.png *.PNG);;"
            "JPEG Images (*.jpg *.jpeg *.JPG *.JPEG);;"
            "WebP Images (*.webp *.WEBP);;"
            "All Files (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Wallpaper Image", "", filter_str)
        if file_path:
            pix = QPixmap(file_path)
            if pix.isNull():
                reader = QImageReader(file_path)
                reader.setAutoTransform(True)
                if reader.read().isNull():
                    QMessageBox.warning(self, "Unsupported Image", f"Unable to load the selected image file:\n{file_path}")
                    return
            self.bg_image_path = file_path
            self.bg_status_label.setText(f"Current: {os.path.basename(file_path)}")

    def reset_wallpaper(self):
        self.bg_image_path = None
        self.bg_status_label.setText("Current: Default Gradient")

    def apply_and_save(self):
        new_settings = self.save_to_file()
        self.settings_changed.emit(new_settings)
        self.accept()

    def apply_theme(self):
        if self.is_dark_mode:
            self.setStyleSheet("""
                QDialog {
                    background-color: #13141F;
                    color: #FFFFFF;
                }
                QGroupBox {
                    font-weight: bold;
                    font-size: 15px;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 12px;
                    margin-top: 14px;
                    padding-top: 16px;
                    color: #F1F5F9;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 8px;
                    color: #38BDF8;
                    font-size: 14px;
                }
                QLabel {
                    color: #F1F5F9;
                    font-size: 14px;
                }
                QComboBox {
                    background-color: #1E2235;
                    color: #FFFFFF;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-size: 15px;
                }
                QComboBox QAbstractItemView {
                    background-color: #1E2235;
                    color: #FFFFFF;
                    selection-background-color: #38BDF8;
                    selection-color: #0F172A;
                    font-size: 15px;
                }
                QRadioButton {
                    color: #F1F5F9;
                    font-size: 15px;
                }
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.08);
                    color: #F1F5F9;
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.15);
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #F8FAFC;
                    color: #0F172A;
                }
                QGroupBox {
                    font-weight: bold;
                    font-size: 15px;
                    border: 1px solid rgba(0, 0, 0, 0.12);
                    border-radius: 12px;
                    margin-top: 14px;
                    padding-top: 16px;
                    color: #0F172A;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 8px;
                    color: #0284C7;
                    font-size: 14px;
                }
                QLabel {
                    color: #0F172A;
                    font-size: 14px;
                }
                QComboBox {
                    background-color: #FFFFFF;
                    color: #0F172A;
                    border: 1px solid rgba(0, 0, 0, 0.15);
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-size: 15px;
                }
                QComboBox QAbstractItemView {
                    background-color: #FFFFFF;
                    color: #0F172A;
                    selection-background-color: #0284C7;
                    selection-color: #FFFFFF;
                    font-size: 15px;
                }
                QRadioButton {
                    color: #0F172A;
                    font-size: 15px;
                }
                QPushButton {
                    background-color: rgba(0, 0, 0, 0.05);
                    color: #0F172A;
                    border: 1px solid rgba(0, 0, 0, 0.15);
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: rgba(0, 0, 0, 0.1);
                }
            """)
