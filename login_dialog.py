"""로그인 다이얼로그."""

import keyring

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QPushButton, QMessageBox,
)
from PyQt6.QtCore import Qt

from config import Config

SERVICE_NAME = "MLMS_Windows"


class LoginDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("MLMS 로그인")
        self.setFixedSize(340, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("충남대 LMS 로그인"))

        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("학번 / 아이디")
        layout.addWidget(self.id_input)

        self.pw_input = QLineEdit()
        self.pw_input.setPlaceholderText("비밀번호")
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pw_input)

        self.auto_login_cb = QCheckBox("자동 로그인")
        self.auto_login_cb.setChecked(config["auto_login"])
        layout.addWidget(self.auto_login_cb)

        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("로그인")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("취소")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.login_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # 저장된 자격 복원
        saved_user = config["username"]
        if saved_user:
            self.id_input.setText(saved_user)
            pw = keyring.get_password(SERVICE_NAME, saved_user)
            if pw:
                self.pw_input.setText(pw)

    def get_credentials(self) -> tuple[str, str, bool]:
        return (
            self.id_input.text().strip(),
            self.pw_input.text(),
            self.auto_login_cb.isChecked(),
        )

    def save_credentials(self, username: str, password: str, auto_login: bool):
        self.config["username"] = username
        self.config["auto_login"] = auto_login
        self.config.save()
        if auto_login:
            keyring.set_password(SERVICE_NAME, username, password)

    @staticmethod
    def clear_credentials(config: Config):
        username = config["username"]
        if username:
            try:
                keyring.delete_password(SERVICE_NAME, username)
            except keyring.errors.PasswordDeleteError:
                pass
        config["username"] = ""
        config["auto_login"] = False
        config.save()

    @staticmethod
    def get_saved_credentials(config: Config) -> tuple[str, str] | None:
        """자동 로그인용 저장된 자격 반환."""
        if not config["auto_login"]:
            return None
        username = config["username"]
        if not username:
            return None
        password = keyring.get_password(SERVICE_NAME, username)
        if not password:
            return None
        return username, password
