"""설정 관리 — JSON 파일 기반."""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".mlms_windows"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "bg_alpha": 200,          # 배경 투명도 (0~255)
    "block_alpha": 220,       # 블록 투명도 (0~255)
    "text_size": 100,         # 텍스트 크기 % (50~150)
    "dark_mode": False,
    "block_color": "#4A90D9", # 블록 기본 색상
    "class_filter": "all",    # "all" | "A" | "B"
    "exam_highlight": True,
    "widget_x": 100,
    "widget_y": 100,
    "widget_w": 520,
    "widget_h": 600,
    "auto_login": False,
    "username": "",
    "refresh_interval": 30,   # 분 단위
    "font_family": "맑은 고딕",
    "auto_start": False,      # Windows 시작 시 자동 실행
}


class Config:
    def __init__(self):
        self._data: dict = {}
        self.load()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        # 누락 키 채우기
        for k, v in DEFAULTS.items():
            self._data.setdefault(k, v)

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    def get(self, key: str):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value):
        self._data[key] = value

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)
