import sys
import json
import os
import winreg
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QMenu, QFontDialog, QColorDialog, QDialog,
                             QDateTimeEdit, QDialogButtonBox, QGraphicsDropShadowEffect,
                             QSystemTrayIcon, QInputDialog, QFileDialog)
from PyQt6.QtCore import Qt, QTimer, QDateTime, QPoint
from PyQt6.QtGui import QFont, QColor, QLinearGradient, QPainter, QPen, QBrush, QIcon, QPixmap, QAction

# --- PATH LOGIC ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_CONFIG = os.path.join(BASE_DIR, "default.json")
APP_NAME = "MinimalGlowClockPro"

def create_minimal_clock_icon():
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#00FFFF"), 16)
    painter.setPen(pen)
    painter.drawEllipse(20, 20, 216, 216)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(128, 128, 128, 70)
    painter.drawLine(128, 128, 190, 128)
    painter.setBrush(QBrush(QColor("#00FFFF")))
    painter.drawEllipse(120, 120, 16, 16)
    painter.end()
    return QIcon(pixmap)

class GradientLabel(QLabel):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

    def paintEvent(self, event):
        if not self.settings.get("gradient_on", False):
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.settings["font_family"], self.settings["font_size"], QFont.Weight.Bold)
        painter.setFont(font)
        gradient = QLinearGradient(0, 0, 0, self.height())
        bias = self.settings.get("gradient_balance", 50) / 100.0
        gradient.setColorAt(0, QColor(self.settings["color1"]))
        gradient.setColorAt(bias, QColor(self.settings["color2"]))
        gradient.setColorAt(1, QColor(self.settings["color2"]))
        painter.setPen(QPen(QBrush(gradient), 0))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())
        painter.end()

class FloatingClock(QWidget):
    def __init__(self, settings=None, clock_id=None):
        super().__init__()
        self.clock_id = clock_id or str(datetime.now().timestamp())
        self.settings = settings or {
            "x": 200, "y": 200, "font_family": "Segoe UI Semibold", "font_size": 48,
            "color1": "#FFFFFF", "color2": "#00FFFF", "gradient_on": False,
            "gradient_balance": 50, "glow_on": True, "glow_color": "#00FFFF",
            "glow_radius": 20, "mode": "Time", "target_time": None
        }
        
        # FIX 1: Enhanced Window Flags
        # Tool: Hides from Taskbar
        # Frameless: No borders
        # WindowStaysOnTopHint: Front layer
        # WindowTransparentForInput: NOT used here because we want to drag it
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool |
            Qt.WindowType.NoDropShadowWindowHint
        )
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # FIX 2: Prevent taking focus from other apps
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.layout = QVBoxLayout()
        self.label = GradientLabel(self.settings)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)
        
        self.move(self.settings["x"], self.settings["y"])
        self.update_style()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_display)
        self.timer.start(100)
        self.drag_pos = None

    def update_style(self):
        f = QFont(self.settings["font_family"], self.settings["font_size"], QFont.Weight.Bold)
        self.label.setFont(f)
        if self.settings.get("glow_on", True):
            glow = QGraphicsDropShadowEffect()
            glow.setBlurRadius(self.settings["glow_radius"])
            glow.setColor(QColor(self.settings["glow_color"]))
            glow.setOffset(0, 0)
            self.label.setGraphicsEffect(glow)
        else:
            self.label.setGraphicsEffect(None)
            
        color_style = "transparent" if self.settings["gradient_on"] else self.settings["color1"]
        self.label.setStyleSheet(f"padding: 40px; color: {color_style};")
        self.adjustSize()
        auto_save_default()

    def refresh_display(self):
        # FIX 3: Force the window to the top of the stack periodically
        if not self.isActiveWindow():
             self.raise_()

        if self.settings["mode"] == "Time":
            t = datetime.now().strftime("%H:%M:%S")
        else:
            if self.settings["target_time"]:
                try:
                    rem = datetime.fromisoformat(self.settings["target_time"]) - datetime.now()
                    if rem.total_seconds() > 0:
                        d = rem.days
                        h, r = divmod(rem.seconds, 3600)
                        m, s = divmod(r, 60)
                        t = f"{d}d {h:02d}:{m:02d}:{s:02d}" if d > 0 else f"{h:02d}:{m:02d}:{s:02d}"
                    else: t = "00:00:00"
                except: t = "Error"
            else: t = "Set Target"
        if self.label.text() != t: self.label.setText(t)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        if self.settings["mode"] == "Time":
            menu.addAction("Set Countdown").triggered.connect(self.set_target)
        else:
            menu.addAction("Switch to Real Time").triggered.connect(self.reset_to_time)
        menu.addSeparator()
        style_m = menu.addMenu("Customize Visuals")
        style_m.addAction("Change Font").triggered.connect(self.change_font)
        style_m.addAction("Toggle Gradient").triggered.connect(self.toggle_grad)
        style_m.addAction("Top Color").triggered.connect(self.change_c1)
        style_m.addAction("Bottom Color").triggered.connect(self.change_c2)
        style_m.addAction("Adjust Gradient Bias").triggered.connect(self.change_bias)
        style_m.addAction("Toggle Glow").triggered.connect(self.toggle_glow)
        style_m.addAction("Glow Color").triggered.connect(self.change_glow_color)
        style_m.addAction("Glow Intensity").triggered.connect(self.change_glow_radius)
        menu.addSeparator()
        menu.addAction("➕ Add New Clock").triggered.connect(add_new_clock)
        menu.addAction("📂 Save Current Layout As...").triggered.connect(save_layout_as)
        menu.addAction("📂 Load Layout File...").triggered.connect(load_layout)
        menu.addSeparator()
        menu.addAction("❌ Close This Clock").triggered.connect(self.remove_clock)
        menu.exec(event.globalPos())

    def toggle_grad(self): self.settings["gradient_on"] = not self.settings["gradient_on"]; self.update_style()
    def toggle_glow(self): self.settings["glow_on"] = not self.settings["glow_on"]; self.update_style()
    def change_c1(self): 
        c = QColorDialog.getColor(QColor(self.settings["color1"]), self)
        if c.isValid(): self.settings["color1"] = c.name(); self.update_style()
    def change_c2(self): 
        c = QColorDialog.getColor(QColor(self.settings["color2"]), self)
        if c.isValid(): self.settings["color2"] = c.name(); self.update_style()
    def change_glow_color(self): 
        c = QColorDialog.getColor(QColor(self.settings["glow_color"]), self)
        if c.isValid(): self.settings["glow_color"] = c.name(); self.update_style()
    def change_glow_radius(self):
        val, ok = QInputDialog.getInt(self, "Intensity", "Radius (1-100):", self.settings["glow_radius"], 1, 100, 5)
        if ok: self.settings["glow_radius"] = val; self.update_style()
    def change_bias(self):
        val, ok = QInputDialog.getInt(self, "Bias", "Balance (1-99):", self.settings["gradient_balance"], 1, 99, 5)
        if ok: self.settings["gradient_balance"] = val; self.update_style()
    def change_font(self):
        res = QFontDialog.getFont(self.label.font(), self)
        font, ok = (res[0], res[1]) if isinstance(res[1], bool) else (res[1], res[0])
        if ok: self.settings["font_family"] = font.family(); self.settings["font_size"] = font.pointSize(); self.update_style()

    def set_target(self):
        dialog = QDialog(self); dialog.setWindowTitle("Target Time")
        l = QVBoxLayout(dialog); dt = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        dt.setDisplayFormat("yyyy-MM-dd HH:mm:ss"); dt.setCalendarPopup(True); l.addWidget(dt)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dialog.accept); btns.rejected.connect(dialog.reject); l.addWidget(btns)
        if dialog.exec():
            self.settings["target_time"] = dt.dateTime().toPyDateTime().isoformat()
            self.settings["mode"] = "Countdown"; self.update_style()

    def reset_to_time(self): self.settings["mode"] = "Time"; self.update_style()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
    
    def mouseMoveEvent(self, event):
        if self.drag_pos:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            self.settings["x"], self.settings["y"] = self.x(), self.y()
    
    def mouseReleaseEvent(self, event):
        self.drag_pos = None
        auto_save_default()
    
    def remove_clock(self):
        if self in active_clocks: active_clocks.remove(self)
        self.close()
        auto_save_default()

# --- APP MANAGEMENT ---
active_clocks = []

def add_new_clock():
    c = FloatingClock(); active_clocks.append(c); c.show(); auto_save_default()

def auto_save_default():
    perform_save(DEFAULT_CONFIG)

def save_layout_as():
    path, _ = QFileDialog.getSaveFileName(None, "Save Layout", "", "JSON (*.json)")
    if path: perform_save(path)

def perform_save(path):
    data = [{"id": c.clock_id, "settings": c.settings} for c in active_clocks]
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except: pass

def load_layout():
    path, _ = QFileDialog.getOpenFileName(None, "Open Layout", "", "JSON (*.json)")
    if path:
        for c in active_clocks[:]: c.close()
        active_clocks.clear()
        perform_load(path)
        auto_save_default()

def perform_load(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                for item in json.load(f):
                    c = FloatingClock(item["settings"], item["id"])
                    active_clocks.append(c); c.show()
        except: pass

def toggle_startup():
    path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS) as key:
        if check_startup(): winreg.DeleteValue(key, APP_NAME)
        else:
            cmd = f'"{sys.executable}"' if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)

def check_startup():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME); return True
    except: return False

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    app_icon = create_minimal_clock_icon()
    app.setWindowIcon(app_icon)

    tray = QSystemTrayIcon(app_icon, app)
    tray_menu = QMenu()
    tray_menu.addAction("➕ Add New Clock").triggered.connect(add_new_clock)
    tray_menu.addSeparator()
    tray_menu.addAction("💾 Save Layout As...").triggered.connect(save_layout_as)
    tray_menu.addAction("📂 Load Layout...").triggered.connect(load_layout)
    tray_menu.addSeparator()
    
    startup_action = QAction("🚀 Run at Startup", tray_menu, checkable=True)
    startup_action.setChecked(check_startup())
    startup_action.triggered.connect(toggle_startup)
    tray_menu.addAction(startup_action)
    
    tray_menu.addSeparator()
    tray_menu.addAction("❌ Exit Application").triggered.connect(app.quit)
    tray.setContextMenu(tray_menu)
    tray.show()

    perform_load(DEFAULT_CONFIG)
    
    if not active_clocks:
        add_new_clock()
        
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
