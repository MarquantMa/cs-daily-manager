import os
import sys
import json
import hashlib
import secrets

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFrame, QMessageBox, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QSize
from PyQt6.QtGui import QIcon, QPixmap, QFont, QColor

AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'exports', 'auth_config.json')

class AuthManager:
    @staticmethod
    def is_password_set():
        if os.path.exists(AUTH_FILE):
            try:
                with open(AUTH_FILE, 'r') as f:
                    data = json.load(f)
                    return bool(data.get('hash') and data.get('salt'))
            except Exception as e:
                print("Error reading auth config:", e)
        return False

    @staticmethod
    def set_password(plain_password):
        if not plain_password:
            return False
        salt = secrets.token_hex(16)
        pwd_hash = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
        os.makedirs(os.path.dirname(AUTH_FILE), exist_ok=True)
        with open(AUTH_FILE, 'w') as f:
            json.dump({'salt': salt, 'hash': pwd_hash}, f)
        return True

    @staticmethod
    def verify_password(plain_password):
        if not os.path.exists(AUTH_FILE):
            return False
        try:
            with open(AUTH_FILE, 'r') as f:
                data = json.load(f)
            salt = data.get('salt')
            stored_hash = data.get('hash')
            if not salt or not stored_hash:
                return False
            computed_hash = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), 100000).hex()
            return secrets.compare_digest(stored_hash, computed_hash)
        except Exception as e:
            print("Error verifying password:", e)
            return False

    @staticmethod
    def _parse_eval_res(res):
        if isinstance(res, (tuple, list)):
            return bool(res[0])
        return bool(res)

    @staticmethod
    def is_touch_id_available():
        if sys.platform != 'darwin':
            return False
        try:
            from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthenticationWithBiometrics, LAPolicyDeviceOwnerAuthentication
            context = LAContext.alloc().init()
            can_bio = AuthManager._parse_eval_res(context.canEvaluatePolicy_error_(LAPolicyDeviceOwnerAuthenticationWithBiometrics, None))
            can_dev = AuthManager._parse_eval_res(context.canEvaluatePolicy_error_(LAPolicyDeviceOwnerAuthentication, None))
            return can_bio or can_dev
        except Exception as e:
            print("Touch ID check exception:", e)
            return False


class TouchIDBridge(QObject):
    success_signal = pyqtSignal()
    failed_signal = pyqtSignal(str)

    def trigger_touch_id(self, reason="Unlock AI Daily Assistant"):
        if sys.platform != 'darwin':
            self.failed_signal.emit("Touch ID is only supported on macOS.")
            return

        try:
            from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthenticationWithBiometrics, LAPolicyDeviceOwnerAuthentication
            context = LAContext.alloc().init()

            can_bio = AuthManager._parse_eval_res(context.canEvaluatePolicy_error_(LAPolicyDeviceOwnerAuthenticationWithBiometrics, None))
            can_dev = AuthManager._parse_eval_res(context.canEvaluatePolicy_error_(LAPolicyDeviceOwnerAuthentication, None))

            if not (can_bio or can_dev):
                self.failed_signal.emit("Touch ID is not available or configured on this device.")
                return

            policy = LAPolicyDeviceOwnerAuthenticationWithBiometrics if can_bio else LAPolicyDeviceOwnerAuthentication

            def reply_handler(success, error):
                if success:
                    self.success_signal.emit()
                else:
                    err_msg = str(error.localizedDescription()) if error else "Authentication canceled"
                    self.failed_signal.emit(err_msg)

            context.evaluatePolicy_localizedReason_reply_(policy, reason, reply_handler)
        except Exception as e:
            self.failed_signal.emit(str(e))


class LoginDialog(QDialog):
    def __init__(self, is_dark_mode=True, parent=None):
        super().__init__(parent)
        self.is_dark_mode = is_dark_mode
        self.is_setup_mode = not AuthManager.is_password_set()

        self.touch_bridge = TouchIDBridge()
        self.touch_bridge.success_signal.connect(self.on_touch_success)
        self.touch_bridge.failed_signal.connect(self.on_touch_failed)

        self.init_ui()

        # Auto-trigger Touch ID if available and not in initial setup mode
        if not self.is_setup_mode and AuthManager.is_touch_id_available():
            QTimer.singleShot(400, self.prompt_touch_id)

    def init_ui(self):
        self.setWindowTitle("Security Authentication - AI Daily Assistant")
        self.setFixedSize(460, 560)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowCloseButtonHint)

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setSpacing(18)

        # 1. Header Card (App Icon + Title)
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.setSpacing(8)

        icon_label = QLabel()
        icon_label.setFixedSize(72, 72)
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(pix)
        else:
            icon_label.setText("Login")
            icon_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #38BDF8;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label = QLabel("AI Daily Assistant")
        title_label.setObjectName("app_title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle_text = "Create Master Password" if self.is_setup_mode else "Protected Session • Please Unlock"
        self.subtitle_label = QLabel(subtitle_text)
        self.subtitle_label.setObjectName("app_subtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)
        header_layout.addWidget(self.subtitle_label)
        main_layout.addLayout(header_layout)

        main_layout.addSpacing(10)

        # 2. Touch ID Section (if available and not setup mode)
        if not self.is_setup_mode and AuthManager.is_touch_id_available():
            self.touch_btn = QPushButton("Unlock with Touch ID")
            self.touch_btn.setObjectName("touch_btn")
            self.touch_btn.setFixedHeight(50)
            self.touch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.touch_btn.clicked.connect(self.prompt_touch_id)
            main_layout.addWidget(self.touch_btn)

            divider_layout = QHBoxLayout()
            divider_layout.setContentsMargins(0, 6, 0, 6)
            line1 = QFrame()
            line1.setFrameShape(QFrame.Shape.HLine)
            line1.setFrameShadow(QFrame.Shadow.Sunken)
            line2 = QFrame()
            line2.setFrameShape(QFrame.Shape.HLine)
            line2.setFrameShadow(QFrame.Shadow.Sunken)
            or_label = QLabel("OR ENTER PASSWORD")
            or_label.setObjectName("or_label")
            or_label.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: bold;")

            divider_layout.addWidget(line1)
            divider_layout.addWidget(or_label)
            divider_layout.addWidget(line2)
            main_layout.addLayout(divider_layout)

        # 3. Password Input Section
        pwd_box = QVBoxLayout()
        pwd_box.setSpacing(12)

        pwd_input_layout = QHBoxLayout()
        pwd_input_layout.setSpacing(0)

        self.pwd_field = QLineEdit()
        self.pwd_field.setPlaceholderText("Enter master password..." if not self.is_setup_mode else "Create master password...")
        self.pwd_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd_field.setFixedHeight(48)
        self.pwd_field.returnPressed.connect(self.on_submit_password)

        self.toggle_eye_btn = QPushButton("Show")
        self.toggle_eye_btn.setFixedSize(60, 48)
        self.toggle_eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_eye_btn.setToolTip("Show/Hide Password")
        self.toggle_eye_btn.clicked.connect(self.toggle_password_visibility)
        self.toggle_eye_btn.setObjectName("eye_btn")

        pwd_input_layout.addWidget(self.pwd_field)
        pwd_input_layout.addWidget(self.toggle_eye_btn)
        pwd_box.addLayout(pwd_input_layout)

        # Confirm password field if setup mode
        if self.is_setup_mode:
            self.confirm_pwd_field = QLineEdit()
            self.confirm_pwd_field.setPlaceholderText("Confirm master password...")
            self.confirm_pwd_field.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_pwd_field.setFixedHeight(48)
            self.confirm_pwd_field.returnPressed.connect(self.on_submit_password)
            pwd_box.addWidget(self.confirm_pwd_field)

        main_layout.addLayout(pwd_box)

        # Error / Status Label
        self.status_msg = QLabel("")
        self.status_msg.setObjectName("status_msg")
        self.status_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_msg.setWordWrap(True)
        main_layout.addWidget(self.status_msg)

        # Action Submit Button
        btn_text = "Set Password & Unlock" if self.is_setup_mode else "Unlock Assistant"
        self.submit_btn = QPushButton(btn_text)
        self.submit_btn.setObjectName("submit_btn")
        self.submit_btn.setFixedHeight(50)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.clicked.connect(self.on_submit_password)
        main_layout.addWidget(self.submit_btn)

        main_layout.addStretch()

        self.apply_theme()

    def toggle_password_visibility(self):
        if self.pwd_field.echoMode() == QLineEdit.EchoMode.Password:
            self.pwd_field.setEchoMode(QLineEdit.EchoMode.Normal)
            if hasattr(self, 'confirm_pwd_field'):
                self.confirm_pwd_field.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_eye_btn.setText("Hide")
        else:
            self.pwd_field.setEchoMode(QLineEdit.EchoMode.Password)
            if hasattr(self, 'confirm_pwd_field'):
                self.confirm_pwd_field.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_eye_btn.setText("Show")

    def prompt_touch_id(self):
        self.status_msg.setStyleSheet("color: #38BDF8; font-size: 14px; font-weight: bold;")
        self.status_msg.setText("Waiting for Touch ID biometrics...")
        self.touch_bridge.trigger_touch_id("Authenticate to open AI Daily Assistant")

    def on_touch_success(self):
        self.status_msg.setStyleSheet("color: #30D158; font-size: 14px; font-weight: bold;")
        self.status_msg.setText("Touch ID Authenticated!")
        QTimer.singleShot(300, self.accept)

    def on_touch_failed(self, err_msg):
        self.status_msg.setStyleSheet("color: #FF453A; font-size: 14px; font-weight: bold;")
        if "canceled" in err_msg.lower() or "usercancel" in err_msg.lower():
            self.status_msg.setText("Touch ID canceled. Please enter your password.")
        else:
            self.status_msg.setText(f"Touch ID failed: {err_msg}")

    def on_submit_password(self):
        pwd = self.pwd_field.text().strip()

        if self.is_setup_mode:
            confirm_pwd = self.confirm_pwd_field.text().strip()
            if not pwd:
                self.show_error("Password cannot be empty.")
                return
            if len(pwd) < 4:
                self.show_error("Password must be at least 4 characters.")
                return
            if pwd != confirm_pwd:
                self.show_error("Passwords do not match.")
                return

            if AuthManager.set_password(pwd):
                self.status_msg.setStyleSheet("color: #30D158; font-size: 14px; font-weight: bold;")
                self.status_msg.setText("Master Password Created!")
                QTimer.singleShot(400, self.accept)
            else:
                self.show_error("Failed to save password.")
        else:
            if not pwd:
                self.show_error("Please enter your password.")
                return
            if AuthManager.verify_password(pwd):
                self.status_msg.setStyleSheet("color: #30D158; font-size: 14px; font-weight: bold;")
                self.status_msg.setText("Password Verified!")
                QTimer.singleShot(300, self.accept)
            else:
                self.show_error("Incorrect master password. Please try again.")

    def show_error(self, msg):
        self.status_msg.setStyleSheet("color: #FF453A; font-size: 14px; font-weight: bold;")
        self.status_msg.setText(msg)

    def apply_theme(self):
        if self.is_dark_mode:
            bg_color = "#0F172A"
            text_color = "#F8FAFC"
            field_bg = "rgba(255, 255, 255, 0.06)"
            field_border = "rgba(255, 255, 255, 0.12)"
            btn_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0EA5E9, stop:1 #2563EB)"
            btn_hover = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #38BDF8, stop:1 #3B82F6)"
            touch_bg = "rgba(56, 189, 248, 0.12)"
            touch_border = "rgba(56, 189, 248, 0.35)"
        else:
            bg_color = "#FFFFFF"
            text_color = "#0F172A"
            field_bg = "rgba(0, 0, 0, 0.04)"
            field_border = "rgba(0, 0, 0, 0.15)"
            btn_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #1D4ED8)"
            btn_hover = "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369A1, stop:1 #1E40AF)"
            touch_bg = "rgba(2, 132, 199, 0.1)"
            touch_border = "rgba(2, 132, 199, 0.3)"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                border-radius: 16px;
            }}
            QLabel#app_title {{
                font-size: 26px;
                font-weight: 800;
                color: {text_color};
            }}
            QLabel#app_subtitle {{
                font-size: 15px;
                color: #94A3B8;
            }}
            QLineEdit {{
                background-color: {field_bg};
                border: 1px solid {field_border};
                border-top-left-radius: 10px;
                border-bottom-left-radius: 10px;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 0px;
                padding: 10px 14px;
                font-size: 15px;
                color: {text_color};
            }}
            QLineEdit:focus {{
                border: 1px solid #38BDF8;
            }}
            QPushButton#eye_btn {{
                background-color: {field_bg};
                border: 1px solid {field_border};
                border-left: none;
                border-top-right-radius: 10px;
                border-bottom-right-radius: 10px;
                font-size: 13px;
                font-weight: bold;
                color: #38BDF8;
            }}
            QPushButton#eye_btn:hover {{
                color: #FFFFFF;
                background-color: rgba(56, 189, 248, 0.2);
            }}
            QPushButton#touch_btn {{
                background-color: {touch_bg};
                border: 1.5px solid {touch_border};
                border-radius: 12px;
                font-size: 16px;
                font-weight: 700;
                color: #38BDF8;
            }}
            QPushButton#touch_btn:hover {{
                background-color: rgba(56, 189, 248, 0.22);
                border: 1.5px solid #38BDF8;
            }}
            QPushButton#submit_btn {{
                background-color: {btn_bg};
                border-radius: 12px;
                border: none;
                font-size: 16px;
                font-weight: 700;
                color: #FFFFFF;
            }}
            QPushButton#submit_btn:hover {{
                background-color: {btn_hover};
            }}
        """)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    dialog = LoginDialog(is_dark_mode=True)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        print("Login Successful!")
    else:
        print("Login Canceled!")
