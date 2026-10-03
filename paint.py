import sys
import json
import math
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QPoint, QPointF, QRect, QRectF, QSize, QTimer, Signal
from PySide6.QtGui import (
    QImage, QPainter, QPen, QColor, QFont, QFontDatabase, QIcon, QPixmap,
    QKeySequence, QShortcut, QEventPoint,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QPushButton, QLabel, QSpinBox, QSlider, QListWidget,
    QListWidgetItem, QScrollArea, QFileDialog, QColorDialog, QInputDialog,
    QMessageBox, QMenu, QButtonGroup, QPlainTextEdit, QCheckBox, QScroller,
    QStyledItemDelegate, QSizePolicy,
)

# ------------------------------------------------------------
# 保存場所:  C:\Users\あなた\PeTitPaintProjects
# ------------------------------------------------------------
OLD_BASE = Path.home() / "MyPaintProjects"      # 前の名前のフォルダ(あれば引っ越し)
BASE = Path.home() / "PeTitPaintProjects"
if OLD_BASE.exists() and not BASE.exists():
    try:
        OLD_BASE.rename(BASE)
    except Exception:
        pass
BASE.mkdir(parents=True, exist_ok=True)

# 追加したフォントの置き場所(.ttf / .otf を入れると起動時に自動で読み込まれます)
FONT_DIR = BASE / "fonts"
FONT_DIR.mkdir(parents=True, exist_ok=True)

# ゆる系・手書き風のおすすめフォント(PCに入っているものだけ上に ★ つきで出ます)
YURU_FONTS = [
    "Yomogi", "Hachi Maru Pop", "Zen Kurenaido", "Yusei Magic", "Kiwi Maru",
    "Mochiy Pop One", "Potta One", "RocknRoll One", "Reggae One", "Dela Gothic One",
    "Klee One", "HG丸ｺﾞｼｯｸM-PRO", "HGP創英角ﾎﾟｯﾌﾟ体", "UD デジタル 教科書体 N-R",
    "Ink Free", "Segoe Print", "Comic Sans MS",
]


def load_user_fonts():
    for f in FONT_DIR.iterdir():
        if f.suffix.lower() in (".ttf", ".otf"):
            QFontDatabase.addApplicationFont(str(f))

STYLE = """
QWidget { background: #1e1f22; color: #e6e6e6; font-size: 14px; }
QPushButton { background: #2b2d31; border: 1px solid #3a3d42; border-radius: 8px; padding: 8px 12px; }
QPushButton:hover { background: #383b41; }
QPushButton:checked { background: #2ee6d0; color: #00201c; font-weight: bold; border: 1px solid #2ee6d0; }
QPushButton#hero {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2ee6d0, stop:1 #3a6bff);
    color: #06222a; font-size: 26px; font-weight: bold; border: none; border-radius: 16px;
}
QPushButton#hero:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5af0de, stop:1 #5a85ff); }
QPushButton#danger:hover { background: #7a2b2b; }
QListWidget { background: #1e1f22; border: none; }
QListWidget::item { border-radius: 8px; padding: 6px; }
QListWidget::item:selected { background: #2c4f4b; color: white; }
QPlainTextEdit, QSpinBox { background: #2b2d31; border: 1px solid #3a3d42; border-radius: 6px; padding: 4px; }
QScrollArea { border: none; }
QMenu { border: 1px solid #3a3d42; }
QMenu::item { padding: 10px 28px; }
QMenu::item:selected { background: #2c4f4b; }
QLabel#title { font-size: 28px; font-weight: bold; }
QLabel#section { font-size: 15px; font-weight: bold; color: #9aa0a6; }
QLabel#status { background: #2b2d31; border-radius: 8px; padding: 10px; font-size: 15px; font-weight: bold; }
"""


# ------------------------------------------------------------
# プロジェクトの保存・読み込み
# ------------------------------------------------------------
def save_project(dir_path, name, image):
    d = Path(dir_path)
    d.mkdir(parents=True, exist_ok=True)
    image.save(str(d / "image.png"))
    thumb = image.scaled(440, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    thumb.save(str(d / "thumb.png"))
    meta = {
        "name": name,
        "width": image.width(),
        "height": image.height(),
        "modified": datetime.now().isoformat(timespec="seconds"),
    }
    (d / "project.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def load_projects():
    items = []
    for d in BASE.iterdir():
        meta = d / "project.json"
        if d.is_dir() and meta.exists():
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except Exception:
                continue
            data["dir"] = str(d)
            items.append(data)
    items.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return items


# ------------------------------------------------------------
# キャンバス(絵を描く場所)
# ------------------------------------------------------------
class Canvas(QWidget):
    stroke_finished = Signal()
    zoom_changed = Signal(float)

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(200, 200)
        self.zoom = 1.0
        self.offset = QPointF(0, 0)   # 画像の左上が表示される位置(自由に動かせる)
        self.autofit = True           # Trueの間は、画面の大きさが変わっても全体表示を保つ
        self.pan = None               # 移動中の情報
        self.touch_mode = None        # None / draw / move / pinch / done
        self.color = QColor("black")
        self.pen_size = 6
        self.eraser_size = 30
        self.tool = "pen"             # "move" / "pen" / "eraser" / "text"
        self.text = ""
        self.font_size = 40
        self.font_family = ""         # 空 = 標準フォント
        self.last = None
        self.hover = None
        self.undo_stack = []
        self.redo_stack = []
        self.image = QImage(800, 600, QImage.Format_ARGB32)
        self.image.fill(Qt.white)
        self.set_tool("pen")

    @property
    def brush_size(self):
        """今のツールの太さ(ペンと消しゴムは別々)"""
        return self.eraser_size if self.tool == "eraser" else self.pen_size

    def set_image(self, image):
        self.image = image
        self.undo_stack = []
        self.redo_stack = []
        self.autofit = True
        self.fit_view()

    def set_tool(self, tool):
        self.tool = tool
        cursors = {"move": Qt.OpenHandCursor, "pen": Qt.CrossCursor,
                   "eraser": Qt.BlankCursor, "text": Qt.IBeamCursor}
        self.setCursor(cursors[tool])
        self.update()

    def refresh(self):
        self.update()

    # ---- 表示位置・ズーム ----
    def to_image(self, wpos):
        return (wpos - self.offset) / self.zoom

    def fit_zoom(self):
        w, h = self.image.width(), self.image.height()
        return max(0.05, min((self.width() - 40) / w, (self.height() - 40) / h, 1.0))

    def fit_view(self):
        z = self.fit_zoom()
        w, h = self.image.width(), self.image.height()
        self.zoom = z
        self.offset = QPointF((self.width() - w * z) / 2, (self.height() - h * z) / 2)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def resizeEvent(self, e):
        if self.autofit:
            self.fit_view()
        super().resizeEvent(e)

    def set_zoom_at(self, new_zoom, anchor):
        """anchor(画面上の点)の下にある絵の場所を動かさずにズーム"""
        new_zoom = max(0.05, min(new_zoom, 16.0))
        ip = (anchor - self.offset) / self.zoom
        self.zoom = new_zoom
        self.offset = anchor - ip * new_zoom
        self.autofit = False
        self.zoom_changed.emit(self.zoom)
        self.update()

    def zoom_center(self, new_zoom):
        self.set_zoom_at(new_zoom, QPointF(self.width() / 2, self.height() / 2))

    def do_pan(self, pos):
        start, off0 = self.pan
        self.offset = off0 + (pos - start)
        self.autofit = False
        self.update()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps == 0:
            e.ignore()
            return
        self.set_zoom_at(self.zoom * (1.15 ** steps), e.position())
        e.accept()

    # ---- 表示 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#2a2c30"))
        p.save()
        p.translate(self.offset)
        p.scale(self.zoom, self.zoom)
        p.setRenderHint(QPainter.SmoothPixmapTransform, self.zoom < 1.0)
        p.drawImage(0, 0, self.image)
        p.restore()
        w, h = self.image.width() * self.zoom, self.image.height() * self.zoom
        p.setPen(QPen(QColor("#555a60"), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(self.offset.x(), self.offset.y(), w, h))
        # ペン・消しゴムの範囲を丸い線で表示
        if self.tool in ("pen", "eraser") and self.hover is not None:
            p.setRenderHint(QPainter.Antialiasing)
            r = max(self.brush_size * self.zoom / 2, 2.0)
            p.setPen(QPen(QColor("white"), 3))
            p.drawEllipse(self.hover, r, r)
            p.setPen(QPen(QColor("black"), 1.5))
            p.drawEllipse(self.hover, r, r)

    # ---- マウス操作 ----
    def mousePressEvent(self, e):
        move_drag = e.button() == Qt.LeftButton and self.tool == "move"
        if e.button() == Qt.MiddleButton or move_drag:
            self.pan = (QPointF(e.position()), QPointF(self.offset))
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton:
            return
        pos = self.to_image(e.position())
        self.push_undo()
        if self.tool == "text":
            self.place_text(pos)
            self.stroke_finished.emit()
            return
        self.last = pos
        self.draw_line(pos, pos)

    def mouseMoveEvent(self, e):
        if self.pan is not None:
            self.do_pan(e.position())
            return
        self.hover = e.position()
        if self.last is not None:
            now = self.to_image(e.position())
            self.draw_line(self.last, now)
            self.last = now
        if self.tool in ("pen", "eraser"):
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() in (Qt.MiddleButton, Qt.LeftButton) and self.pan is not None:
            self.pan = None
            self.set_tool(self.tool)
            return
        if self.last is not None:
            self.last = None
            self.stroke_finished.emit()

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    # ---- タッチ操作(指1本で描く/動かす、指2本でピンチ拡大縮小+移動) ----
    def event(self, e):
        if e.type() in (QEvent.TouchBegin, QEvent.TouchUpdate,
                        QEvent.TouchEnd, QEvent.TouchCancel):
            self.handle_touch(e)
            e.accept()
            return True
        return super().event(e)

    def handle_touch(self, e):
        active = [p for p in e.points() if p.state() != QEventPoint.State.Released]
        n = len(active)
        if n == 0 or e.type() == QEvent.TouchCancel:
            if self.last is not None:
                self.last = None
                self.stroke_finished.emit()
            if self.touch_mode == "move":
                self.pan = None
            self.touch_mode = None
            self.hover = None
            self.update()
            return
        if n >= 2:
            a, b = active[0].position(), active[1].position()
            dist = max(1.0, math.hypot(a.x() - b.x(), a.y() - b.y()))
            mid = (a + b) / 2
            if self.touch_mode != "pinch":
                if self.last is not None:          # 描きかけの線は取り消す
                    if self.undo_stack:
                        self.image = self.undo_stack.pop()
                    self.last = None
                self.touch_mode = "pinch"
                self.pan = None
                self.hover = None
                self.pinch_ip = (mid - self.offset) / self.zoom
                self.pinch_zoom0 = self.zoom
                self.pinch_dist0 = dist
                self.update()
            else:
                z = max(0.05, min(self.pinch_zoom0 * dist / self.pinch_dist0, 16.0))
                self.zoom = z
                self.offset = mid - self.pinch_ip * z
                self.autofit = False
                self.zoom_changed.emit(z)
                self.update()
            return
        # 指1本
        if self.touch_mode in ("pinch", "done"):
            return
        pos_w = active[0].position()
        if self.tool == "move":
            if self.touch_mode is None:
                self.touch_mode = "move"
                self.pan = (QPointF(pos_w), QPointF(self.offset))
            elif self.pan is not None:
                self.do_pan(pos_w)
            return
        pos = self.to_image(pos_w)
        self.hover = pos_w
        if self.touch_mode is None:
            self.touch_mode = "draw"
            self.push_undo()
            if self.tool == "text":
                self.place_text(pos)
                self.stroke_finished.emit()
                self.touch_mode = "done"
                return
            self.last = pos
            self.draw_line(pos, pos)
        elif self.last is not None:
            self.draw_line(self.last, pos)
            self.last = pos
        self.update()

    # ---- 描画 ----
    def draw_line(self, a, b):
        p = QPainter(self.image)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor("white") if self.tool == "eraser" else self.color
        p.setPen(QPen(color, self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(a, b)
        p.end()
        self.update()

    def place_text(self, pos):
        if not self.text.strip():
            return
        p = QPainter(self.image)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        font = QFont(self.font_family) if self.font_family else QFont()
        font.setPixelSize(self.font_size)
        p.setFont(font)
        p.setPen(self.color)
        rect = QRectF(pos.x(), pos.y(), self.image.width(), self.image.height())
        p.drawText(rect, Qt.AlignLeft | Qt.AlignTop, self.text)
        p.end()
        self.update()

    # ---- 元に戻す / やり直す ----
    def push_undo(self):
        self.undo_stack.append(self.image.copy())
        # 大きい画像でもメモリを使いすぎないよう、戻せる回数を自動調整
        per = max(1, self.image.width() * self.image.height() * 4)
        limit = max(3, min(30, 400_000_000 // per))
        while len(self.undo_stack) > limit:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.image.copy())
            self.image = self.undo_stack.pop()
            self.update()
            self.stroke_finished.emit()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.image.copy())
            self.image = self.redo_stack.pop()
            self.update()
            self.stroke_finished.emit()


# ------------------------------------------------------------
# 編集画面(中央キャンバス + 右パネル)
# ------------------------------------------------------------
class Editor(QWidget):
    go_home = Signal()

    TOOL_NAMES = {"move": "なでなで(移動)", "pen": "ペン", "eraser": "消しゴム", "text": "テキスト"}
    PRESETS = ["#000000", "#ffffff", "#e53935", "#fb8c00", "#fdd835", "#43a047",
               "#1e88e5", "#8e24aa", "#6d4c41", "#757575", "#f48fb1", "#80deea"]

    def __init__(self):
        super().__init__()
        self.dir = None
        self.name = ""
        self.prev_zoom = None
        self.canvas = Canvas()

        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.timeout.connect(self.save)
        self.canvas.stroke_finished.connect(lambda: self.autosave.start(1500))

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- 左側: 上バー + キャンバス ---
        left = QVBoxLayout()
        left.setContentsMargins(10, 10, 10, 10)
        bar = QHBoxLayout()
        b_home = QPushButton("◀ ホーム")
        b_home.clicked.connect(self.go_home.emit)
        self.name_label = QLabel("")
        self.name_label.setObjectName("section")
        b_fit = QPushButton("全体表示")
        b_fit.clicked.connect(lambda _=False: self.fit(True))
        b_zout = QPushButton("－")
        b_zout.clicked.connect(lambda _=False: self.canvas.zoom_center(self.canvas.zoom / 1.25))
        b_zin = QPushButton("＋")
        b_zin.clicked.connect(lambda _=False: self.canvas.zoom_center(self.canvas.zoom * 1.25))
        self.zoom_btn = QPushButton("100%")
        self.zoom_btn.setMinimumWidth(76)
        self.zoom_btn.setToolTip("クリックで等倍(100%)")
        self.zoom_btn.clicked.connect(lambda _=False: self.canvas.zoom_center(1.0))
        self.canvas.zoom_changed.connect(lambda z: self.zoom_btn.setText(f"{round(z * 100)}%"))
        b_undo = QPushButton("元に戻す")
        b_undo.clicked.connect(self.canvas.undo)
        b_redo = QPushButton("やり直す")
        b_redo.clicked.connect(self.canvas.redo)
        b_export = QPushButton("書き出し(PNG/JPG)")
        b_export.clicked.connect(self.export_image)
        bar.addWidget(b_home)
        bar.addWidget(self.name_label)
        bar.addStretch(1)
        for b in (b_zout, self.zoom_btn, b_zin, b_fit, b_undo, b_redo, b_export):
            bar.addWidget(b)
        left.addLayout(bar)

        left.addWidget(self.canvas, 1)
        root.addLayout(left, 1)

        # --- 右パネル ---
        panel = QWidget()
        panel.setStyleSheet("QWidget#panel { background: #25272b; }")
        panel.setObjectName("panel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(14, 14, 22, 14)
        pl.setSpacing(8)

        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        pl.addWidget(self.status)

        t = QLabel("ツール")
        t.setObjectName("section")
        pl.addWidget(t)
        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)
        self.tool_buttons = {}
        for key in ("move", "pen", "eraser", "text"):
            b = QPushButton(self.TOOL_NAMES[key])
            b.setCheckable(True)
            b.setMinimumHeight(40)
            b.clicked.connect(lambda _=False, k=key: self.set_tool(k))
            self.tool_group.addButton(b)
            self.tool_buttons[key] = b
            pl.addWidget(b)
        self.tool_buttons["pen"].setChecked(True)

        self.pen_label = QLabel("")
        pl.addWidget(self.pen_label)
        self.pen_slider = QSlider(Qt.Horizontal)
        self.pen_slider.setRange(1, 100)
        self.pen_slider.setValue(self.canvas.pen_size)
        self.pen_slider.valueChanged.connect(self.on_pen_size)
        pl.addWidget(self.pen_slider)
        self.eraser_label = QLabel("")
        pl.addWidget(self.eraser_label)
        self.eraser_slider = QSlider(Qt.Horizontal)
        self.eraser_slider.setRange(1, 200)
        self.eraser_slider.setValue(self.canvas.eraser_size)
        self.eraser_slider.valueChanged.connect(self.on_eraser_size)
        pl.addWidget(self.eraser_slider)

        c = QLabel("色")
        c.setObjectName("section")
        pl.addWidget(c)
        self.swatch = QPushButton("色を選ぶ…")
        self.swatch.clicked.connect(self.pick_color)
        pl.addWidget(self.swatch)
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, col in enumerate(self.PRESETS):
            b = QPushButton()
            b.setFixedSize(30, 30)
            b.setStyleSheet(f"background:{col}; border:1px solid #555; border-radius:6px;")
            b.clicked.connect(lambda _=False, cc=col: self.set_color(QColor(cc)))
            grid.addWidget(b, i // 6, i % 6)
        pl.addLayout(grid)

        tt = QLabel("テキスト")
        tt.setObjectName("section")
        pl.addWidget(tt)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("文字を入力 → 「テキスト」を選んでキャンバスをクリック")
        self.text_edit.setFixedHeight(80)
        self.text_edit.textChanged.connect(
            lambda: setattr(self.canvas, "text", self.text_edit.toPlainText()))
        pl.addWidget(self.text_edit)
        row = QHBoxLayout()
        row.addWidget(QLabel("文字サイズ"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(8, 400)
        self.font_spin.setValue(self.canvas.font_size)
        self.font_spin.valueChanged.connect(lambda v: setattr(self.canvas, "font_size", v))
        row.addWidget(self.font_spin)
        pl.addLayout(row)
        ft = QLabel("フォント(スワイプ/ドラッグでスクロール)")
        ft.setObjectName("section")
        ft.setWordWrap(True)
        pl.addWidget(ft)
        self.font_list = QListWidget()
        self.font_list.setFixedHeight(230)
        self.font_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.font_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.font_list.setTextElideMode(Qt.ElideRight)
        self.font_list.setStyleSheet("QListWidget { background: #2b2d31; border-radius: 8px; }")
        QScroller.grabGesture(self.font_list.viewport(), QScroller.LeftMouseButtonGesture)
        self.font_list.currentItemChanged.connect(self.on_font)
        pl.addWidget(self.font_list)
        self.show_all = QCheckBox("日本語以外のフォントも表示")
        self.show_all.toggled.connect(lambda _=False: self.reload_fonts())
        pl.addWidget(self.show_all)
        b_font = QPushButton("フォントを追加(.ttf / .otf)")
        b_font.clicked.connect(self.add_font)
        pl.addWidget(b_font)
        self.reload_fonts()

        pl.addStretch(1)
        panel_scroll = QScrollArea()
        panel_scroll.setWidget(panel)
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFixedWidth(285)
        panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_scroll = panel_scroll
        self.handle = QPushButton("▶")
        self.handle.setFixedWidth(26)
        self.handle.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.handle.setStyleSheet(
            "QPushButton { border-radius: 0; padding: 0; background: #2b2d31; border: none; }"
            "QPushButton:hover { background: #383b41; }")
        self.handle.clicked.connect(self.toggle_panel)
        root.addWidget(self.handle)
        root.addWidget(panel_scroll)

        # ショートカット
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self.canvas.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, activated=self.canvas.redo)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save)

        self.set_color(QColor("black"))
        self.on_pen_size(self.canvas.pen_size)
        self.on_eraser_size(self.canvas.eraser_size)

    # ---- 状態表示 ----
    def refresh_status(self):
        tool = self.canvas.tool
        s = f"選択中: {self.TOOL_NAMES[tool]}"
        if tool == "move":
            s += "\nドラッグ/指1本で絵を自由に動かす"
        if tool in ("pen", "eraser"):
            s += f"\n太さ {self.canvas.brush_size}px"
        if tool == "text":
            s += f"\n文字サイズ {self.canvas.font_size}px"
            s += f"\nフォント {self.canvas.font_family or '標準'}"
        self.status.setText(s)

    def reload_fonts(self, select=None):
        if select is None and self.font_list.currentItem() is not None:
            select = self.font_list.currentItem().data(Qt.UserRole)
        if self.show_all.isChecked():
            families = list(QFontDatabase.families())
        else:
            families = list(QFontDatabase.families(QFontDatabase.Japanese))
        if select and select not in families:
            families.append(select)
        yuru = [f for f in YURU_FONTS if f in families]
        others = [f for f in families if f not in yuru]

        self.font_list.blockSignals(True)
        self.font_list.clear()
        for f in yuru + others:
            item = QListWidgetItem(("★ " if f in yuru else "") + f)
            item.setData(Qt.UserRole, f)
            item.setFont(QFont(f, 14))      # 各フォントの見た目で表示
            item.setSizeHint(QSize(0, 36))
            self.font_list.addItem(item)
        if select is None and self.font_list.count() > 0:
            select = self.font_list.item(0).data(Qt.UserRole)
        for i in range(self.font_list.count()):
            if self.font_list.item(i).data(Qt.UserRole) == select:
                self.font_list.setCurrentRow(i)
                self.font_list.scrollToItem(self.font_list.item(i), QListWidget.PositionAtCenter)
                break
        self.font_list.blockSignals(False)
        self.on_font()

    def on_font(self, *_):
        item = self.font_list.currentItem()
        self.canvas.font_family = item.data(Qt.UserRole) if item else ""
        self.refresh_status()

    def add_font(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "フォントを選ぶ", "", "フォント (*.ttf *.otf)")
        last = None
        for path in paths:
            dest = FONT_DIR / Path(path).name
            try:
                if Path(path).resolve() != dest.resolve():
                    shutil.copy(path, dest)
            except Exception:
                continue
            fid = QFontDatabase.addApplicationFont(str(dest))
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                last = fams[0]
        if last:
            self.reload_fonts(select=last)
        elif paths:
            QMessageBox.warning(self, "エラー", "フォントを読み込めませんでした。")

    def toggle_panel(self):
        show = not self.panel_scroll.isVisible()
        self.panel_scroll.setVisible(show)
        self.handle.setText("▶" if show else "◀")

    def set_tool(self, key):
        self.canvas.set_tool(key)
        self.tool_buttons[key].setChecked(True)
        self.refresh_status()

    def on_pen_size(self, v):
        self.canvas.pen_size = v
        self.pen_label.setText(f"ペンの太さ: {v}px")
        self.refresh_status()
        self.canvas.update()

    def on_eraser_size(self, v):
        self.canvas.eraser_size = v
        self.eraser_label.setText(f"消しゴムの太さ: {v}px")
        self.refresh_status()
        self.canvas.update()

    def set_color(self, color):
        self.canvas.color = color
        text_color = "#000" if color.lightness() > 128 else "#fff"
        self.swatch.setStyleSheet(
            f"background:{color.name()}; color:{text_color}; border:2px solid #888;")
        if self.canvas.tool == "eraser":
            self.set_tool("pen")

    def pick_color(self):
        c = QColorDialog.getColor(self.canvas.color, self)
        if c.isValid():
            self.set_color(c)

    # ---- プロジェクト ----
    def open_project(self, dir_path, name, image):
        self.dir = dir_path
        self.name = name
        self.name_label.setText(name)
        self.prev_zoom = 1.0
        self.canvas.set_image(image)

    def fit(self, toggle=False):
        """全体表示。もう一度押すと、前の拡大率に戻る"""
        c = self.canvas
        if toggle and c.autofit and self.prev_zoom:
            c.zoom_center(self.prev_zoom)
        else:
            if not c.autofit:
                self.prev_zoom = c.zoom
            c.autofit = True
            c.fit_view()

    def save(self):
        if self.dir:
            save_project(self.dir, self.name, self.canvas.image)

    def export_image(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "書き出し", f"{self.name}.png", "PNG (*.png);;JPEG (*.jpg)")
        if path:
            self.canvas.image.save(path)


# ------------------------------------------------------------
# プロジェクト一覧(各カード右上に「⋮」ボタン)
# ------------------------------------------------------------
class CardDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        r = option.rect
        c = QPointF(r.right() - 24, r.top() + 24)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawEllipse(c, 16, 16)
        painter.setBrush(QColor("white"))
        for dy in (-7, 0, 7):
            painter.drawEllipse(QPointF(c.x(), c.y() + dy), 2.3, 2.3)
        painter.restore()


class ProjectList(QListWidget):
    menu_clicked = Signal(object, object)   # (item, 画面上の位置)

    def mousePressEvent(self, e):
        pos = e.position().toPoint()
        item = self.itemAt(pos)
        if item is not None and e.button() == Qt.LeftButton:
            r = self.visualItemRect(item)
            if QRect(r.right() - 46, r.top() + 2, 44, 44).contains(pos):
                self.menu_clicked.emit(item, e.globalPosition().toPoint())
                return
        super().mousePressEvent(e)


# ------------------------------------------------------------
# ホーム画面
# ------------------------------------------------------------
class Home(QWidget):
    create = Signal(int, int)
    open_dir = Signal(str)
    import_image = Signal()

    RATIOS = [("16:9", 1600, 900), ("9:16", 900, 1600), ("1:1", 1200, 1200),
              ("4:3", 1600, 1200), ("A4縦", 2480, 3508), ("SNS 1080", 1080, 1080)]

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(14)

        title = QLabel("PeTitPaint")
        title.setObjectName("title")
        lay.addWidget(title)

        ratio_row = QHBoxLayout()
        ratio_row.addWidget(QLabel("サイズ  幅"))
        self.w_spin = QSpinBox()
        self.w_spin.setRange(1, 6000)
        self.w_spin.setValue(1600)
        ratio_row.addWidget(self.w_spin)
        ratio_row.addWidget(QLabel("×  高さ"))
        self.h_spin = QSpinBox()
        self.h_spin.setRange(1, 6000)
        self.h_spin.setValue(900)
        ratio_row.addWidget(self.h_spin)
        ratio_row.addWidget(QLabel("px"))
        ratio_row.addSpacing(16)
        ratio_row.addWidget(QLabel("プリセット:"))
        for label, w, h in self.RATIOS:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, ww=w, hh=h: self.set_size(ww, hh))
            ratio_row.addWidget(b)
        ratio_row.addStretch(1)
        lay.addLayout(ratio_row)

        hero_row = QHBoxLayout()
        hero = QPushButton("＋  新しいプロジェクト")
        hero.setObjectName("hero")
        hero.setMinimumHeight(150)
        hero.clicked.connect(lambda: self.create.emit(self.w_spin.value(), self.h_spin.value()))
        hero_row.addWidget(hero, 3)
        img_btn = QPushButton("画像を開いて\nプロジェクトにする")
        img_btn.setMinimumHeight(150)
        img_btn.clicked.connect(self.import_image.emit)
        hero_row.addWidget(img_btn, 1)
        lay.addLayout(hero_row)

        head = QHBoxLayout()
        lbl = QLabel("最近のプロジェクト")
        lbl.setObjectName("section")
        head.addWidget(lbl)
        head.addStretch(1)
        del_btn = QPushButton("選択したものを削除")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.delete_selected)
        head.addWidget(del_btn)
        lay.addLayout(head)

        self.list = ProjectList()
        self.list.setItemDelegate(CardDelegate(self.list))
        self.list.menu_clicked.connect(self.popup_menu)
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(220, 150))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(12)
        self.list.setWordWrap(True)
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.itemDoubleClicked.connect(lambda it: self.open_dir.emit(it.data(Qt.UserRole)))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self.show_menu)
        sc = QShortcut(QKeySequence("Delete"), self.list, activated=self.delete_selected)
        sc.setContext(Qt.WidgetShortcut)
        lay.addWidget(self.list, 1)

        self.empty = QLabel("まだプロジェクトがありません。上の「新しいプロジェクト」から始めよう!")
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)

        tip = QLabel("ダブルクリックで開く / 右上の「⋮」で名前変更・削除")
        tip.setStyleSheet("color:#7d838a; font-size:12px;")
        lay.addWidget(tip)

    def set_size(self, w, h):
        self.w_spin.setValue(w)
        self.h_spin.setValue(h)

    def refresh(self):
        self.list.clear()
        projects = load_projects()
        for pr in projects:
            when = pr.get("modified", "")[:16].replace("T", " ")
            item = QListWidgetItem(f"{pr.get('name', '無題')}\n{when}")
            thumb = Path(pr["dir"]) / "thumb.png"
            if thumb.exists():
                item.setIcon(QIcon(QPixmap(str(thumb))))
            item.setData(Qt.UserRole, pr["dir"])
            item.setSizeHint(QSize(240, 215))
            self.list.addItem(item)
        self.empty.setVisible(len(projects) == 0)

    def show_menu(self, pos):
        item = self.list.itemAt(pos)
        if item is not None:
            self.popup_menu(item, self.list.viewport().mapToGlobal(pos))

    def popup_menu(self, item, global_pos):
        if not item.isSelected():
            self.list.clearSelection()
            item.setSelected(True)
        menu = QMenu(self)
        a_open = menu.addAction("開く")
        a_ren = menu.addAction("名前を変更")
        a_del = menu.addAction("削除")
        act = menu.exec(global_pos)
        if act == a_open:
            self.open_dir.emit(item.data(Qt.UserRole))
        elif act == a_ren:
            self.rename(item)
        elif act == a_del:
            self.delete_selected()

    def rename(self, item):
        d = Path(item.data(Qt.UserRole))
        meta_path = d / "project.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return
        new, ok = QInputDialog.getText(self, "名前を変更", "プロジェクト名", text=meta.get("name", ""))
        if ok and new.strip():
            meta["name"] = new.strip()
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            self.refresh()

    def delete_selected(self):
        items = self.list.selectedItems()
        if not items:
            QMessageBox.information(self, "削除", "削除するプロジェクトを選んでください。")
            return
        r = QMessageBox.question(
            self, "削除", f"{len(items)}個のプロジェクトを削除しますか?(元に戻せません)")
        if r == QMessageBox.Yes:
            for it in items:
                shutil.rmtree(it.data(Qt.UserRole), ignore_errors=True)
            self.refresh()


# ------------------------------------------------------------
# メインウィンドウ
# ------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PeTitPaint")
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home = Home()
        self.editor = Editor()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.editor)

        self.home.create.connect(self.create_project)
        self.home.open_dir.connect(self.open_project)
        self.home.import_image.connect(self.import_image)
        self.editor.go_home.connect(self.show_home)
        self.home.refresh()

    def create_project(self, w, h, image=None, name=None):
        if image is None:
            image = QImage(w, h, QImage.Format_ARGB32)
            image.fill(Qt.white)
        name = name or datetime.now().strftime("作品 %m-%d %H:%M")
        d = BASE / uuid.uuid4().hex
        save_project(d, name, image)
        self.editor.open_project(str(d), name, image)
        self.stack.setCurrentWidget(self.editor)

    def open_project(self, dir_path):
        d = Path(dir_path)
        try:
            meta = json.loads((d / "project.json").read_text(encoding="utf-8"))
        except Exception:
            return
        image = QImage(str(d / "image.png"))
        if image.isNull():
            QMessageBox.warning(self, "エラー", "画像を読み込めませんでした。")
            return
        image = image.convertToFormat(QImage.Format_ARGB32)
        self.editor.open_project(str(d), meta.get("name", "無題"), image)
        self.stack.setCurrentWidget(self.editor)

    def import_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "画像を開く", "", "画像 (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "エラー", "画像を読み込めませんでした。")
            return
        self.create_project(0, 0, img.convertToFormat(QImage.Format_ARGB32), Path(path).stem)

    def show_home(self):
        self.editor.save()
        self.home.refresh()
        self.stack.setCurrentWidget(self.home)

    def closeEvent(self, e):
        if self.stack.currentWidget() is self.editor:
            self.editor.save()
        e.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    load_user_fonts()
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    sys.exit(app.exec())