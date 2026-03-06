"""LMS 세션 관리 — QWebEngineView 기반 로그인 + 시간표 로드 + 수업 상세 + 파일 다운로드."""

import json
import re
import os
from urllib.parse import quote
from pathlib import Path
from datetime import datetime, timedelta

CACHE_DIR = Path.home() / ".mlms_windows"
CACHE_FILE = CACHE_DIR / "events_cache.json"

from PyQt6.QtCore import QObject, QUrl, QTimer, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineDownloadRequest,
)
from PyQt6.QtNetwork import QNetworkCookie

BASE_URL = "https://cnu.u-lms.com"
LOGIN_URL = f"{BASE_URL}/login"
TIMETABLE_URL = f"{BASE_URL}/aca/MYscheduleMST"
SCHEDULE_SHOW_URL = f"{BASE_URL}/st/lesson/scheduleShow"
FILE_DOWNLOAD_URL = f"{BASE_URL}/file/download"
READ_RECEIPT_URL = f"{BASE_URL}/ajax/st/lesson/lessonData/read"


class LmsSession(QObject):
    """숨겨진 QWebEngineView로 LMS 로그인 후 시간표 이벤트를 추출한다."""

    login_success = pyqtSignal()
    login_failed = pyqtSignal(str)
    events_loaded = pyqtSignal(list)       # List[dict]
    events_failed = pyqtSignal(str)
    detail_loaded = pyqtSignal(dict)       # {subject, room, files: [{name, url, attachSeq, dataSeq}]}
    detail_failed = pyqtSignal(str)
    download_started = pyqtSignal(str)     # file name
    download_finished = pyqtSignal(str)    # saved path
    download_failed = pyqtSignal(str)      # error

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile = QWebEngineProfile("mlms", self)
        self._page = QWebEnginePage(self._profile, self)
        self._view = QWebEngineView()
        self._view.setPage(self._page)
        self._view.resize(1, 1)
        self._view.hide()

        # 별도 WebView — 수업 상세 로드용
        self._detail_page = QWebEnginePage(self._profile, self)
        self._detail_view = QWebEngineView()
        self._detail_view.setPage(self._detail_page)
        self._detail_view.resize(1, 1)
        self._detail_view.hide()

        self._injected = False
        self._login_timer = None
        self._poll_count = 0
        self._all_events: list[dict] = self._load_disk_cache()  # 전체 이벤트 캐시

        self._page.loadFinished.connect(self._on_load_finished)

        # 다운로드 핸들
        self._profile.downloadRequested.connect(self._on_download_requested)

    @staticmethod
    def _load_disk_cache() -> list[dict]:
        try:
            if CACHE_FILE.exists():
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
        return []

    @staticmethod
    def _save_disk_cache(events: list[dict]):
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False)
        except OSError:
            pass

    # ── 로그인 ──────────────────────────────────────

    def login(self, username: str, password: str):
        """로그인 시작."""
        self._username = username
        self._password = password
        self._injected = False
        self._page.load(QUrl(LOGIN_URL))

        self._login_timer = QTimer(self)
        self._login_timer.setSingleShot(True)
        self._login_timer.timeout.connect(lambda: self.login_failed.emit("로그인 시간 초과"))
        self._login_timer.start(30_000)

    def _on_load_finished(self, ok: bool):
        url = self._page.url().toString()

        if "/login" in url and not self._injected:
            self._injected = True
            QTimer.singleShot(800, self._inject_credentials)
            return

        if "/login" not in url and self._injected:
            if self._login_timer:
                self._login_timer.stop()
            self.login_success.emit()
            return

    def _inject_credentials(self):
        safe_id = self._username.replace("\\", "\\\\").replace("'", "\\'")
        safe_pw = self._password.replace("\\", "\\\\").replace("'", "\\'")
        js = f"""
        (function() {{
            var idEl = document.querySelector('input[name="id"]')
                    || document.querySelector('input[name="username"]')
                    || document.querySelectorAll('input[type="text"]')[0];
            var pwEl = document.querySelector('input[name="pwd"]')
                    || document.querySelector('input[name="password"]')
                    || document.querySelector('input[type="password"]');
            if (!idEl || !pwEl) return 'fields_not_found';
            idEl.value = '{safe_id}';
            pwEl.value = '{safe_pw}';
            ['input','change'].forEach(function(ev) {{
                idEl.dispatchEvent(new Event(ev, {{bubbles:true}}));
                pwEl.dispatchEvent(new Event(ev, {{bubbles:true}}));
            }});
            var btn = document.querySelector('button[type="submit"]')
                   || document.querySelector('input[type="submit"]')
                   || document.querySelector('button.btn-login')
                   || document.querySelector('a.btn-login')
                   || document.querySelector('button');
            if (btn) {{ btn.click(); return 'clicked'; }}
            var form = document.querySelector('form');
            if (form) {{ form.submit(); return 'form_submitted'; }}
            return 'no_submit_element';
        }})();
        """
        self._page.runJavaScript(js)

    # ── 시간표 로드 ─────────────────────────────────

    def get_cached_week(self, week_start: datetime) -> list[dict] | None:
        """캐시에서 해당 주차 이벤트를 필터링해 반환. 캐시가 없으면 None."""
        if not self._all_events:
            return None
        ws = week_start.strftime("%Y-%m-%d")
        we = (week_start + timedelta(days=6)).strftime("%Y-%m-%d")
        return [e for e in self._all_events if ws <= e.get("date", "") <= we]

    def load_all_events(self):
        """FullCalendar의 전체 이벤트를 한 번에 로드한다."""
        self._poll_count = 0

        # 로그인 타이머가 남아있으면 확실히 정리
        if self._login_timer and self._login_timer.isActive():
            self._login_timer.stop()

        current = self._page.url().toString()
        if "MYscheduleMST" in current:
            QTimer.singleShot(500, self._poll_all_events)
        else:
            try:
                self._page.loadFinished.disconnect()
            except TypeError:
                pass
            self._page.loadFinished.connect(self._on_timetable_loaded)
            self._page.load(QUrl(TIMETABLE_URL))

    def _on_timetable_loaded(self, ok: bool):
        try:
            self._page.loadFinished.disconnect(self._on_timetable_loaded)
        except TypeError:
            pass
        self._page.loadFinished.connect(self._on_load_finished)

        if not ok:
            self.events_failed.emit("시간표 페이지 로드 실패")
            return

        # 세션 만료로 로그인 페이지로 리다이렉트된 경우
        url = self._page.url().toString()
        if "/login" in url:
            self.events_failed.emit("세션 만료")
            return

        QTimer.singleShot(500, self._poll_all_events)

    def _poll_all_events(self):
        """날짜 필터 없이 전체 clientEvents를 추출."""
        js = """
        (function() {
            try {
                var fcEl = document.querySelector('.fc');
                if (!fcEl) return JSON.stringify([]);
                var jq = window.jQuery || window.$;
                if (!jq) return JSON.stringify([]);
                var events = jq(fcEl).fullCalendar('clientEvents');
                if (!events || events.length === 0) return JSON.stringify([]);
                return JSON.stringify(events
                    .filter(function(e) { return !!e.start; })
                    .map(function(e) {
                        return {
                            title: e.title || '',
                            start: e.start.format('YYYY-MM-DDTHH:mm:ss'),
                            end:   e.end ? e.end.format('YYYY-MM-DDTHH:mm:ss') : '',
                            url:   e.url || ''
                        };
                    }));
            } catch(ex) {
                return JSON.stringify([{"error": String(ex)}]);
            }
        })()
        """
        self._page.runJavaScript(js, 0, self._on_all_events_result)

    def _on_all_events_result(self, result):
        try:
            events = json.loads(result) if isinstance(result, str) else (result or [])
        except (json.JSONDecodeError, TypeError):
            events = []

        if not events and self._poll_count < 10:
            self._poll_count += 1
            QTimer.singleShot(300, self._poll_all_events)
            return

        if events and len(events) == 1 and "error" in events[0]:
            self.events_failed.emit(events[0]["error"])
            return

        parsed = self._parse_events(events)
        self._all_events = parsed
        self._save_disk_cache(parsed)
        self.events_loaded.emit(parsed)

    # ── 이벤트 파싱 ─────────────────────────────────

    @staticmethod
    def _parse_events(raw_events: list) -> list:
        """FullCalendar 이벤트를 내부 형식으로 변환. URL에서 seq 파라미터 추출."""
        result = []
        for ev in raw_events:
            title_raw = ev.get("title", "")
            m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", title_raw)
            if m:
                title, professor = m.group(1).strip(), m.group(2).strip()
            else:
                title, professor = title_raw.strip(), ""

            start_str = ev.get("start", "")
            end_str = ev.get("end", "")
            try:
                start_dt = datetime.fromisoformat(start_str)
            except ValueError:
                continue
            try:
                end_dt = datetime.fromisoformat(end_str) if end_str else start_dt + timedelta(hours=1)
            except ValueError:
                end_dt = start_dt + timedelta(hours=1)

            # URL에서 lp_seq, curr_seq, aca_seq 추출
            # 패턴: showPopup(lp_seq, curr_seq, aca_seq) 또는 쿼리 파라미터
            url = ev.get("url", "")
            lp_seq = curr_seq = aca_seq = None
            seq_match = re.search(r"showPopup\((\d+),\s*(\d+),\s*(\d+)\)", url)
            if seq_match:
                lp_seq = seq_match.group(1)
                curr_seq = seq_match.group(2)
                aca_seq = seq_match.group(3)
            else:
                # 쿼리 파라미터 방식
                for param, key in [("lp_seq", "lp_seq"), ("curr_seq", "curr_seq"), ("aca_seq", "aca_seq")]:
                    pm = re.search(rf"{param}=(\d+)", url)
                    if pm:
                        if key == "lp_seq": lp_seq = pm.group(1)
                        elif key == "curr_seq": curr_seq = pm.group(1)
                        elif key == "aca_seq": aca_seq = pm.group(1)

            result.append({
                "title": title,
                "professor": professor,
                "day_of_week": start_dt.isoweekday(),
                "date": start_dt.strftime("%Y-%m-%d"),
                "start_hour": start_dt.hour,
                "start_min": start_dt.minute,
                "end_hour": end_dt.hour,
                "end_min": end_dt.minute,
                "url": url,
                "lp_seq": lp_seq,
                "curr_seq": curr_seq,
                "aca_seq": aca_seq,
            })
        return result

    # ── 수업 상세 로드 ──────────────────────────────

    def load_lesson_detail(self, lp_seq: str, curr_seq: str, aca_seq: str):
        """수업 상세 페이지를 로드하고 과목명, 강의실, 파일 목록을 추출한다."""
        url = f"{SCHEDULE_SHOW_URL}?lp_seq={lp_seq}&curr_seq={curr_seq}&aca_seq={aca_seq}"
        self._detail_page.loadFinished.connect(self._on_detail_page_loaded)
        self._detail_page.load(QUrl(url))

    def _on_detail_page_loaded(self, ok: bool):
        self._detail_page.loadFinished.disconnect(self._on_detail_page_loaded)
        if not ok:
            self.detail_failed.emit("상세 페이지 로드 실패")
            return

        # 세션 만료로 로그인 페이지로 리다이렉트된 경우
        url = self._detail_page.url().toString()
        if "/login" in url:
            self.detail_failed.emit("세션 만료")
            return

        # 1500ms 대기 후 JS 추출 (렌더링 대기)
        QTimer.singleShot(1500, self._extract_lesson_detail)

    def _extract_lesson_detail(self):
        js = """
        (function() {
            var subjectEl = document.getElementById('subject');
            var subject = '';
            if (subjectEl) {
                for (var i = 0; i < subjectEl.childNodes.length; i++) {
                    if (subjectEl.childNodes[i].nodeType === 3) {
                        subject = subjectEl.childNodes[i].textContent.trim();
                        if (subject) break;
                    }
                }
            }
            var room = '';
            var lis = document.querySelectorAll('ul.content-list li');
            for (var i = 0; i < lis.length; i++) {
                var t = lis[i].textContent.trim();
                if (t && t.indexOf('교시') === -1 && t.indexOf('~') === -1
                    && t !== '강의' && t !== '실습' && t !== '세미나' && t !== '시험') {
                    room = t;
                    break;
                }
            }
            var files = [];
            var links = document.querySelectorAll('#lesson_plan_data a[onclick*="attachEvent"]');
            for (var i = 0; i < links.length; i++) {
                var onclick = links[i].getAttribute('onclick') || '';
                var m = onclick.match(/attachEvent\\s*\\(\\s*'[^']*'\\s*,\\s*'([^']+)'\\s*,\\s*'([^']+)'\\s*,\\s*'(\\d+)'\\s*,\\s*'(\\d+)'/);
                if (m) {
                    files.push({path: m[1], name: m[2], attachSeq: m[3], dataSeq: m[4]});
                }
            }
            return JSON.stringify({subject: subject, room: room, files: files});
        })()
        """
        self._detail_page.runJavaScript(js, 0, self._on_detail_result)

    def _on_detail_result(self, result):
        try:
            data = json.loads(result) if isinstance(result, str) else {}
        except (json.JSONDecodeError, TypeError):
            data = {}

        if not data:
            self.detail_failed.emit("상세 정보 파싱 실패")
            return

        # 다운로드 URL 구성
        files = []
        for f in data.get("files", []):
            path = f.get("path", "")
            name = f.get("name", "")
            if not path.startswith("/ubladv_res"):
                path = "/ubladv_res" + path
            download_url = f"{FILE_DOWNLOAD_URL}?file_path={quote(path)}&file_name={quote(name)}"
            files.append({
                "name": name,
                "download_url": download_url,
                "attach_seq": f.get("attachSeq", ""),
                "data_seq": f.get("dataSeq", ""),
            })

        self.detail_loaded.emit({
            "subject": data.get("subject", ""),
            "room": data.get("room", ""),
            "files": files,
        })

    # ── 파일 다운로드 ──────────────────────────────

    def download_file(self, file_info: dict, save_dir: str = ""):
        """파일을 다운로드한다. read-receipt POST 후 GET."""
        if not save_dir:
            save_dir = str(Path.home() / "Downloads")

        self._pending_download = {
            "file_info": file_info,
            "save_dir": save_dir,
        }

        # Step 1: read-receipt POST (다운로드 허가에 필요)
        attach_seq = file_info.get("attach_seq", "")
        data_seq = file_info.get("data_seq", "")
        if attach_seq and data_seq:
            read_js = f"""
            (function() {{
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '{READ_RECEIPT_URL}', true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.send('lesson_attach_seq={attach_seq}&lesson_data_seq={data_seq}');
                return 'sent';
            }})()
            """
            self._detail_page.runJavaScript(read_js, 0, lambda _: QTimer.singleShot(500, self._start_download))
        else:
            self._start_download()

    def _start_download(self):
        """read-receipt 후 실제 다운로드 시작."""
        info = self._pending_download
        url = info["file_info"]["download_url"]
        self.download_started.emit(info["file_info"]["name"])
        # WebEngineView를 통해 다운로드 — 세션 쿠키가 자동으로 포함됨
        self._detail_page.download(QUrl(url))

    def _on_download_requested(self, download: QWebEngineDownloadRequest):
        """다운로드 요청 처리."""
        info = getattr(self, "_pending_download", None)
        if not info:
            download.cancel()
            return

        save_dir = info["save_dir"]
        file_name = info["file_info"]["name"]
        save_path = os.path.join(save_dir, file_name)

        # 중복 파일명 처리
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base} ({counter}){ext}"
            counter += 1

        download.setDownloadDirectory(os.path.dirname(save_path))
        download.setDownloadFileName(os.path.basename(save_path))
        download.isFinishedChanged.connect(
            lambda: self._on_download_finished(download, save_path)
        )
        download.accept()

    def _on_download_finished(self, download: QWebEngineDownloadRequest, save_path: str):
        if download.state() == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self.download_finished.emit(save_path)
        else:
            self.download_failed.emit(f"다운로드 실패: {download.state()}")

    def cleanup(self):
        """리소스 정리."""
        try:
            self._page.loadFinished.disconnect()
        except TypeError:
            pass
        self._view.close()
        self._detail_view.close()
