"""수업 상세 다이얼로그 — 과목 정보 + 파일 다운로드."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QScrollArea, QWidget, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor


class FileButton(QPushButton):
    """파일 다운로드 버튼."""
    download_requested = pyqtSignal(dict)

    def __init__(self, file_info: dict, parent=None):
        super().__init__(parent)
        self.file_info = file_info
        self.setText(f"  {file_info['name']}")
        self.setStyleSheet("""
            QPushButton {
                color: #1976D2;
                text-align: left;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid #E0E0E0;
                background: transparent;
            }
            QPushButton:hover {
                background: #E3F2FD;
            }
        """)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clicked.connect(lambda: self.download_requested.emit(self.file_info))


class ClassDetailDialog(QDialog):
    """수업 상세 정보 팝업."""
    file_download_requested = pyqtSignal(dict)  # file_info dict

    def __init__(self, class_info: dict, parent=None):
        super().__init__(parent)
        self.class_info = class_info
        self.setWindowTitle("수업 상세")
        self.setMinimumWidth(380)
        self.setMaximumWidth(500)

        layout = QVBoxLayout(self)

        # 과목명 (항상 표시)
        title = class_info.get("title", "")
        title_label = QLabel(title)
        title_label.setFont(QFont("맑은 고딕", 14, QFont.Weight.Bold))
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(line)

        # 로딩 인디케이터
        self.loading_label = QLabel("상세 정보 로딩 중…")
        self.loading_label.setStyleSheet("color: #999; padding: 10px;")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.loading_label)

        # 상세 정보 영역 (로드 전까지 숨김)
        self.detail_widget = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_widget)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.detail_widget.hide()
        layout.addWidget(self.detail_widget)

        # 파일 목록 영역 (로드 전까지 숨김)
        self.files_widget = QWidget()
        self.files_layout = QVBoxLayout(self.files_widget)
        self.files_layout.setContentsMargins(0, 0, 0, 0)
        self.files_widget.hide()
        layout.addWidget(self.files_widget)

        # 다운로드 상태
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #4CAF50; padding: 4px;")
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # 닫기 버튼
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def set_detail(self, detail: dict):
        """비동기로 받은 상세 정보를 표시. 과목 → 교수 → 시간 → 강의실 순서."""
        self.loading_label.hide()

        info_font = QFont("맑은 고딕", 10)
        subject = detail.get("subject", "")
        room = detail.get("room", "")
        professor = self.class_info.get("professor", "")
        ci = self.class_info

        # 과목
        if subject:
            lbl = QLabel(f"과목: {subject}")
            lbl.setFont(info_font)
            self.detail_layout.addWidget(lbl)

        # 교수
        if professor:
            lbl = QLabel(f"교수: {professor}")
            lbl.setFont(info_font)
            self.detail_layout.addWidget(lbl)

        # 시간
        time_str = f"{ci.get('start_hour', 0):02d}:{ci.get('start_min', 0):02d}"
        time_str += f" ~ {ci.get('end_hour', 0):02d}:{ci.get('end_min', 0):02d}"
        lbl = QLabel(f"시간: {time_str}")
        lbl.setFont(info_font)
        self.detail_layout.addWidget(lbl)

        # 강의실
        if room:
            lbl = QLabel(f"강의실: {room}")
            lbl.setFont(info_font)
            self.detail_layout.addWidget(lbl)

        self.detail_widget.show()

        # 파일 목록
        files = detail.get("files", [])
        if files:
            files_header = QLabel(f"첨부파일 ({len(files)})")
            files_header.setFont(QFont("맑은 고딕", 11, QFont.Weight.Bold))
            files_header.setStyleSheet("padding-top: 8px;")
            self.files_layout.addWidget(files_header)

            for f in files:
                btn = FileButton(f)
                btn.download_requested.connect(self._on_download_click)
                self.files_layout.addWidget(btn)
        else:
            no_files = QLabel("첨부파일 없음")
            no_files.setStyleSheet("color: #999; padding: 8px;")
            self.files_layout.addWidget(no_files)

        self.files_widget.show()

    def set_detail_error(self, msg: str):
        """상세 로드 실패."""
        self.loading_label.setText(f"로드 실패: {msg}")
        self.loading_label.setStyleSheet("color: #F44336; padding: 10px;")

    def _on_download_click(self, file_info: dict):
        self.status_label.setText(f"다운로드 중: {file_info['name']}")
        self.status_label.setStyleSheet("color: #FF9800; padding: 4px;")
        self.status_label.show()
        self.file_download_requested.emit(file_info)

    def on_download_finished(self, path: str):
        self.status_label.setText(f"저장됨: {path}")
        self.status_label.setStyleSheet("color: #4CAF50; padding: 4px;")

    def on_download_failed(self, msg: str):
        self.status_label.setText(f"실패: {msg}")
        self.status_label.setStyleSheet("color: #F44336; padding: 4px;")
