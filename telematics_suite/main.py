import sys
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QFrame, QLabel, QPushButton, QComboBox
)
from PyQt6.QtCore import QTimer, Qt

# Internal Package Imports
from ui.styles import SAAS_THEME

# These will be the decoupled UI components (to be created next)
from ui.dashboard_tab import DashboardTab
from ui.provisioning_tab import ProvisioningTab
from ui.fota_tab import FotaTab
from ui.relay_tab import RelayTab
from ui.automation_tab import AutomationTab
from ui.terminal_tab import TerminalTab

class TelecomSaaSDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # High DPI Scaling
        if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

        self.setWindowTitle("Telematics Suite")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(SAAS_THEME)

        # Global State
        self.current_is_connected = False
        self.current_device_name = None
        self.nav_buttons = []

        self._build_main_layout()

        # Global Device Watchdog
        self.watchdog_timer = QTimer(self)
        self.watchdog_timer.timeout.connect(lambda: self.scan_adb_devices(silent=True))
        self.watchdog_timer.start(3000)

        # Initial Scan
        self.scan_adb_devices(silent=False)

    def _build_main_layout(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # Margins to create the "floating box" sidebar effect
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(25)

        # 1. Floating Sidebar
        main_layout.addWidget(self.create_sidebar())

        # 2. Main Content Area
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # 3. Stacked Widget (Tab Manager)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, stretch=1)
        main_layout.addWidget(content_area, stretch=1)

        # Initialize and inject UI Tabs
        self.dashboard_tab = DashboardTab(self)
        self.provisioning_tab = ProvisioningTab(self)
        self.fota_tab = FotaTab(self)
        self.automation_tab = AutomationTab(self)
        self.terminal_tab = TerminalTab(self)
        self.relay_tab = RelayTab(self)

        self.stack.addWidget(self.dashboard_tab)     # Index 0
        self.stack.addWidget(self.provisioning_tab)  # Index 1
        self.stack.addWidget(self.fota_tab)          # Index 2
        self.stack.addWidget(self.automation_tab)    # Index 3
        self.stack.addWidget(self.terminal_tab)      # Index 4
        self.stack.addWidget(self.relay_tab)         # Index 5

    def create_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("SidebarBox")
        sidebar.setFixedWidth(240)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 30, 10, 30)
        
        logo = QLabel("TELEMATICS SUITE")
        logo.setStyleSheet("font-size: 20px; font-weight: bold; letter-spacing: 1px; color: #F3F4F6; padding-left: 10px; margin-bottom: 20px; border: none;")
        sidebar_layout.addWidget(logo)

        nav_items = [
            "Dashboard Overview", 
            "Board Provisioning", 
            "FOTA Updates", 
            "Test Automation", 
            "Terminal Interface", 
            "Ignition Control"
        ]

        for idx, item in enumerate(nav_items):
            btn = QPushButton(item)
            btn.setProperty("class", "navBtn")
            btn.setCheckable(True)
            if idx == 0: 
                btn.setChecked(True)
            
            btn.clicked.connect(lambda checked, i=idx: self.switch_tab(i))
            sidebar_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        sidebar_layout.addStretch()
        sidebar_layout.addWidget(self.create_device_box())
        return sidebar

    def create_device_box(self) -> QFrame:
        device_box = QFrame()
        device_box.setStyleSheet("background-color: #0E0E10; border: 1px solid #28282E; border-radius: 8px;")
        db_layout = QVBoxLayout(device_box)
        db_layout.setContentsMargins(12, 12, 12, 12)
        db_layout.setSpacing(8)

        self.device_combo = QComboBox()
        self.device_combo.setFixedHeight(32)
        self.device_combo.currentIndexChanged.connect(self.on_device_selection_changed)
        db_layout.addWidget(self.device_combo)

        btn_refresh = QPushButton("REFRESH")
        btn_refresh.setProperty("class", "primaryBtn")
        btn_refresh.setFixedHeight(32)
        btn_refresh.clicked.connect(lambda: self.scan_adb_devices(silent=False))
        db_layout.addWidget(btn_refresh)

        self.status_pill = QLabel("OFFLINE")
        self.status_pill.setFixedHeight(32)
        self.status_pill.setStyleSheet("border: 1px solid #ef4444; border-radius: 6px; font-size: 11px; font-weight: bold; color: #ef4444; text-transform: uppercase;")
        self.status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        db_layout.addWidget(self.status_pill)

        return device_box

    def switch_tab(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)

    def scan_adb_devices(self, silent: bool = True):
        """Polls for ADB devices and triggers UI updates if topology changes."""
        try:
            result = subprocess.check_output(
                "adb devices", 
                shell=True, 
                text=True, 
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            lines = result.strip().split('\n')[1:]
            devices = [parts[0] for parts in (line.split() for line in lines) if len(parts) >= 2 and parts[1] == 'device']

            current = self.device_combo.currentText()
            existing = [self.device_combo.itemText(i) for i in range(self.device_combo.count())]
            cleaned_existing = [i for i in existing if i not in ["No devices found", "Error scanning", ""]]

            if set(devices) != set(cleaned_existing):
                self.device_combo.blockSignals(True)
                self.device_combo.clear()
                if devices:
                    self.device_combo.addItems(devices)
                    if current in devices:
                        self.device_combo.setCurrentText(current)
                    else:
                        self.device_combo.setCurrentIndex(0)
                else: 
                    self.device_combo.addItem("No devices found")
                self.device_combo.blockSignals(False)
                self.on_device_selection_changed()

            elif devices and not self.current_is_connected:
                self.on_device_selection_changed()
            elif not devices and self.current_is_connected:
                self.on_device_selection_changed()

        except Exception as e:
            self.current_is_connected = False
            self.current_device_name = None
            self.update_connection_ui()

    def on_device_selection_changed(self):
        """Propagates the connected device state to all child tabs."""
        selected = self.device_combo.currentText().strip()

        if selected and selected not in ["No devices found", "Error scanning", ""]:
            is_new_device = (self.current_device_name != selected) or (not self.current_is_connected)
            self.current_device_name = selected
            self.current_is_connected = True
            
            if is_new_device:
                self.dashboard_tab.on_device_connected(selected)
        else:
            self.current_device_name = None
            self.current_is_connected = False
            self.dashboard_tab.on_device_disconnected()

        self.update_connection_ui()

    def update_connection_ui(self):
        if self.current_is_connected and self.current_device_name:
            self.status_pill.setText("ONLINE")
            self.status_pill.setStyleSheet("border: 1px solid #10b981; border-radius: 6px; font-size: 11px; font-weight: bold; color: #10b981; text-transform: uppercase;")
        else:
            self.status_pill.setText("OFFLINE")
            self.status_pill.setStyleSheet("border: 1px solid #ef4444; border-radius: 6px; font-size: 11px; font-weight: bold; color: #ef4444; text-transform: uppercase;")

    def closeEvent(self, event):
        """Ensures all workers, hardware threads, and serial ports gracefully shut down."""
        self.watchdog_timer.stop()
        self.dashboard_tab.shutdown_workers()
        self.provisioning_tab.shutdown_workers()
        self.fota_tab.shutdown_workers()
        self.terminal_tab.shutdown_workers()
        self.relay_tab.shutdown_workers()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = TelecomSaaSDashboard()
    window.showMaximized()
    sys.exit(app.exec())