SAAS_THEME = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #0A0A0C, stop:0.5 #121214, stop:1 #1C1C20);
    color: #F3F4F6;
}
QWidget { color: #F3F4F6; font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 11px; }

QFrame#SidebarBox { background-color: #121214; border: 1px solid #28282E; border-radius: 12px; }
QPushButton.navBtn { background-color: transparent; border: 1px solid transparent; color: #9CA3AF; text-align: left; padding: 8px 14px; font-size: 12px; border-radius: 6px; margin: 1px 8px; }
QPushButton.navBtn:hover { background-color: #26263A; border: 1px solid #B2BEB5; color: #E4EAE2; }
QPushButton.navBtn:checked { background-color: #26263A; border: 1px solid #B2BEB5; color: #E4EAE2; font-weight: bold; }

QFrame.panel { background-color: #18181C; border: 1px solid #28282E; border-radius: 12px; padding: 8px; }
QLabel.sectionHeader { color: #B2BEB5; font-size: 12px; font-weight: bold; letter-spacing: 1px; padding-bottom: 3px; border: none; }

QPushButton { background-color: transparent; border: 1px solid #4B5563; border-radius: 6px; padding: 5px 12px; color: #D1D5DB; font-weight: bold; font-size: 10px; }
QPushButton:hover { border-color: #B2BEB5; color: #B2BEB5; background-color: rgba(178, 190, 181, 0.12); }
QPushButton.primaryBtn { border-color: #B2BEB5; color: #B2BEB5; }
QPushButton.dangerBtn { border-color: #ef4444; color: #ef4444; }
QPushButton.successBtn { border-color: #10b981; color: #10b981; }

QComboBox, QLineEdit { background-color: #111118; border: 1px solid #374151; border-radius: 6px; padding: 4px 10px; color: #F3F4F6; font-family: 'Consolas', monospace; }
QTextEdit#MonospacePanel { background-color: #111118; color: #D1D5DB; border: 1px solid #2A2A2E; border-radius: 8px; padding: 8px; font-family: 'Consolas', monospace; }
QProgressBar { background-color: #111118; border: none; border-radius: 2px; text-align: center; color: transparent; height: 6px; }
QProgressBar::chunk { background-color: #B2BEB5; border-radius: 2px; }
"""