"""크래시 로깅 + 전역 예외 처리.

- 로그를 ~/.mlms_windows/logs/mlms.log 에 기록한다 (1MB x 5개 회전).
- 처리되지 않은 예외를 잡아 로그에 남긴다. Qt 슬롯 안에서 난 예외는
  로그만 남기고 정상 리턴하므로 앱이 죽지 않는다.
- 네이티브 크래시(세그폴트 등)는 faulthandler로 fault.log 에 기록한다.
"""

import faulthandler
import logging
import logging.handlers
import sys
import traceback
from pathlib import Path

LOG_DIR = Path.home() / ".mlms_windows" / "logs"
LOG_FILE = LOG_DIR / "mlms.log"
FAULT_FILE = LOG_DIR / "fault.log"

log = logging.getLogger("mlms")

# faulthandler가 쓰는 파일 핸들 — 가비지 컬렉션되지 않도록 모듈 레벨에 보관
_fault_fp = None


def setup_logging() -> Path:
    """파일 + 콘솔 로깅을 설정한다. 로그 파일 경로를 반환한다. (중복 호출 안전)"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    log.setLevel(logging.DEBUG)
    if log.handlers:
        return LOG_FILE  # 이미 설정됨

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 파일 핸들러 — 1MB x 5개 회전
    try:
        fh = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass

    # 콘솔 핸들러 — 실제 출력 스트림이 있을 때만 (windowed exe에서는 stderr가 None)
    if sys.stderr is not None:
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(fmt)
        log.addHandler(ch)

    # 네이티브 크래시 추적 (Qt C++ 레이어 세그폴트 등)
    global _fault_fp
    try:
        _fault_fp = open(FAULT_FILE, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_fp)
    except OSError:
        pass

    return LOG_FILE


def install_excepthook():
    """처리되지 않은 예외를 잡아 로그에 남긴다.

    Qt 슬롯 안에서 난 예외는 여기서 처리(로그 기록 후 정상 리턴)되므로
    PyQt가 앱을 종료하지 않고 이벤트 루프를 계속 돌린다.
    """

    def _handle(exc_type, exc_value, exc_tb):
        # KeyboardInterrupt(Ctrl+C)는 정상 종료로 취급
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.critical("처리되지 않은 예외:\n%s", tb_text)

    sys.excepthook = _handle
