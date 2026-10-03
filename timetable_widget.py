"""데스크톱 시간표 위젯 — QPainter로 시간표 렌더링."""

from datetime import datetime, timedelta, date
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QPoint, QPointF, pyqtSignal, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetricsF, QPen, QBrush, QCursor,
    QPainterPath,
)

from config import Config
from variant import INVERT_BLOCK_COLOR

DAY_LABELS = ["월", "화", "수", "목", "금"]
EXAM_KEYWORDS = ["시험", "중간", "기말", "평가"]
# 키워드를 포함하지만 시험이 아닌 단어 — 매칭 전에 제거한다.
EXAM_EXCLUDE_WORDS = ["시험관"]
START_HOUR = 9
END_HOUR = 18
TOTAL_HOURS = END_HOUR - START_HOUR


@dataclass(frozen=True)
class ClassItem:
    title: str
    professor: str
    day_of_week: int   # 1=Mon..5=Fri
    date: str          # "YYYY-MM-DD"
    start_hour: int
    start_min: int
    end_hour: int
    end_min: int


@dataclass
class BlockLayout:
    x: float
    w: float
    y: float
    h: float


def ceil_to_30min(hour: int, minute: int) -> int:
    if minute == 0:
        return hour * 60
    elif minute <= 30:
        return hour * 60 + 30
    else:
        return (hour + 1) * 60


def class_key(title: str, date: str, start_hour: int, start_min: int) -> str:
    """수업 칸 하나를 가리키는 키 — 같은 과목이라도 날짜·시각이 다르면 별개."""
    return f"{date}|{start_hour:02d}:{start_min:02d}|{title}"


def is_exam(title: str) -> bool:
    cleaned = title
    for word in EXAM_EXCLUDE_WORDS:
        cleaned = cleaned.replace(word, "")
    return any(kw in cleaned for kw in EXAM_KEYWORDS)


# 색상 휠(RYB) ↔ RGB 색상각 대응표 — 미술 색상환 기준 보색을 얻기 위한 것.
# 노랑(RGB 60°)의 반대가 보라, 파랑 계열의 반대가 빨강 계열이 되도록 한다.
_RGB_HUES = [0.0, 20.0, 60.0, 120.0, 240.0, 300.0, 360.0]
_RYB_HUES = [0.0, 60.0, 120.0, 180.0, 240.0, 300.0, 360.0]


def _lerp_hue(v: float, xs: list[float], ys: list[float]) -> float:
    for i in range(len(xs) - 1):
        if xs[i] <= v <= xs[i + 1]:
            span = xs[i + 1] - xs[i]
            t = (v - xs[i]) / span if span else 0.0
            return ys[i] + (ys[i + 1] - ys[i]) * t
    return ys[-1]


def complement_color(base: QColor) -> QColor:
    """색상 휠 반대편 색 — 노랑↔보라, 파랑 계열↔빨강 계열."""
    h, s, v, a = base.getHsv()
    if h < 0:  # 무채색 — 돌릴 색상이 없다
        return QColor(base)
    ryb = (_lerp_hue(float(h), _RGB_HUES, _RYB_HUES) + 180.0) % 360.0
    out = QColor()
    out.setHsv(int(round(_lerp_hue(ryb, _RYB_HUES, _RGB_HUES))) % 360, s, v, a)
    return out


def exam_color(base: QColor, dark: bool) -> QColor:
    r, g, b = base.red(), base.green(), base.blue()
    if dark:
        return QColor(
            r + int((255 - r) * 0.20),
            g + int((255 - g) * 0.20),
            b + int((255 - b) * 0.20),
        )
    else:
        return QColor(int(r * 0.85), int(g * 0.85), int(b * 0.85))


def build_layout_map(
    classes: list[ClassItem],
    time_col_w: float, col_w: float,
    header_h: float, hour_h: float,
) -> dict[ClassItem, BlockLayout]:
    """겹치는 수업 레인 레이아웃 알고리즘."""
    result: dict[ClassItem, BlockLayout] = {}
    by_day: dict[int, list[ClassItem]] = {}
    for cls in classes:
        by_day.setdefault(cls.day_of_week, []).append(cls)

    for day, day_classes in by_day.items():
        col = day - 1
        if col < 0 or col > 4:
            continue
        col_x = time_col_w + col * col_w

        valid = []
        for cls in day_classes:
            s = ceil_to_30min(cls.start_hour, cls.start_min) - START_HOUR * 60
            e = ceil_to_30min(cls.end_hour, cls.end_min) - START_HOUR * 60
            if s >= 0 and e > s and s < TOTAL_HOURS * 60:
                valid.append(cls)

        sorted_cls = sorted(valid, key=lambda c: (c.start_hour * 60 + c.start_min, c.title))

        lane_end_times: list[int] = []
        lane_of: dict[ClassItem, int] = {}
        for cls in sorted_cls:
            cls_start = cls.start_hour * 60 + cls.start_min
            lane = -1
            for i, end_t in enumerate(lane_end_times):
                if end_t <= cls_start:
                    lane = i
                    break
            if lane == -1:
                lane = len(lane_end_times)
                lane_end_times.append(cls.end_hour * 60 + cls.end_min)
            else:
                lane_end_times[lane] = cls.end_hour * 60 + cls.end_min
            lane_of[cls] = lane

        for cls in valid:
            cls_s = cls.start_hour * 60 + cls.start_min
            cls_e = cls.end_hour * 60 + cls.end_min
            overlapping_lanes = []
            for other in valid:
                o_s = other.start_hour * 60 + other.start_min
                o_e = other.end_hour * 60 + other.end_min
                if cls_s < o_e and o_s < cls_e:
                    if other in lane_of:
                        overlapping_lanes.append(lane_of[other])
            total_lanes = (max(overlapping_lanes) + 1) if overlapping_lanes else 1

            lane = lane_of.get(cls, 0)
            gap = 1.0 if total_lanes > 1 else 0.0
            slot_w = (col_w - 2.0 - gap * (total_lanes - 1)) / total_lanes
            x = col_x + 1.0 + lane * (slot_w + gap)

            s = ceil_to_30min(cls.start_hour, cls.start_min) - START_HOUR * 60
            e = ceil_to_30min(cls.end_hour, cls.end_min) - START_HOUR * 60
            y1 = header_h + s / 60.0 * hour_h
            y2 = header_h + min(e, TOTAL_HOURS * 60) / 60.0 * hour_h
            bh = max(y2 - y1 - 1.0, 0.0)
            if bh >= 3.0:
                result[cls] = BlockLayout(x, max(slot_w, 2.0), y1, bh)

    return result


class TimetableDesktopWidget(QWidget):
    """투명 프레임리스 데스크톱 위젯."""

    week_changed = pyqtSignal(datetime)
    class_clicked = pyqtSignal(dict)  # 수업 클릭 시 원본 dict 전달

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.classes: list[ClassItem] = []
        self._raw_classes: list[dict] = []  # 원본 dict (seq 정보 포함)
        self.week_offset = 0
        # week_offset이 기준 삼았던 "실제 달력상 이번 주 월요일".
        # 앱을 켜둔 채 주가 넘어가면 넘겨봤던 주가 새 현재 주에 얹혀
        # 한 주 더 밀리므로, 앵커가 달라지면 offset을 0으로 되돌린다.
        self._week_anchor = self._real_week_monday()
        self._layout_map: dict[ClassItem, BlockLayout] = {}

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setGeometry(
            config["widget_x"], config["widget_y"],
            config["widget_w"], config["widget_h"],
        )
        self.setMinimumSize(300, 300)

        self._drag_pos: Optional[QPoint] = None
        self._resizing = False
        self._resize_edge = 0
        self._resize_start_geo = None
        self._resize_start_pos = None
        self._click_start_pos: Optional[QPointF] = None

    def _font(self, size: int, bold: bool = False) -> QFont:
        """설정된 폰트 패밀리로 QFont 생성."""
        family = self.config["font_family"]
        f = QFont(family, max(size, 6))
        f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        if bold:
            f.setBold(True)
        return f

    def _real_week_monday(self) -> datetime:
        """offset과 무관한, 오늘이 속한 주의 월요일."""
        today = datetime.now()
        monday = today - timedelta(days=today.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)

    def current_week_start(self) -> datetime:
        return self._real_week_monday() + timedelta(weeks=self.week_offset)

    def set_classes(self, classes: list[dict]):
        """이벤트 데이터 설정. 원본 dict를 보존한다."""
        self._raw_classes = classes
        self.classes = []
        self._layout_map = {}  # 즉시 클리어하여 stale 클릭 방지
        filter_mode = self.config["class_filter"]
        for c in classes:
            title = c.get("title", "")
            upper = title.upper()
            if filter_mode != "all":
                if "AB" in upper or "AB 반" in upper or "A/B" in upper:
                    pass
                elif "A반" in upper or "A 반" in upper:
                    if filter_mode != "A":
                        continue
                elif "B반" in upper or "B 반" in upper:
                    if filter_mode != "B":
                        continue

            self.classes.append(ClassItem(
                title=title,
                professor=c.get("professor", ""),
                day_of_week=c.get("day_of_week", 1),
                date=c.get("date", ""),
                start_hour=c.get("start_hour", 9),
                start_min=c.get("start_min", 0),
                end_hour=c.get("end_hour", 10),
                end_min=c.get("end_min", 0),
            ))
        self.update()

    @staticmethod
    def _raw_key(class_info: dict) -> str:
        return class_key(
            class_info.get("title", ""), class_info.get("date", ""),
            class_info.get("start_hour", 0), class_info.get("start_min", 0),
        )

    def is_class_inverted(self, class_info: dict) -> bool:
        return self._raw_key(class_info) in (self.config["inverted_blocks"] or [])

    def set_class_inverted(self, class_info: dict, inverted: bool):
        """수업 칸 하나의 색 반전 — 설정에 저장하고 즉시 다시 그린다."""
        key = self._raw_key(class_info)
        keys = list(self.config["inverted_blocks"] or [])
        if inverted and key not in keys:
            keys.append(key)
        elif not inverted and key in keys:
            keys.remove(key)
        else:
            return
        self.config["inverted_blocks"] = keys
        self.config.save()
        self.update()

    def _find_raw_class(self, cls: ClassItem) -> dict | None:
        """ClassItem에 대응하는 원본 dict를 찾는다."""
        for raw in self._raw_classes:
            if (raw.get("title") == cls.title
                    and raw.get("date") == cls.date
                    and raw.get("start_hour") == cls.start_hour
                    and raw.get("start_min") == cls.start_min):
                return raw
        return None

    def _hit_test(self, pos: QPointF) -> ClassItem | None:
        """pos가 어떤 수업 블록 위에 있는지 확인."""
        for cls, layout in self._layout_map.items():
            rect = QRectF(layout.x, layout.y, layout.w, layout.h)
            if rect.contains(pos):
                return cls
        return None

    def _clear_for_week_change(self):
        """주 이동 직전 — stale 블록 클릭 방지."""
        self.classes = []
        self._raw_classes = []
        self._layout_map = {}

    def go_prev_week(self):
        self._clear_for_week_change()
        self.week_offset -= 1
        self._week_anchor = self._real_week_monday()
        self.week_changed.emit(self.current_week_start())

    def go_next_week(self):
        self._clear_for_week_change()
        self.week_offset += 1
        self._week_anchor = self._real_week_monday()
        self.week_changed.emit(self.current_week_start())

    def go_this_week(self):
        self._week_anchor = self._real_week_monday()
        if self.week_offset == 0:
            return
        self._clear_for_week_change()
        self.week_offset = 0
        self.week_changed.emit(self.current_week_start())

    def sync_week_to_today(self):
        """실제 달력상 주가 바뀌었으면 이번 주로 되돌린다.

        앱을 며칠씩 켜두는 상주 위젯이라, 다음 주를 보던 상태로 주 경계를
        넘기면 현재 주가 이동한 만큼 표시 주차가 한 주 더 밀린다.
        """
        monday = self._real_week_monday()
        if monday == self._week_anchor:
            return
        self._week_anchor = monday
        if self.week_offset == 0:
            return
        self._clear_for_week_change()
        self.week_offset = 0
        self.week_changed.emit(self.current_week_start())

    # ── 그리기 ──────────────────────────────────────

    def paintEvent(self, event):
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        dark = self.config["dark_mode"]
        bg_alpha = self.config["bg_alpha"]
        block_alpha = self.config["block_alpha"]
        text_scale = self.config["text_size"] / 100.0
        block_color = QColor(self.config["block_color"])
        exam_hl = self.config["exam_highlight"]

        bg_val = 0 if dark else 255
        bg_color = QColor(bg_val, bg_val, bg_val, bg_alpha)

        header_h = h * 0.03
        time_col_w = header_h
        col_w = (w - time_col_w) / 5.0
        hour_h = (h - header_h) / TOTAL_HOURS

        text_sm = h * 0.024 * text_scale
        text_xs = h * 0.022 * text_scale

        # 배경 (둥근 모서리)
        radius = 10.0
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
        p.setClipPath(bg_path)
        p.fillRect(0, 0, w, h, bg_color)

        # 오늘 컬럼 하이라이트
        today = date.today()
        week_start = self.current_week_start().date()
        week_end = week_start + timedelta(days=6)
        if week_start <= today <= week_end:
            today_dow = today.isoweekday()
            if 1 <= today_dow <= 5:
                hl_alpha = 40 if dark else 25
                hl_color = QColor(block_color.red(), block_color.green(), block_color.blue(), hl_alpha)
                x = time_col_w + (today_dow - 1) * col_w
                p.fillRect(QRectF(x, 0, col_w, h), hl_color)

        grid_color = QColor("#3A3A3A") if dark else QColor("#E0E0E0")
        text_color = QColor("#AAAAAA") if dark else QColor("#666666")

        # 헤더
        header_font = self._font(int(text_sm))
        header_font_bold = self._font(int(text_sm), bold=True)

        for i in range(5):
            d = week_start + timedelta(days=i)
            cx = time_col_w + i * col_w + col_w / 2
            cy = header_h * 0.45
            label = f"{DAY_LABELS[i]} {d.month}/{d.day}"
            is_today = (d == today)
            if is_today:
                p.setFont(header_font_bold)
                p.setPen(QColor(Qt.GlobalColor.white) if dark else QColor("#555555"))
            else:
                p.setFont(header_font)
                p.setPen(text_color)
            fm = QFontMetricsF(p.font())
            tw = fm.horizontalAdvance(label)
            p.drawText(QPointF(cx - tw / 2, cy + fm.ascent() / 2), label)

        # 그리드
        grid_pen = QPen(grid_color, 0.8)
        p.setPen(grid_pen)
        for i in range(6):
            x = time_col_w + i * col_w
            p.drawLine(QPointF(x, header_h), QPointF(x, h))
        for hr in range(TOTAL_HOURS + 1):
            y = header_h + hr * hour_h
            p.drawLine(QPointF(time_col_w, y), QPointF(w, y))

        # 시간 축
        time_font = self._font(int(text_xs))
        p.setFont(time_font)
        p.setPen(text_color)
        fm = QFontMetricsF(time_font)
        for hr in range(TOTAL_HOURS + 1):
            y = header_h + hr * hour_h + fm.ascent() * 0.9
            label = str(START_HOUR + hr)
            tw = fm.horizontalAdvance(label)
            p.drawText(QPointF(time_col_w - tw - 2, y), label)

        # 네비게이션 화살표
        nav_font = self._font(int(text_sm * 1.2), bold=True)
        p.setFont(nav_font)
        p.setPen(text_color)
        p.drawText(QPointF(2, header_h * 0.75), "◀")
        nav_fm = QFontMetricsF(nav_font)
        p.drawText(QPointF(w - nav_fm.horizontalAdvance("▶") - 2, header_h * 0.75), "▶")

        # 수업 블록
        if not self.classes:
            self._layout_map = {}
            p.setFont(self._font(max(int(h * 0.025), 10)))
            p.setPen(text_color)
            msg = "시간표 로딩 중…" if not hasattr(self, '_loaded') else "이번 주 수업이 없습니다"
            fm = QFontMetricsF(p.font())
            tw = fm.horizontalAdvance(msg)
            p.drawText(QPointF(w / 2 - tw / 2, h / 2), msg)
            p.end()
            return

        self._loaded = True
        self._layout_map = build_layout_map(self.classes, time_col_w, col_w, header_h, hour_h)

        inverted_keys = set(self.config["inverted_blocks"] or [])

        title_font = self._font(int(text_xs), bold=True)
        prof_font = self._font(int(text_xs * 0.88))
        title_fm = QFontMetricsF(title_font)
        prof_fm = QFontMetricsF(prof_font)
        title_line_h = title_fm.height()
        prof_line_h = prof_fm.height()

        for cls in self.classes:
            layout = self._layout_map.get(cls)
            if not layout:
                continue

            cls_key = class_key(cls.title, cls.date, cls.start_hour, cls.start_min)
            marked = cls_key in inverted_keys
            base_color = (complement_color(block_color)
                          if marked and INVERT_BLOCK_COLOR else block_color)
            if exam_hl and is_exam(cls.title):
                bc = exam_color(base_color, dark)
            else:
                bc = QColor(base_color)
            bc.setAlpha(block_alpha)

            rect = QRectF(layout.x, layout.y, layout.w, layout.h)
            path = QPainterPath()
            path.addRoundedRect(rect, 3, 3)
            p.fillPath(path, QBrush(bc))

            pad = 3.0
            text_w = layout.w - 2 * pad
            if text_w < 2:
                continue

            has_prof = bool(cls.professor)
            prof_space = prof_line_h + 4 if has_prof else 0
            title_max_h = max(layout.h - 2 * pad - prof_space, title_line_h)

            p.setFont(title_font)
            p.setPen(QColor(Qt.GlobalColor.white))
            p.save()
            p.setClipRect(QRectF(layout.x + pad, layout.y + pad, text_w, title_max_h))
            words = cls.title
            lines = []
            while words:
                for end in range(len(words), 0, -1):
                    if title_fm.horizontalAdvance(words[:end]) <= text_w:
                        lines.append(words[:end])
                        words = words[end:]
                        break
                else:
                    lines.append(words[0])
                    words = words[1:]
            y_offset = layout.y + pad + title_fm.ascent()
            actual_title_h = 0.0
            for line in lines:
                if y_offset - layout.y - pad > title_max_h:
                    break
                p.drawText(QPointF(layout.x + pad, y_offset), line)
                actual_title_h = y_offset - layout.y - pad + title_fm.descent()
                y_offset += title_line_h
            p.restore()

            if has_prof:
                prof_y = layout.y + pad + min(actual_title_h, title_max_h) + 4
                if prof_y + prof_line_h < layout.y + layout.h:
                    p.setFont(prof_font)
                    prof_color = QColor(Qt.GlobalColor.white)
                    prof_color.setAlpha(210)
                    p.setPen(prof_color)
                    p.drawText(QPointF(layout.x + pad, prof_y + prof_fm.ascent()), cls.professor)

        p.end()

    # ── 마우스 이벤트 ───────────────────────────────

    def _edge_at(self, pos: QPointF) -> int:
        margin = 8
        edge = 0
        if pos.x() < margin:
            edge |= 1
        if pos.x() > self.width() - margin:
            edge |= 2
        if pos.y() < margin:
            edge |= 4
        if pos.y() > self.height() - margin:
            edge |= 8
        return edge

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()

            header_h = self.height() * 0.03
            time_col_w = header_h
            if pos.y() < header_h:
                if pos.x() < time_col_w:
                    self.go_prev_week()
                    return
                elif pos.x() > self.width() - time_col_w:
                    self.go_next_week()
                    return

            self._click_start_pos = pos

            # 위치 잠금 — 이동·크기조절은 막되, 수업 클릭은 계속 동작
            if self.config["lock_position"]:
                return

            edge = self._edge_at(pos)
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = QCursor.pos()
            else:
                self._drag_pos = QCursor.pos() - self.pos()

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_start_geo:
            delta = QCursor.pos() - self._resize_start_pos
            geo = self._resize_start_geo
            x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
            dx, dy = int(delta.x()), int(delta.y())

            if self._resize_edge & 1:
                x += dx; w -= dx
            if self._resize_edge & 2:
                w += dx
            if self._resize_edge & 4:
                y += dy; h -= dy
            if self._resize_edge & 8:
                h += dy

            w = max(w, self.minimumWidth())
            h = max(h, self.minimumHeight())
            self.setGeometry(x, y, w, h)
            self.update()
        elif self._drag_pos is not None:
            # QCursor.pos()와 self.pos()는 모두 QPoint → 차이도 QPoint, 변환 불필요
            self.move(QCursor.pos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        was_resizing = self._resizing
        click_start = self._click_start_pos

        self._drag_pos = None
        self._resizing = False
        self._resize_edge = 0
        self._click_start_pos = None

        # 위치/크기 저장 — 실제로 변경된 경우에만
        geo = self.geometry()
        gx, gy, gw, gh = geo.x(), geo.y(), geo.width(), geo.height()
        if (gx != self.config["widget_x"] or gy != self.config["widget_y"]
                or gw != self.config["widget_w"] or gh != self.config["widget_h"]):
            self.config["widget_x"] = gx
            self.config["widget_y"] = gy
            self.config["widget_w"] = gw
            self.config["widget_h"] = gh
            self.config.save()

        # 클릭 판정 — 이동 거리가 5px 이내면 클릭으로 판정
        if event.button() == Qt.MouseButton.LeftButton and click_start and not was_resizing:
            release_pos = event.position()
            dx = abs(release_pos.x() - click_start.x())
            dy = abs(release_pos.y() - click_start.y())
            if dx < 5 and dy < 5:
                cls = self._hit_test(release_pos)
                if cls:
                    raw = self._find_raw_class(cls)
                    if raw:
                        self.class_clicked.emit(raw)

    def mouseDoubleClickEvent(self, event):
        pos = event.position()
        # 수업 블록 위에서 더블클릭하면 무시
        if self._hit_test(pos):
            return
        # 화살표 영역 더블클릭은 주 이동 (연타 지원)
        header_h = self.height() * 0.03
        time_col_w = header_h
        if pos.y() < header_h:
            if pos.x() < time_col_w:
                self.go_prev_week()
                return
            elif pos.x() > self.width() - time_col_w:
                self.go_next_week()
                return
        self.go_this_week()
