"""MLMS Windows 데스크톱 위젯 — 엔트리포인트."""

import os
import sys
from datetime import datetime

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction
from PyQt6.QtCore import QTimer

from config import Config
from lms_session import LmsSession
from timetable_widget import TimetableDesktopWidget
from login_dialog import LoginDialog
from settings_dialog import SettingsDialog
from class_detail_dialog import ClassDetailDialog


def create_default_icon() -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setBrush(QColor("#4A90D9"))
    p.setPen(QColor("#4A90D9"))
    p.drawRoundedRect(1, 1, 14, 14, 3, 3)
    p.setPen(QColor(255, 255, 255))
    p.drawText(3, 13, "M")
    p.end()
    return QIcon(pm)


class MLMSApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.config = Config()
        self.session = LmsSession()
        self.widget = TimetableDesktopWidget(self.config)
        self.widget.week_changed.connect(self._on_week_changed)
        self.widget.class_clicked.connect(self._on_class_clicked)

        # 시스템 트레이
        self.tray = QSystemTrayIcon(create_default_icon(), self.app)
        self._build_tray_menu()
        self.tray.show()

        # 시그널 연결
        self.session.login_success.connect(self._on_login_success)
        self.session.login_failed.connect(self._on_login_failed)
        self.session.events_loaded.connect(self._on_events_loaded)
        self.session.events_failed.connect(self._on_events_failed)

        # 자동 갱신 타이머
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh)
        interval_ms = self.config["refresh_interval"] * 60 * 1000
        self.refresh_timer.start(interval_ms)

        # 로그인 상태
        self._logged_in = False
        self._username = ""
        self._password = ""
        self._detail_dialog = None

    def _build_tray_menu(self):
        menu = QMenu()

        self.action_refresh = QAction("새로고침")
        self.action_refresh.triggered.connect(self._refresh)
        menu.addAction(self.action_refresh)

        self.action_this_week = QAction("이번 주로 이동")
        self.action_this_week.triggered.connect(self.widget.go_this_week)
        menu.addAction(self.action_this_week)

        menu.addSeparator()

        self.action_settings = QAction("설정")
        self.action_settings.triggered.connect(self._show_settings)
        menu.addAction(self.action_settings)

        self.action_login = QAction("로그인")
        self.action_login.triggered.connect(self._show_login)
        menu.addAction(self.action_login)

        self.action_logout = QAction("로그아웃")
        self.action_logout.triggered.connect(self._logout)
        menu.addAction(self.action_logout)

        menu.addSeparator()

        action_quit = QAction("종료")
        action_quit.triggered.connect(self._quit)
        menu.addAction(action_quit)

        self.tray.setContextMenu(menu)

    def start(self):
        # 디스크 캐시가 있으면 즉시 위젯에 표시
        week_start = self.widget.current_week_start()
        cached = self.session.get_cached_week(week_start)
        if cached:
            self.widget.set_classes(cached)
            self.widget.show()

        creds = LoginDialog.get_saved_credentials(self.config)
        if creds:
            self._username, self._password = creds
            self.tray.setToolTip("MLMS — 로그인 중…")
            self.session.login(self._username, self._password)
        else:
            self._show_login()

        return self.app.exec()

    # ── 로그인 ──────────────────────────────────

    def _show_login(self):
        dlg = LoginDialog(self.config)
        if dlg.exec() == LoginDialog.DialogCode.Accepted:
            self._username, self._password, auto_login = dlg.get_credentials()
            if not self._username or not self._password:
                QMessageBox.warning(None, "MLMS", "아이디와 비밀번호를 입력해주세요.")
                return
            self.tray.setToolTip("MLMS — 로그인 중…")
            self._auto_login = auto_login
            self.session.login(self._username, self._password)

    def _on_login_success(self):
        self._logged_in = True
        self.tray.setToolTip(f"MLMS — {self._username}")

        auto = getattr(self, '_auto_login', self.config["auto_login"])
        LoginDialog(self.config).save_credentials(self._username, self._password, auto)

        # 세션 만료 후 재로그인된 경우 — 대기 중인 상세 요청 재시도
        if getattr(self, '_pending_relogin_detail', False) and self._detail_dialog:
            self._pending_relogin_detail = False
            ci = self._detail_dialog.class_info
            lp_seq = ci.get("lp_seq")
            curr_seq = ci.get("curr_seq")
            aca_seq = ci.get("aca_seq")
            if lp_seq and curr_seq and aca_seq:
                self.session.load_lesson_detail(lp_seq, curr_seq, aca_seq)
            return

        self._load_all()
        self.widget.show()

    def _on_login_failed(self, msg: str):
        self.tray.setToolTip("MLMS — 로그인 실패")
        QMessageBox.warning(None, "MLMS 로그인 실패", msg)
        self._show_login()

    def _logout(self):
        self._logged_in = False
        self.widget.hide()
        LoginDialog.clear_credentials(self.config)
        self.tray.setToolTip("MLMS — 로그아웃됨")

    # ── 시간표 ──────────────────────────────────

    def _load_all(self):
        """전체 이벤트를 한 번에 로드."""
        self.session.load_all_events()

    def _on_week_changed(self, week_start: datetime):
        """주차 이동 — 캐시에서 즉시 표시, 캐시 없으면 네트워크 로드."""
        if not self._logged_in:
            return
        cached = self.session.get_cached_week(week_start)
        if cached is not None:
            self.widget.set_classes(cached)
        else:
            self.session.load_all_events()

    def _on_events_loaded(self, all_events: list):
        """전체 이벤트 로드 완료 — 현재 보고 있는 주차만 필터링해서 표시."""
        week_start = self.widget.current_week_start()
        cached = self.session.get_cached_week(week_start)
        self.widget.set_classes(cached if cached is not None else [])

    def _on_events_failed(self, msg: str):
        if "세션 만료" in msg and self._username and self._password:
            self._logged_in = False
            self.session.login(self._username, self._password)
            return
        self.tray.showMessage("MLMS", f"시간표 로드 실패: {msg}", QSystemTrayIcon.MessageIcon.Warning)

    def _refresh(self):
        """백그라운드 갱신 — 새 데이터를 가져와서 변경 시에만 위젯 업데이트."""
        if self._logged_in:
            self.session.load_all_events()

    # ── 수업 상세 + 파일 다운로드 ───────────────

    def _on_class_clicked(self, class_info: dict):
        """수업 블록 클릭 → 상세 다이얼로그."""
        dlg = ClassDetailDialog(class_info)
        self._detail_dialog = dlg

        lp_seq = class_info.get("lp_seq")
        curr_seq = class_info.get("curr_seq")
        aca_seq = class_info.get("aca_seq")

        if lp_seq and curr_seq and aca_seq:
            # 비동기로 상세 로드
            self.session.detail_loaded.connect(self._on_detail_loaded)
            self.session.detail_failed.connect(self._on_detail_failed)
            self.session.load_lesson_detail(lp_seq, curr_seq, aca_seq)
        else:
            dlg.set_detail({"subject": "", "room": "", "files": []})

        dlg.file_download_requested.connect(self._on_file_download)
        dlg.exec()

        # 시그널 정리
        try:
            self.session.detail_loaded.disconnect(self._on_detail_loaded)
            self.session.detail_failed.disconnect(self._on_detail_failed)
        except TypeError:
            pass
        self._detail_dialog = None

    def _on_detail_loaded(self, detail: dict):
        if self._detail_dialog:
            self._detail_dialog.set_detail(detail)

    def _on_detail_failed(self, msg: str):
        if "세션 만료" in msg and self._username and self._password:
            # 재로그인 후 상세 재시도
            self._pending_relogin_detail = True
            self._logged_in = False
            self.session.login(self._username, self._password)
            return
        if self._detail_dialog:
            self._detail_dialog.set_detail_error(msg)

    def _on_file_download(self, file_info: dict):
        """파일 다운로드 시작."""
        self.session.download_finished.connect(self._on_download_finished)
        self.session.download_failed.connect(self._on_download_failed)
        self.session.download_file(file_info)

    def _on_download_finished(self, path: str):
        self.session.download_finished.disconnect(self._on_download_finished)
        self.session.download_failed.disconnect(self._on_download_failed)
        if self._detail_dialog:
            self._detail_dialog.on_download_finished(path)
        self.tray.showMessage("MLMS", f"다운로드 완료: {path}", QSystemTrayIcon.MessageIcon.Information)

    def _on_download_failed(self, msg: str):
        try:
            self.session.download_finished.disconnect(self._on_download_finished)
            self.session.download_failed.disconnect(self._on_download_failed)
        except TypeError:
            pass
        if self._detail_dialog:
            self._detail_dialog.on_download_failed(msg)

    # ── 설정 ────────────────────────────────────

    def _show_settings(self):
        dlg = SettingsDialog(self.config)
        if dlg.exec() == SettingsDialog.DialogCode.Accepted:
            self.widget.update()
            # 갱신 간격 업데이트
            interval_ms = self.config["refresh_interval"] * 60 * 1000
            self.refresh_timer.start(interval_ms)

    def _quit(self):
        self.widget.hide()
        self.tray.hide()
        self.app.quit()


def main():
    app = MLMSApp()
    sys.exit(app.start())


if __name__ == "__main__":
    main()
