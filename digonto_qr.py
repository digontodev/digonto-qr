"""Digonto QR - QR codes for links, Wi-Fi, menus and contacts, with your own style. PySide6 only."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMarginsF, QRectF, QSize, QSizeF, Qt, QTimer
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPainterPath, QPdfWriter,
                           QPixmap)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget)

import digonto_ui as ui
from qrkit import __version__ as VERSION
from qrkit import render
from qrkit.core import TooLong, encode
from qrkit.payloads import FIELDS, TYPES, build

APP_NAME = "Digonto QR"
SLUG = "digonto-qr"
WIN = sys.platform.startswith("win")
LEVELS = [("Low (7 %)", "L"), ("Medium (15 %)", "M"), ("High (25 %)", "Q"), ("Max (30 %)", "H")]
NICE = {"square": "Square", "rounded": "Rounded", "dots": "Dots", "diamond": "Diamond", "liquid": "Liquid", "leaf": "Leaf",
        "vbars": "Vertical bars", "hbars": "Horizontal bars", "circle": "Circle", "none": "None", "box": "Box", "banner": "Banner"}


# ---- shared recent list (read by Digonto Studio)
def base_dir():
    env = (os.environ.get("DIGONTO_BASE") or os.environ.get("PROTTOY_BASE"))
    return env if env else os.path.dirname(os.path.dirname(HERE))


def add_recent(path):
    rp = os.path.join(base_dir(), "recent.json")
    try:
        with open(rp, encoding="utf-8") as f:
            items = [r for r in json.load(f) if isinstance(r, dict)]
    except (OSError, ValueError):
        items = []
    items = [r for r in items if r.get("path") != path]
    items.insert(0, {"app": SLUG, "path": path, "time": time.time()})
    try:
        os.makedirs(base_dir(), exist_ok=True)
        with open(rp, "w", encoding="utf-8") as f:
            json.dump(items[:40], f)
    except OSError:
        pass


def text_path(text, bold=True):
    """text -> SVG path data, 1 unit = font height; returns {"d", "w"} (no font files needed in the exported SVG)"""
    f = QFont()
    f.setPixelSize(100)
    f.setBold(bold)
    f.setFamilies(["Helvetica Neue", "Segoe UI", "DejaVu Sans", "Arial"])
    p = QPainterPath()
    p.addText(0, 80, f, text)
    out = []
    for i in range(p.elementCount()):
        e = p.elementAt(i)
        if e.type == QPainterPath.MoveToElement:
            out.append(f"M{e.x / 100:.4f} {e.y / 100:.4f}")
        elif e.type == QPainterPath.LineToElement:
            out.append(f"L{e.x / 100:.4f} {e.y / 100:.4f}")
        elif e.type == QPainterPath.CurveToElement:
            c1, c2 = e, p.elementAt(i + 1)
            end = p.elementAt(i + 2)
            out.append(f"C{c1.x / 100:.4f} {c1.y / 100:.4f} {c2.x / 100:.4f} {c2.y / 100:.4f} {end.x / 100:.4f} {end.y / 100:.4f}")
    # close each sub-path
    d = "".join(out).replace("M", "ZM")[1:] + "Z" if out else ""
    return {"d": d, "w": QFontMetricsF(f).horizontalAdvance(text) / 100.0, "text": text}


class ColorButton(QPushButton):
    def __init__(self, color, on_change):
        super().__init__()
        self.setFixedSize(38, 26)
        self.on_change = on_change
        self.set(color)
        self.clicked.connect(self.pick)

    def set(self, c):
        self.color = c
        self.setStyleSheet(f"QPushButton{{background:{c}; border:1px solid #9787A3; border-radius:5px;}}")

    def pick(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Choose a color")
        if c.isValid():
            self.set(c.name().upper())
            self.on_change()


def _shrink(root):
    """the right panel is a fixed 250 px column: let buttons, drop-downs and fields get narrower"""
    from PySide6.QtWidgets import QSizePolicy
    for b in root.findChildren(QPushButton):
        if isinstance(b, ColorButton):
            continue
        p = b.sizePolicy()
        p.setHorizontalPolicy(QSizePolicy.Ignored)
        b.setSizePolicy(p)
        if b.text():
            b.setMinimumWidth(min(70, b.fontMetrics().horizontalAdvance(b.text()) + 16))
    for c in root.findChildren(QComboBox):
        c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        c.setMinimumContentsLength(4)
        c.setMinimumWidth(40)
    for e in root.findChildren(QLineEdit):
        e.setMinimumWidth(40)
    for t in root.findChildren(QLabel):
        t.setWordWrap(False)
        t.setMinimumWidth(0)


def labeled(text):
    l = QLabel(text.upper())
    l.setStyleSheet("font-size:11px; font-weight:700; color:#5B5278; letter-spacing:1px; margin-top:6px;")
    return l


class Preview(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(260, 260)
        self.pix = None

    def show_image(self, img):
        self.pix = QPixmap.fromImage(img)
        self.rescale()

    def rescale(self):
        if self.pix is not None:
            self.setPixmap(self.pix.scaled(self.size() - QSize(24, 24), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.rescale()


class BulkDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Many codes from a list")
        self.resize(520, 440)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("One code per line. Use  name ; text  to choose the file name (for example  table-1 ; https://pizzneapol.de/t/1)."))
        self.box = QPlainTextEdit()
        lay.addWidget(self.box, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Format"))
        self.fmt = QComboBox()
        self.fmt.addItems(["PNG", "SVG", "PDF"])
        row.addWidget(self.fmt)
        row.addWidget(QLabel("Size (PNG)"))
        self.px = QSpinBox()
        self.px.setRange(200, 8000)
        self.px.setValue(1200)
        row.addWidget(self.px)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Cancel)
        go = bb.addButton("Choose folder and make codes", QDialogButtonBox.AcceptRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def entries(self):
        out = []
        for i, line in enumerate(self.box.toPlainText().splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            name, text = (x.strip() for x in line.split(";", 1)) if ";" in line and not line.lower().startswith(("wifi:", "http")) else (f"code-{len(out) + 1}", line)
            name = "".join(c if c.isalnum() or c in "-_ ." else "_" for c in name) or f"code-{i}"
            out.append((name, text))
        return out


class Main(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.icon = ui.app_icon(HERE, SLUG)
        self.setWindowIcon(self.icon)
        ui.fit_window(self, 1240, 800)
        self.setMinimumSize(600, 420)
        self.setStyleSheet("QMainWindow{background:#F6F2FA;} QMenuBar{background:#EDE6F4; color:#1B1040;} QMenu{background:white; color:#1B1040;} QMenu::item:selected{background:#FBDCE5;} QStatusBar{background:#EDE6F4;color:#5B5278;}"
                           "QComboBox QAbstractItemView::item{min-height:24px; color:#1B1040; background:white;} QComboBox QAbstractItemView::item:selected,QComboBox QAbstractItemView::item:hover{background:#FBDCE5; color:#1B1040;}"
                           "QComboBox QAbstractItemView{background:white; color:#1B1040; selection-background-color:#FBDCE5; selection-color:#1B1040; border:1px solid #D0C4E1;}"
                           "QLineEdit,QPlainTextEdit,QComboBox,QSpinBox{background:white; border:1px solid #D0C4E1; border-radius:6px; padding:5px;}"
                           "QPushButton{background:white; border:1px solid #D0C4E1; border-radius:6px; padding:6px 12px;}"
                           "QPushButton:hover{background:#EDE6F4;}"
                           "QPushButton#primary{background:qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF6F8E, stop:1 #FFB05A); color:#2A1241; border-color:#FF6F8E; font-weight:600;}"
                           "QPushButton#primary:hover{background:qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #FF86A1, stop:1 #FFC273);}")
        self.logo = None
        self.label_cache = {}
        self.fields = {}
        self.kind = "Link"
        self.last_text = ""
        self.project_path = None
        self.build_menu()

        body = QWidget()
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.rail = ui.Rail(
            [("new", "new", "New QR code (Ctrl+N)", self.new),
             ("open", "open", "Open project (Ctrl+O)", self.open_dialog),
             ("save", "save", "Save project (Ctrl+S)", self.save_project),
             ("export", "export", "Export PNG, SVG or PDF", self.rail_export),
             None,
             ("bulk", "qr", "Many codes from a list", self.bulk),
             ("copy", "images", "Copy the picture (Ctrl+C)", self.copy_image)],
            [("settings", "settings", "Settings and help", self.rail_settings)])
        h.addWidget(self.rail, 0)
        h.addWidget(self.left_panel(), 0)
        h.addWidget(self.center_panel(), 1)
        h.addWidget(self.right_panel(), 0)
        hd = ui.make_header(APP_NAME, "QR codes for links, Wi-Fi, menus and contacts", self.icon, self.about)
        ui.wrap_with_header(self, hd, body)

        self.timer = QTimer(self, singleShot=True, interval=120, timeout=self.update_preview)
        self.build_fields()
        if path and os.path.isfile(path):
            self.open_project(path)
        else:
            self.update_preview()
        QTimer.singleShot(300, lambda: setattr(self, "_saved", self._snap()))

    # ---- menu
    def build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("File")
        for text, sc, fn in (("New", "Ctrl+N", self.new), ("Open project ...", "Ctrl+O", self.open_dialog),
                             ("Save project", "Ctrl+S", self.save_project), ("Save project as ...", "Ctrl+Shift+S", lambda: self.save_project(True)), ("Close project", "Ctrl+W", self.new)):
            fm.addAction(QAction(text, self, shortcut=sc, triggered=fn))
        fm.addSeparator()
        for text, fn in (("Export PNG ...", lambda: self.export("png")), ("Export SVG ...", lambda: self.export("svg")),
                         ("Export PDF ...", lambda: self.export("pdf")), ("Many codes from a list ...", self.bulk)):
            fm.addAction(QAction(text, self, triggered=fn))
        fm.addAction(QAction("Copy image", self, shortcut="Ctrl+C", triggered=self.copy_image))
        fm.addSeparator()
        fm.addAction(QAction("Exit", self, shortcut="Ctrl+Q", triggered=self.close))
        fm.addAction(QAction("Quit (force)", self, shortcut="Ctrl+Shift+Q", triggered=lambda: os._exit(0)))
        hm = mb.addMenu("Help")
        hm.addAction(QAction("About Digonto QR", self, triggered=self.about))

    def rail_export(self):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("Save project as …", lambda: self.save_project(True))
        m.addSeparator()
        m.addAction("Export PNG …", lambda: self.export("png"))
        m.addAction("Export SVG …", lambda: self.export("svg"))
        m.addAction("Export PDF …", lambda: self.export("pdf"))
        b = self.rail.button("export")
        m.exec(b.mapToGlobal(b.rect().topRight()))

    def rail_settings(self):
        from PySide6.QtWidgets import QMenu
        m = QMenu(self)
        m.addAction("About Digonto QR", self.about)
        b = self.rail.button("settings")
        m.exec(b.mapToGlobal(b.rect().topRight()))

    # ---- panels
    def left_panel(self):
        w = QFrame()
        w.setFixedWidth(340)
        w.setStyleSheet("QFrame#l{background:white; border-right:1px solid #DDD3E9;}")
        w.setObjectName("l")
        v = QVBoxLayout(w)
        v.setContentsMargins(18, 14, 18, 14)
        v.addWidget(labeled("Type"))
        self.type = QComboBox()
        self.type.addItems(TYPES)
        self.type.currentTextChanged.connect(self.set_kind)
        v.addWidget(self.type)
        self.form_host = QWidget()
        self.form = QFormLayout(self.form_host)
        self.form.setContentsMargins(0, 8, 0, 0)
        self.form.setLabelAlignment(Qt.AlignLeft)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.form.setVerticalSpacing(8)
        v.addWidget(self.form_host)
        v.addWidget(labeled("Error correction"))
        self.level = QComboBox()
        for t, _ in LEVELS:
            self.level.addItem(t)
        self.level.setCurrentIndex(1)
        self.level.currentIndexChanged.connect(self.changed)
        v.addWidget(self.level)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("background:#EDE6F4; border-radius:8px; padding:9px; color:#5B5278; font-size:12px;")
        v.addWidget(self.hint)
        v.addStretch(1)
        b = QPushButton("Many codes from a list ...")
        b.clicked.connect(self.bulk)
        v.addWidget(b)
        return w

    def center_panel(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 24, 24, 14)
        self.preview = Preview()
        self.preview.setStyleSheet("background:white; border:1px solid #DDD3E9; border-radius:14px;")
        v.addWidget(self.preview, 1)
        self.info = QLabel("")
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setStyleSheet("color:#5B5278; font-size:12.5px;")
        v.addWidget(self.info)
        return w

    def right_panel(self):
        sc = QScrollArea()
        sc.setFixedWidth(250)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setStyleSheet("QScrollArea{background:white; border-left:1px solid #DDD3E9;}")
        w = QWidget()
        w.setStyleSheet("background:white;")
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 12, 10, 14)

        def combo(items, cur, nice=True):
            c = QComboBox()
            for i in items:
                c.addItem(NICE.get(i, i), i)
            c.setCurrentIndex(items.index(cur))
            c.currentIndexChanged.connect(self.changed)
            return c

        d = render.DEFAULT
        v.addWidget(labeled("Dots"))
        self.dots = combo(render.DOT_STYLES, "square")
        v.addWidget(self.dots)
        row = QHBoxLayout()
        row.addWidget(QLabel("Dot size"))
        self.dot_size = QSlider(Qt.Horizontal)
        self.dot_size.setRange(50, 100)
        self.dot_size.setValue(100)
        self.dot_size.valueChanged.connect(self.changed)
        row.addWidget(self.dot_size)
        v.addLayout(row)

        v.addWidget(labeled("Corner eyes"))
        self.eye_outer = combo(render.EYE_OUTER, "square")
        self.eye_inner = combo(render.EYE_INNER, "square")
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Frame"))
        r2.addWidget(self.eye_outer, 1)
        v.addLayout(r2)
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Center"))
        r3.addWidget(self.eye_inner, 1)
        v.addLayout(r3)
        self.eye_same = QCheckBox("Same as the dots")
        self.eye_same.setChecked(True)
        self.eye_same.toggled.connect(self.changed)
        self.eye_same.toggled.connect(lambda on: [b.setEnabled(not on) for b in (self.eye_c1, self.eye_c2)])
        v.addWidget(self.eye_same)
        r4 = QHBoxLayout()
        self.eye_c1 = ColorButton("#000000", self.changed)
        self.eye_c2 = ColorButton("#000000", self.changed)
        r4.addWidget(QLabel("Frame"))
        r4.addWidget(self.eye_c1)
        r4.addWidget(QLabel("Dot"))
        r4.addWidget(self.eye_c2)
        r4.addStretch()
        v.addLayout(r4)
        self.eye_c1.setEnabled(False)
        self.eye_c2.setEnabled(False)

        v.addWidget(labeled("Colors"))
        r5 = QHBoxLayout()
        self.fg = ColorButton("#1B1040", self.changed)
        self.fg2 = ColorButton("#C2395C", self.changed)
        self.bg = ColorButton("#FFFFFF", self.changed)
        r5.addWidget(QLabel("Code"))
        r5.addWidget(self.fg)
        r5.addWidget(QLabel("Back"))
        r5.addWidget(self.bg)
        r5.addStretch()
        v.addLayout(r5)
        self.bg_on = QCheckBox("Solid background")
        self.bg_on.setToolTip("Off = transparent background")
        self.bg_on.setChecked(True)
        self.bg_on.toggled.connect(self.changed)
        v.addWidget(self.bg_on)
        r6 = QHBoxLayout()
        self.grad = QComboBox()
        for k, t in (("none", "One color"), ("linear", "Gradient"), ("radial", "Radial gradient")):
            self.grad.addItem(t, k)
        self.grad.currentIndexChanged.connect(self.changed)
        r6.addWidget(self.grad, 1)
        r6.addWidget(self.fg2)
        v.addLayout(r6)
        r7 = QHBoxLayout()
        r7.addWidget(QLabel("Angle"))
        self.angle = QSlider(Qt.Horizontal)
        self.angle.setRange(0, 360)
        self.angle.setValue(45)
        self.angle.valueChanged.connect(self.changed)
        r7.addWidget(self.angle)
        v.addLayout(r7)

        v.addWidget(labeled("Logo in the middle"))
        r8 = QHBoxLayout()
        b = QPushButton("Choose ...")
        b.clicked.connect(self.pick_logo)
        c = QPushButton("Clear")
        c.clicked.connect(self.clear_logo)
        r8.addWidget(b, 1)
        r8.addWidget(c, 1)
        v.addLayout(r8)
        r9 = QHBoxLayout()
        r9.addWidget(QLabel("Size"))
        self.logo_size = QSlider(Qt.Horizontal)
        self.logo_size.setRange(8, 30)
        self.logo_size.setValue(20)
        self.logo_size.valueChanged.connect(self.changed)
        r9.addWidget(self.logo_size)
        v.addLayout(r9)
        r10 = QHBoxLayout()
        self.plate = combo(render.PLATES, "rounded")
        self.plate_color = ColorButton("#FFFFFF", self.changed)
        r10.addWidget(QLabel("Behind it"))
        r10.addWidget(self.plate, 1)
        r10.addWidget(self.plate_color)
        v.addLayout(r10)

        v.addWidget(labeled("Frame and label"))
        self.frame = combo(render.FRAMES, "none")
        v.addWidget(self.frame)
        self.label = QLineEdit()
        self.label.setPlaceholderText("Text under the code, for example Scan for our menu")
        self.label.textChanged.connect(self.changed)
        v.addWidget(self.label)
        r11 = QHBoxLayout()
        self.frame_color = ColorButton("#C2395C", self.changed)
        r11.addWidget(QLabel("Color"))
        r11.addWidget(self.frame_color)
        self.label_color = ColorButton("#FFFFFF", self.changed)
        r11.addWidget(QLabel("Text"))
        r11.addWidget(self.label_color)
        r11.addStretch()
        v.addLayout(r11)

        v.addWidget(labeled("Export"))
        r12 = QHBoxLayout()
        for t in ("PNG", "SVG", "PDF"):
            b = QPushButton(t)
            b.clicked.connect(lambda _=False, t=t: self.export(t.lower()))
            r12.addWidget(b)
        v.addLayout(r12)
        r13 = QHBoxLayout()
        r13.addWidget(QLabel("PNG size"))
        self.png_px = QSpinBox()
        self.png_px.setRange(200, 10000)
        self.png_px.setValue(2000)
        self.png_px.setSuffix(" px")
        r13.addWidget(self.png_px)
        v.addLayout(r13)
        sv = QPushButton("Save project")
        sv.setObjectName("primary")
        sv.clicked.connect(lambda: self.save_project())
        v.addWidget(sv)
        v.addStretch(1)
        _shrink(w)
        w.setMaximumWidth(234)
        sc.setWidget(w)
        return sc

    # ---- fields
    def set_kind(self, kind):
        self.kind = kind
        self.build_fields()
        self.changed()

    def build_fields(self, values=None):
        while self.form.rowCount():
            self.form.removeRow(0)
        self.fields = {}
        for key, label, kind, default in FIELDS[self.kind]:
            val = (values or {}).get(key, default)
            if kind == "multi":
                w = QPlainTextEdit(val)
                w.setFixedHeight(90)
                w.textChanged.connect(self.changed)
            elif kind.startswith("choice:"):
                w = QComboBox()
                w.addItems(kind[7:].split(","))
                w.setCurrentText(val)
                w.currentIndexChanged.connect(self.changed)
            else:
                w = QLineEdit(val)
                w.textChanged.connect(self.changed)
            self.fields[key] = w
            self.form.addRow(label, w)
        first = next(iter(self.fields.values()))
        first.setFocus()

    def values(self):
        out = {}
        for k, w in self.fields.items():
            out[k] = w.toPlainText() if isinstance(w, QPlainTextEdit) else (w.currentText() if isinstance(w, QComboBox) else w.text())
        return out

    # ---- state -> picture
    def changed(self, *_):
        self.timer.start()

    def style(self):
        return {"dots": self.dots.currentData(), "dot_size": self.dot_size.value() / 100, "eye_outer": self.eye_outer.currentData(),
                "eye_inner": self.eye_inner.currentData(), "eye_same": self.eye_same.isChecked(),
                "eye_outer_color": self.eye_c1.color, "eye_inner_color": self.eye_c2.color, "fg": self.fg.color,
                "fg2": self.fg2.color, "gradient": self.grad.currentData(), "angle": self.angle.value(), "bg": self.bg.color,
                "bg_on": self.bg_on.isChecked(), "logo_size": self.logo_size.value() / 100, "plate": self.plate.currentData(),
                "plate_color": self.plate_color.color, "frame": self.frame.currentData(), "frame_color": self.frame_color.color,
                "label_color": self.label_color.color}

    def label_data(self):
        t = self.label.text().strip()
        if not t:
            return None
        if t not in self.label_cache:
            self.label_cache = {t: text_path(t)}
        return self.label_cache[t]

    def make_qr(self, text, st=None, logo=None):
        st = st or self.style()
        idx = self.level.currentIndex()
        lvl = LEVELS[idx][1]
        qr = encode(text, lvl)
        if logo:
            for lv in "MQH":
                if "LMQH".index(lv) >= "LMQH".index(lvl):
                    q2 = encode(text, lv)
                    if render.coverage(q2, {**render.DEFAULT, **st}, logo) <= {"M": 0.06, "Q": 0.11, "H": 0.17}[lv]:
                        return q2
            return encode(text, "H")
        return qr

    def svg(self, text=None, px=10):
        text = self.current_text() if text is None else text
        if not text:
            return None
        st = self.style()
        qr = self.make_qr(text, st, self.logo)
        return render.build_svg(qr, st, self.logo, self.label_data(), px), qr

    def current_text(self):
        return build(self.kind, self.values())

    def update_preview(self):
        text = self.current_text()
        self.last_text = text
        if not text:
            self.preview.clear()
            self.preview.pix = None
            self.preview.setText("Fill in the form on the left")
            self.info.setText("")
            self.hint.setText("Your code appears here while you type.")
            return
        try:
            svg, qr = self.svg(text)
        except TooLong:
            self.preview.pix = None
            self.preview.setText("Too much text for one QR code.\nShorten it or lower the error correction.")
            self.info.setText("")
            return
        self.svg_text, self.qr = svg, qr
        img = self.raster(svg, 900)
        self.preview.setText("")
        self.preview.show_image(img)
        n = qr.size
        self.info.setText(f"Version {qr.version}  -  {n} x {n} modules  -  correction {qr.level}  -  {len(text.encode())} bytes")
        notes = []
        st = self.style()
        if self.logo:
            notes.append(f"Logo in the middle: correction was raised to {qr.level} so the code still scans.")
        if not st["bg_on"] and not self.logo:
            notes.append("Transparent background: put the code on a light, calm surface.")
        if self.contrast(st) < 3:
            notes.append("Low contrast between code and background - phones may not read it. Use a darker code color.")
        self.hint.setText(" ".join(notes) or "Higher correction keeps the code readable with a logo or a small scratch. Test with your phone before printing.")

    @staticmethod
    def lum(c):
        c = QColor(c)
        f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(c.redF()) + 0.7152 * f(c.greenF()) + 0.0722 * f(c.blueF())

    def contrast(self, st):
        if not st["bg_on"]:
            return 21
        cols = [st["fg"]] + ([st["fg2"]] if st["gradient"] != "none" else [])
        a = self.lum(st["bg"])
        worst = 21
        for c in cols:
            b = self.lum(c)
            hi, lo = max(a, b), min(a, b)
            worst = min(worst, (hi + 0.05) / (lo + 0.05))
        if st["bg"] and a < min(self.lum(c) for c in cols):
            worst = min(worst, 1.5)          # light code on dark background: many scanners fail
        return worst

    @staticmethod
    def raster(svg, px, transparent=False):
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        sz = r.defaultSize()
        h = max(1, round(px * sz.height() / max(1, sz.width())))
        img = QImage(px, h, QImage.Format_ARGB32)
        img.fill(0 if transparent else 0xFFFFFFFF)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        r.render(p, QRectF(0, 0, px, h))
        p.end()
        return img

    # ---- logo
    def pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a logo", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)")
        if not path:
            return
        img = QImage(path)
        if path.lower().endswith(".svg"):
            r = QSvgRenderer(path)
            if r.isValid():
                s = r.defaultSize()
                k = 512 / max(s.width(), s.height(), 1)
                img = QImage(int(s.width() * k), int(s.height() * k), QImage.Format_ARGB32)
                img.fill(0)
                p = QPainter(img)
                r.render(p)
                p.end()
        if img.isNull():
            QMessageBox.warning(self, APP_NAME, "This image could not be opened.")
            return
        if max(img.width(), img.height()) > 700:
            img = img.scaled(700, 700, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        self.logo = {"data": bytes(ba), "mime": "image/png", "w": img.width(), "h": img.height()}
        self.changed()

    def clear_logo(self):
        self.logo = None
        self.changed()

    # ---- export
    def ask(self, ext, title):
        path, _ = QFileDialog.getSaveFileName(self, title, f"qr-code.{ext}", f"{ext.upper()} (*.{ext})")
        if path and not path.lower().endswith("." + ext):
            path += "." + ext
        return path

    def write_file(self, fmt, path, text, px=None):
        svg, _qr = self.svg(text)
        if fmt == "svg":
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg)
        elif fmt == "png":
            img = self.raster(svg, px or self.png_px.value(), transparent=not self.bg_on.isChecked())
            if not img.save(path, "PNG"):
                raise OSError("could not write the file")
        else:
            r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            s = r.defaultSize()
            w_mm = 80.0
            h_mm = w_mm * s.height() / s.width()
            pw = QPdfWriter(path)
            pw.setResolution(600)
            pw.setPageSize(QPageSize(QSizeF(w_mm, h_mm), QPageSize.Millimeter))
            pw.setPageMargins(QMarginsF(0, 0, 0, 0))
            pw.setTitle("QR code")
            p = QPainter(pw)
            r.render(p, QRectF(0, 0, pw.width(), pw.height()))
            p.end()

    def export(self, fmt):
        text = self.current_text()
        if not text:
            QMessageBox.information(self, APP_NAME, "Fill in the form first.")
            return
        path = self.ask(fmt, f"Export {fmt.upper()}")
        if not path:
            return
        try:
            self.write_file(fmt, path, text)
        except (OSError, TooLong) as e:
            QMessageBox.warning(self, APP_NAME, f"Could not save:\n{e}")
            return
        self.statusBar().showMessage(f"Saved {path}", 6000)

    def copy_image(self):
        if getattr(self, "svg_text", None):
            QApplication.clipboard().setImage(self.raster(self.svg_text, 1200))
            self.statusBar().showMessage("Copied the picture", 3000)

    def bulk(self):
        dlg = BulkDialog(self)
        if not dlg.exec():
            return
        items = dlg.entries()
        if not items:
            return
        folder = QFileDialog.getExistingDirectory(self, "Save the codes in this folder")
        if not folder:
            return
        fmt = dlg.fmt.currentText().lower()
        ok, bad = 0, []
        for name, text in items:
            try:
                self.write_file(fmt, os.path.join(folder, f"{name}.{fmt}"), text, dlg.px.value())
                ok += 1
            except (OSError, TooLong) as e:
                bad.append(name)
        msg = f"{ok} code(s) saved in\n{folder}"
        if bad:
            msg += "\n\nToo long or not saved: " + ", ".join(bad)
        QMessageBox.information(self, APP_NAME, msg)

    # ---- project files (.dqr; older .pqr still open)
    def project(self):
        import base64
        d = {"app": SLUG, "version": 1, "kind": self.kind, "values": self.values(), "level": self.level.currentIndex(),
             "style": self.style(), "label": self.label.text()}
        if self.logo:
            d["logo"] = {**{k: v for k, v in self.logo.items() if k != "data"}, "data": base64.b64encode(self.logo["data"]).decode()}
        return d

    def _snap(self):
        try:
            return json.dumps(self.project(), sort_keys=True, default=str)
        except Exception:                      # noqa: BLE001
            return ""

    def maybe_save(self):
        """True when it is fine to leave this project (asks to save when it has changes)"""
        if self._snap() == getattr(self, "_saved", None):
            return True
        r = QMessageBox.question(self, APP_NAME, "Save changes to this project?", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            self.save_project()
            return self._snap() == getattr(self, "_saved", None)
        return r == QMessageBox.Discard

    def new(self):
        if not self.maybe_save():
            return
        self.project_path = None
        self.type.setCurrentText("Link")
        self.build_fields()
        self.logo = None
        self.label.clear()
        self.changed()
        self._saved = self._snap()

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "Digonto QR project (*.dqr *.pqr)")
        if path and self.maybe_save():
            self.open_project(path)

    def open_project(self, path):
        import base64
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            self.type.blockSignals(True)
            self.type.setCurrentText(d["kind"])
            self.type.blockSignals(False)
            self.kind = d["kind"]
            self.build_fields(d.get("values"))
            self.level.setCurrentIndex(int(d.get("level", 1)))
            s = d.get("style", {})
            for name, widget in (("dots", self.dots), ("eye_outer", self.eye_outer), ("eye_inner", self.eye_inner),
                                 ("gradient", self.grad), ("plate", self.plate), ("frame", self.frame)):
                i = widget.findData(s.get(name))
                if i >= 0:
                    widget.setCurrentIndex(i)
            self.dot_size.setValue(int(s.get("dot_size", 1) * 100))
            self.eye_same.setChecked(s.get("eye_same", True))
            for w, k in ((self.eye_c1, "eye_outer_color"), (self.eye_c2, "eye_inner_color"), (self.fg, "fg"), (self.fg2, "fg2"),
                         (self.bg, "bg"), (self.plate_color, "plate_color"), (self.frame_color, "frame_color"), (self.label_color, "label_color")):
                if k in s:
                    w.set(s[k])
            self.bg_on.setChecked(s.get("bg_on", True))
            self.angle.setValue(int(s.get("angle", 45)))
            self.logo_size.setValue(int(s.get("logo_size", 0.2) * 100))
            self.label.setText(d.get("label", ""))
            lg = d.get("logo")
            self.logo = {**lg, "data": base64.b64decode(lg["data"])} if lg else None
        except (OSError, ValueError, KeyError) as e:
            QMessageBox.warning(self, APP_NAME, f"This project could not be opened:\n{e}")
            return
        self.project_path = path
        add_recent(path)
        self.update_preview()
        self._saved = self._snap()

    def save_project(self, as_new=False):
        path = self.project_path
        if as_new or not path:
            path = self.ask("dqr", "Save project")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.project(), f)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, f"Could not save:\n{e}")
            return
        self.project_path = path
        add_recent(path)
        self._saved = self._snap()
        self.statusBar().showMessage(f"Saved {path}", 5000)

    def closeEvent(self, ev):
        if not self.maybe_save():
            ev.ignore()
            return
        ev.accept()
        QApplication.instance().quit()
        QTimer.singleShot(1500, lambda: os._exit(0))

    def about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
                          f"<h3>{APP_NAME} {VERSION}</h3><p>QR codes for links, Wi-Fi, menus, contacts and more, with your own dots, "
                          "corner eyes, colors, gradient, logo and frame. Export PNG, SVG or PDF; make many codes from a list.</p>"
                          "<p>The QR encoder is built into this program (no extra QR library). Built with Qt for Python (PySide6-Essentials).</p>")


def main():
    if "--version" in sys.argv:
        print(VERSION)
        return
    ui.mac_app_name(APP_NAME)
    app = QApplication(sys.argv)
    if ui.forward_to_running(SLUG, sys.argv[1:]):
        os._exit(0)
    ui.setup_app(app, APP_NAME, SLUG, ui.app_icon(HERE, SLUG))
    path = next((a for a in sys.argv[1:] if os.path.isfile(a)), None)
    w = Main(path)
    w.show()
    _extra = []

    def _new_window(p):
        x = Main(p)
        x.show()
        _extra.append(x)
        return x
    ui.serve_single(SLUG, w, _new_window)
    rc = app.exec()
    os._exit(rc)


if __name__ == "__main__":
    main()
