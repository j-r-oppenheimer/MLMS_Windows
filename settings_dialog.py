"""설정 다이얼로그."""

import sys
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QCheckBox, QPushButton, QRadioButton, QButtonGroup,
    QColorDialog, QGroupBox, QFontComboBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from config import Config


def set_auto_start(enabled: bool):
    """Windows 시작프로그램 레지스트리에 등록/해제."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        if enabled:
            # exe로 빌드된 경우 exe 경로, 아니면 python + script 경로
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = f'"{sys.executable}" "{os.path.abspath("main.py")}"'
            winreg.SetValueEx(key, "MLMS", 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, "MLMS")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("MLMS 위젯 설정")
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)

        # 배경 투명도
        layout.addWidget(QLabel("배경 투명도"))
        self.bg_alpha = QSlider(Qt.Orientation.Horizontal)
        self.bg_alpha.setRange(0, 255)
        self.bg_alpha.setValue(config["bg_alpha"])
        layout.addWidget(self.bg_alpha)

        # 블록 투명도
        layout.addWidget(QLabel("블록 투명도"))
        self.block_alpha = QSlider(Qt.Orientation.Horizontal)
        self.block_alpha.setRange(0, 255)
        self.block_alpha.setValue(config["block_alpha"])
        layout.addWidget(self.block_alpha)

        # 텍스트 크기
        self.text_size_label = QLabel(f"텍스트 크기: {config['text_size']}%")
        layout.addWidget(self.text_size_label)
        self.text_size = QSlider(Qt.Orientation.Horizontal)
        self.text_size.setRange(50, 150)
        self.text_size.setValue(config["text_size"])
        self.text_size.valueChanged.connect(
            lambda v: self.text_size_label.setText(f"텍스트 크기: {v}%")
        )
        layout.addWidget(self.text_size)

        # 폰트 선택
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("폰트:"))
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(config["font_family"]))
        font_layout.addWidget(self.font_combo)
        layout.addLayout(font_layout)

        # 다크모드
        self.dark_mode = QCheckBox("다크 모드")
        self.dark_mode.setChecked(config["dark_mode"])
        layout.addWidget(self.dark_mode)

        # 시험 하이라이트
        self.exam_hl = QCheckBox("시험 하이라이트")
        self.exam_hl.setChecked(config["exam_highlight"])
        layout.addWidget(self.exam_hl)

        # 블록 색상
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("블록 색상:"))
        self.color_btn = QPushButton()
        self._block_color = config["block_color"]
        self._update_color_btn()
        self.color_btn.clicked.connect(self._pick_color)
        color_layout.addWidget(self.color_btn)
        layout.addLayout(color_layout)

        # A/B반 선택
        class_group = QGroupBox("반 선택")
        class_layout = QHBoxLayout()
        self.class_btn_group = QButtonGroup(self)
        for label, val in [("전체", "all"), ("A반", "A"), ("B반", "B")]:
            rb = QRadioButton(label)
            if config["class_filter"] == val:
                rb.setChecked(True)
            rb.setProperty("filter_val", val)
            self.class_btn_group.addButton(rb)
            class_layout.addWidget(rb)
        class_group.setLayout(class_layout)
        layout.addWidget(class_group)

        # 시작 시 자동 실행
        self.auto_start = QCheckBox("Windows 시작 시 자동 실행")
        self.auto_start.setChecked(config["auto_start"])
        layout.addWidget(self.auto_start)

        # 버튼
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("저장")
        ok_btn.clicked.connect(self._save_and_close)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _update_color_btn(self):
        self.color_btn.setStyleSheet(
            f"background-color: {self._block_color}; min-width: 60px; min-height: 24px;"
        )
        self.color_btn.setText(self._block_color)

    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self._block_color), self, "블록 색상 선택")
        if color.isValid():
            self._block_color = color.name()
            self._update_color_btn()

    def _save_and_close(self):
        self.config["bg_alpha"] = self.bg_alpha.value()
        self.config["block_alpha"] = self.block_alpha.value()
        self.config["text_size"] = self.text_size.value()
        self.config["font_family"] = self.font_combo.currentFont().family()
        self.config["dark_mode"] = self.dark_mode.isChecked()
        self.config["exam_highlight"] = self.exam_hl.isChecked()
        self.config["block_color"] = self._block_color

        checked = self.class_btn_group.checkedButton()
        if checked:
            self.config["class_filter"] = checked.property("filter_val")

        # 자동 시작 설정
        auto_start = self.auto_start.isChecked()
        self.config["auto_start"] = auto_start
        set_auto_start(auto_start)

        self.config.save()
        self.accept()
