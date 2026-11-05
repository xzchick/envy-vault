"""A native ENVY Vault window: a real desktop application, not a web view.

Built with PyQt6, so it opens a genuine OS window on macOS, Windows and Linux
and bundles as a self-contained app. Styled in the ENVY palette — midnight with
neon pink, cyan and lavender — with a live animated header (starfield, a pulsing
gradient wordmark, a travelling light) and a shimmer while it works.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

from . import __version__
from .core import VaultError, check_passphrase, transform_file

# ENVY theme.
BG = "#050713"
PANEL = "#0a0e22"
PANEL_HI = "#121735"
INK = "#f2f4ff"
MUTED = "#b9c3df"
DIM = "#6f7898"
PINK = "#ff3db4"
CYAN = "#35e8ff"
LAVENDER = "#ac8cff"
VIOLET = "#8547e8"
LINE = "#1f2547"


def _build():
    from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF, QPointF
    from PyQt6.QtGui import (QColor, QPainter, QLinearGradient, QRadialGradient, QFont,
                             QPen, QBrush, QPainterPath)
    from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QLineEdit, QPushButton,
                                 QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog,
                                 QCheckBox, QFrame, QSizePolicy)

    class Header(QWidget):
        """Animated neon header painted with QPainter."""

        def __init__(self):
            super().__init__()
            self.setFixedHeight(188)
            self.phase = 0.0
            self.stars = [(((i * 139 + 37) % 1000) / 1000.0,
                           ((i * 83 + 19) % 188) / 188.0,
                           0.6 + (i % 3) * 0.5, (i % 7) / 7.0) for i in range(60)]

        def tick(self, phase):
            self.phase = phase
            self.update()

        def paintEvent(self, _event):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w, h = self.width(), self.height()
            p.fillRect(self.rect(), QColor(BG))
            # Nebula glows.
            for cx, cy, rad, col, a in ((w - 120, 70, 260, PINK, 70),
                                        (60, h, 300, CYAN, 55), (w * 0.5, -40, 260, VIOLET, 45)):
                g = QRadialGradient(cx, cy, rad)
                c = QColor(col); c.setAlpha(a); g.setColorAt(0, c)
                c2 = QColor(col); c2.setAlpha(0); g.setColorAt(1, c2)
                p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), rad, rad)
            # Twinkling stars.
            for sx, sy, sr, ph in self.stars:
                tw = 0.5 + 0.5 * math.sin(self.phase / 0.5 + ph * 6.28)
                c = QColor(205, 217, 255); c.setAlphaF(0.15 + 0.6 * tw)
                p.setBrush(c); p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(sx * w, sy * h), sr, sr)
            # Lock glyph.
            pulse = 0.5 + 0.5 * math.sin(self.phase)
            p.setFont(QFont("Helvetica", 26))
            p.setPen(QColor(CYAN) if pulse > 0.5 else QColor(PINK))
            p.drawText(QRectF(26, 34, 44, 44), Qt.AlignmentFlag.AlignCenter, "\U0001F512")
            # Wordmark with a soft glow, gradient fill and a pulse.
            font = QFont("Helvetica", 42, QFont.Weight.Bold)
            p.setFont(font)
            grad = QLinearGradient(74, 0, 360, 0)
            grad.setColorAt(0, QColor(PINK))
            grad.setColorAt(0.5, QColor(lerp(PINK, "#ffffff", 0.2 * pulse)))
            grad.setColorAt(1, QColor(CYAN))
            glow = QColor(PINK); glow.setAlpha(int(60 + 60 * pulse))
            p.setPen(QPen(glow, 1))
            for dx, dy in ((1.4, 1.4), (-1.4, 1.4), (1.4, -1.4)):
                p.drawText(QRectF(74 + dx, 40 + dy, 420, 56), Qt.AlignmentFlag.AlignVCenter, "ENVY VAULT")
            p.setPen(QPen(QBrush(grad), 1))
            p.drawText(QRectF(74, 40, 420, 56), Qt.AlignmentFlag.AlignVCenter, "ENVY VAULT")
            # Kicker.
            p.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
            p.setPen(QColor(LAVENDER))
            p.drawText(QRectF(78, 104, 500, 20), Qt.AlignmentFlag.AlignVCenter,
                       "AUTHENTICATED  ·  LOCAL  ·  AES-256-GCM")
            # Accent underline + travelling light.
            y = 142
            p.setPen(QPen(QColor(LINE), 2)); p.drawLine(78, y, w - 54, y)
            p.setPen(QPen(QColor(PINK), 3)); p.drawLine(78, y, 150, y)
            span = (w - 54) - 78
            t = (self.phase * 0.12) % 1.0
            x = 78 + span * t
            halo = QRadialGradient(x, y, 16)
            hc = QColor(CYAN); hc.setAlpha(170); halo.setColorAt(0, hc)
            hc2 = QColor(CYAN); hc2.setAlpha(0); halo.setColorAt(1, hc2)
            p.setBrush(QBrush(halo)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, y), 16, 16)
            p.setBrush(QColor("#ffffff")); p.drawEllipse(QPointF(x, y), 2.5, 2.5)
            p.end()

    class Shimmer(QWidget):
        def __init__(self):
            super().__init__()
            self.setFixedHeight(8)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.active = False
            self.phase = 0.0

        def tick(self, phase):
            self.phase = phase
            if self.active:
                self.update()

        def paintEvent(self, _event):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = self.width()
            p.setPen(QPen(QColor(LINE), 2)); p.drawLine(0, 4, w, 4)
            if self.active and w > 0:
                band = (self.phase * 180) % (w + 120) - 120
                grad = QLinearGradient(band, 0, band + 120, 0)
                grad.setColorAt(0, QColor(PINK)); grad.setColorAt(1, QColor(CYAN))
                p.setPen(QPen(QBrush(grad), 4)); p.drawLine(int(band), 4, int(band + 120), 4)
            p.end()

    class Worker(QThread):
        done = pyqtSignal(str, object)

        def __init__(self, mode, source, dest, secret):
            super().__init__()
            self.mode, self.source, self.dest, self.secret = mode, source, dest, secret

        def run(self):
            try:
                self.done.emit("ok", transform_file(self.mode, self.source, self.dest, self.secret))
            except VaultError as exc:
                self.done.emit("error", str(exc))
            except Exception as exc:  # pragma: no cover
                self.done.emit("error", f"Unexpected error: {exc}")

    class VaultWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.mode = "encrypt"
            self.worker = None
            self.setWindowTitle("ENVY Vault")
            self.resize(820, 660)
            self.setMinimumSize(720, 600)
            self.setStyleSheet(STYLE)

            root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
            self.header = Header(); root.addWidget(self.header)

            body = QWidget(); body.setObjectName("body")
            bl = QVBoxLayout(body); bl.setContentsMargins(28, 20, 28, 24); bl.setSpacing(16)
            root.addWidget(body, 1)

            modes = QHBoxLayout(); modes.setSpacing(12)
            self.b_enc = QPushButton("\U0001F512  Encrypt"); self.b_enc.setObjectName("mode")
            self.b_dec = QPushButton("\U0001F513  Decrypt"); self.b_dec.setObjectName("mode")
            for b in (self.b_enc, self.b_dec):
                b.setCheckable(True); b.setMinimumHeight(48); b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.b_enc.clicked.connect(lambda: self.set_mode("encrypt"))
            self.b_dec.clicked.connect(lambda: self.set_mode("decrypt"))
            modes.addWidget(self.b_enc); modes.addWidget(self.b_dec); bl.addLayout(modes)

            card = QFrame(); card.setObjectName("card")
            grid = QGridLayout(card); grid.setContentsMargins(22, 20, 22, 20); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(8)
            bl.addWidget(card, 1)

            self.src = QLineEdit(); self.src.setPlaceholderText("Choose a file…")
            self.dst = QLineEdit(); self.dst.setPlaceholderText("Where to save the result…")
            self.src.textChanged.connect(self.suggest_dest)
            grid.addWidget(self._tag("FILE"), 0, 0, 1, 2)
            grid.addWidget(self.src, 1, 0); grid.addWidget(self._pick("Choose…", self.pick_source), 1, 1)
            grid.addWidget(self._tag("SAVE TO"), 2, 0, 1, 2)
            grid.addWidget(self.dst, 3, 0); grid.addWidget(self._pick("Save as…", self.pick_dest), 3, 1)
            grid.addWidget(self._tag("PASSPHRASE"), 4, 0, 1, 2)
            self.pw = QLineEdit(); self.pw.setEchoMode(QLineEdit.EchoMode.Password)
            self.pw.setPlaceholderText("At least 12 characters")
            self.pw.textChanged.connect(self.update_strength)
            self.pw.returnPressed.connect(self.go)
            grid.addWidget(self.pw, 5, 0)
            show = QCheckBox("Show"); show.toggled.connect(
                lambda on: self.pw.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
            grid.addWidget(show, 5, 1)
            self.strength = QLabel("At least 12 characters."); self.strength.setObjectName("hint")
            grid.addWidget(self.strength, 6, 0, 1, 2)
            grid.setColumnStretch(0, 1)

            actions = QHBoxLayout(); actions.setSpacing(18)
            self.go_btn = QPushButton("Encrypt file  →"); self.go_btn.setObjectName("go")
            self.go_btn.setMinimumHeight(52); self.go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.go_btn.clicked.connect(self.go)
            self.shimmer = Shimmer()
            actions.addWidget(self.go_btn); actions.addWidget(self.shimmer, 1)
            bl.addLayout(actions)

            self.status = QLabel("Ready."); self.status.setObjectName("status"); self.status.setWordWrap(True)
            bl.addWidget(self.status)
            foot = QLabel(f"AES-256-GCM · scrypt · nothing leaves this machine · v{__version__}")
            foot.setObjectName("foot"); bl.addWidget(foot)

            self.phase = 0.0
            self.timer = QTimer(self); self.timer.timeout.connect(self._animate); self.timer.start(33)
            self.set_mode("encrypt")

        def _tag(self, text):
            lab = QLabel(text); lab.setObjectName("tag"); return lab

        def _pick(self, text, slot):
            b = QPushButton(text); b.setObjectName("pick"); b.setMinimumHeight(40)
            b.setCursor(Qt.CursorShape.PointingHandCursor); b.clicked.connect(slot); return b

        def _animate(self):
            self.phase += 0.05
            self.header.tick(self.phase)
            self.shimmer.tick(self.phase)

        def set_mode(self, mode):
            if self.worker:
                return
            self.mode = mode
            self.b_enc.setChecked(mode == "encrypt"); self.b_dec.setChecked(mode == "decrypt")
            accent = PINK if mode == "encrypt" else CYAN
            self.go_btn.setText("Encrypt file  →" if mode == "encrypt" else "Decrypt file  →")
            self.go_btn.setStyleSheet(f"#go{{background:{accent};color:{BG};}}")
            self.strength.setVisible(mode == "encrypt")
            self.suggest_dest(); self.status.setText("Ready to encrypt." if mode == "encrypt" else "Ready to decrypt.")
            self.status.setStyleSheet("")

        def update_strength(self):
            if self.mode != "encrypt":
                return
            n = len(self.pw.text())
            if n == 0:
                self.strength.setText("At least 12 characters."); color = DIM
            elif n < 12:
                self.strength.setText(f"{12 - n} more character(s)."); color = PINK
            else:
                self.strength.setText("Good length."); color = CYAN
            self.strength.setStyleSheet(f"#hint{{color:{color};}}")

        def pick_source(self):
            path, _ = QFileDialog.getOpenFileName(self, "Choose a file")
            if path:
                self.src.setText(path)

        def pick_dest(self):
            path, _ = QFileDialog.getSaveFileName(self, "Save to")
            if path:
                self.dst.setText(path)

        def suggest_dest(self):
            src = self.src.text().strip()
            if not src:
                return
            p = Path(src)
            self.dst.setText(str(p) + ".envy" if self.mode == "encrypt"
                             else (str(p.with_suffix("")) if p.suffix == ".envy" else str(p) + ".out"))

        def go(self):
            if self.worker:
                return
            source, dest = self.src.text().strip(), self.dst.text().strip()
            secret = self.pw.text().encode()
            if not source or not dest:
                return self._fail("Choose a file and where to save it.")
            if self.mode == "encrypt":
                try:
                    check_passphrase(secret)
                except VaultError as exc:
                    return self._fail(str(exc))
            self._set_busy(True)
            self.status.setText("Working…"); self.status.setStyleSheet(f"#status{{color:{CYAN};}}")
            self.worker = Worker(self.mode, source, dest, secret)
            self.worker.done.connect(self._finished); self.worker.start()

        def _fail(self, message):
            self.status.setText(message); self.status.setStyleSheet(f"#status{{color:{PINK};}}")

        def _finished(self, kind, payload):
            self._set_busy(False); self.worker = None
            if kind == "ok":
                verb = "Encrypted" if self.mode == "encrypt" else "Decrypted"
                self.status.setText(f"{verb}  →  {payload['output']}   ({payload['bytes']:,} bytes)")
                self.status.setStyleSheet(f"#status{{color:{CYAN};}}")
            else:
                self._fail(payload)

        def _set_busy(self, value):
            self.shimmer.active = value
            for widget in (self.go_btn, self.b_enc, self.b_dec):
                widget.setEnabled(not value)

    return QApplication, VaultWindow


def lerp(a: str, b: str, t: float):
    from PyQt6.QtGui import QColor
    ca, cb = QColor(a), QColor(b)
    return QColor(int(ca.red() + (cb.red() - ca.red()) * t),
                  int(ca.green() + (cb.green() - ca.green()) * t),
                  int(ca.blue() + (cb.blue() - ca.blue()) * t))


STYLE = f"""
#body {{ background: {BG}; }}
QWidget {{ color: {INK}; font-family: Helvetica, Arial, sans-serif; font-size: 13px; }}
#card {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 16px; }}
#tag {{ color: {MUTED}; font-weight: bold; font-size: 11px; letter-spacing: 1px; }}
#hint {{ color: {DIM}; font-size: 11px; }}
#status {{ color: {MUTED}; font-size: 12px; }}
#foot {{ color: {DIM}; font-family: "Courier New", monospace; font-size: 10px; }}
QLineEdit {{ background: {PANEL_HI}; border: 1px solid {LINE}; border-radius: 9px;
            padding: 9px 11px; color: {INK}; selection-background-color: {VIOLET}; }}
QLineEdit:focus {{ border: 1px solid {CYAN}; }}
QPushButton#mode {{ background: {PANEL_HI}; border: 1px solid {LINE}; border-radius: 12px;
                    color: {MUTED}; font-weight: bold; font-size: 14px; }}
QPushButton#mode:hover {{ border: 1px solid {LAVENDER}; color: {INK}; }}
QPushButton#mode:checked {{ background: {PANEL_HI}; border: 2px solid {PINK}; color: {INK}; }}
QPushButton#pick {{ background: {PANEL_HI}; border: 1px solid {LAVENDER}; border-radius: 9px;
                    color: {INK}; font-weight: bold; padding: 0 14px; }}
QPushButton#pick:hover {{ background: {{LLAV}}; }}
QPushButton#go {{ background: {PINK}; color: {BG}; border: none; border-radius: 12px;
                  font-weight: bold; font-size: 15px; padding: 0 22px; }}
QPushButton#go:disabled {{ background: {PANEL_HI}; color: {DIM}; }}
QCheckBox {{ color: {MUTED}; font-size: 11px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {LINE};
                        border-radius: 4px; background: {PANEL_HI}; }}
QCheckBox::indicator:checked {{ background: {CYAN}; border: 1px solid {CYAN}; }}
""".replace("{LLAV}", "#1b2150")


def run_app() -> int:
    try:
        from PyQt6.QtWidgets import QApplication  # noqa: F401
    except Exception:
        print("PyQt6 is required for the ENVY Vault window. "
              "Use 'envy-vault encrypt FILE OUT' or 'decrypt' in a terminal instead.")
        return 2
    if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print("No display found. Use 'envy-vault encrypt FILE OUT' or 'decrypt' in a terminal instead.")
        return 2
    try:
        QApplication, VaultWindow = _build()
        app = QApplication.instance() or QApplication(sys.argv)
        window = VaultWindow()
        window.show()
        return app.exec()
    except Exception as exc:  # pragma: no cover
        print(f"Could not open the window: {exc}")
        return 2
