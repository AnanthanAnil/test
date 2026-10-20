import os
import re
from collections import deque
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QTextEdit, QScrollArea
)
from PyQt6.QtCore import QTimer
from .custom_widgets import LiveSmoothLineChart
from workers.adb_workers import SilentFetchWorker, FirmwareFetchWorker

class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_device_name = None
        self.boot_fetched = False
        self.esync_fetch_in_progress = False

        self.fw_worker = None
        self.boot_worker = None
        self.esync_worker = None

        self.fw_labels = {
            "T.OS Version:": QLabel("—"), "T.OS Core Version:": QLabel("—"),
            "Harman Version:": QLabel("—"), "eSync Version:": QLabel("—"),
            "Quectel Version:": QLabel("—"), "IOC Version:": QLabel("—"),
            "VIN:": QLabel("—"), "VID:": QLabel("—"), "IMEI:": QLabel("—"),
            "ICCID:": QLabel("—"), "Serial Number:": QLabel("—"),
            "HABL System State:": QLabel("—"), "LCM Current Mode:": QLabel("—"),
            "Fuel Type:": QLabel("—")
        }

        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.setSpacing(16)

        # 1. Device Vitals (CPU/RAM Charts)
        chart_card = self._create_panel("DEVICE VITALS")
        chart_layout = chart_card.layout()

        self.cpu_lbl = QLabel("—%")
        self.cpu_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #22d3ee;")
        chart_layout.addWidget(self.cpu_lbl)
        self.cpu_chart = LiveSmoothLineChart(accent_color="#22d3ee")
        self.cpu_chart.setMinimumHeight(80)
        chart_layout.addWidget(self.cpu_chart)

        self.ram_lbl = QLabel("—%")
        self.ram_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #a78bfa;")
        chart_layout.addWidget(self.ram_lbl)
        self.ram_chart = LiveSmoothLineChart(accent_color="#a78bfa")
        self.ram_chart.setMinimumHeight(80)
        chart_layout.addWidget(self.ram_chart)

        # Column 1 layout wrapper
        col1_widget = QWidget()
        col1_layout = QVBoxLayout(col1_widget)
        col1_layout.setContentsMargins(0, 0, 0, 0)
        col1_layout.addWidget(chart_card)
        top_row.addWidget(col1_widget, stretch=4)

        # 2. Boot Timings & eSync (Column 2)
        col2_widget = QWidget()
        col2_layout = QVBoxLayout(col2_widget)
        col2_layout.setContentsMargins(0, 0, 0, 0)

        boot_card = self._create_panel("BOOT TIMINGS")
        self.lbl_boot_total = QLabel("—")
        self.lbl_boot_total.setStyleSheet("font-size: 14px; font-weight: bold; color: #10b981;")
        boot_card.layout().addWidget(QLabel("TOTAL BOOT:"))
        boot_card.layout().addWidget(self.lbl_boot_total)
        col2_layout.addWidget(boot_card)

        esync_card = self._create_panel("ESYNC HEALTH")
        self.esync_container = QWidget()
        self.esync_layout = QVBoxLayout(self.esync_container)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.esync_container)
        esync_card.layout().addWidget(scroll)
        
        btn_refresh_esync = QPushButton("REFRESH ESYNC STATE")
        btn_refresh_esync.clicked.connect(self.fetch_esync_manual)
        esync_card.layout().addWidget(btn_refresh_esync)
        col2_layout.addWidget(esync_card)

        # 3. System Architecture (Column 3)
        arch_card = self._create_panel("SYSTEM ARCHITECTURE")
        arch_scroll = QScrollArea()
        arch_scroll.setWidgetResizable(True)
        arch_container = QWidget()
        arch_v_layout = QVBoxLayout(arch_container)
        for key, lbl_val in self.fw_labels.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(key))
            row.addWidget(lbl_val)
            arch_v_layout.addLayout(row)
        arch_scroll.setWidget(arch_container)
        arch_card.layout().addWidget(arch_scroll)

        right_top_row = QHBoxLayout()
        right_top_row.addWidget(col2_widget, stretch=3)
        right_top_row.addWidget(arch_card, stretch=4)
        top_row.addLayout(right_top_row, stretch=7)

        main_layout.addLayout(top_row)

    def _create_panel(self, title: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "panel")
        layout = QVBoxLayout(card)
        lbl = QLabel(title)
        lbl.setProperty("class", "sectionHeader")
        layout.addWidget(lbl)
        return card

    def on_device_connected(self, device_name):
        self.current_device_name = device_name
        self.trigger_firmware_fetch()
        if not self.boot_fetched:
            self.fetch_boot_timings()

    def on_device_disconnected(self):
        self.current_device_name = None
        self.boot_fetched = False
        for label in self.fw_labels.values():
            label.setText("—")

    def trigger_firmware_fetch(self):
        if not self.current_device_name: return
        if self.fw_worker and self.fw_worker.isRunning(): return
        
        for label in self.fw_labels.values(): label.setText("Reading...")
        self.fw_worker = FirmwareFetchWorker(self.current_device_name)
        self.fw_worker.info_signal.connect(self.populate_firmware_ui)
        self.fw_worker.start()

    def populate_firmware_ui(self, fw_dict):
        for key, label in self.fw_labels.items():
            label.setText(fw_dict.get(key, "—"))

    def fetch_boot_timings(self):
        if not self.current_device_name: return
        if self.boot_worker and self.boot_worker.isRunning(): return

        self.boot_fetched = True
        self.lbl_boot_total.setText("Reading...")
        
        cmd = (
            f'adb -s {self.current_device_name} shell '
            f'"systemd-analyze 2>/dev/null || dmesg | grep -E -i \'boot|init|systemd\' | tail -n 25"'
        )
        self.boot_worker = SilentFetchWorker(cmd)
        self.boot_worker.result_signal.connect(self.populate_boot_timings)
        self.boot_worker.start()

    def populate_boot_timings(self, output):
        startup_match = re.search(r'=\s*([\d\.]+[m]?s)', output)
        if startup_match:
            self.lbl_boot_total.setText(startup_match.group(1).strip())
        else:
            self.lbl_boot_total.setText("N/A")

    def fetch_esync_manual(self):
        if not self.current_device_name or self.esync_fetch_in_progress:
            return
        self.esync_fetch_in_progress = True
        self.esync_worker = SilentFetchWorker(f'adb -s {self.current_device_name} shell "/oemapp/esync/start.sh"')
        self.esync_worker.result_signal.connect(self.populate_esync_services)
        self.esync_worker.start()

    def populate_esync_services(self, raw_text):
        self.esync_fetch_in_progress = False
        while self.esync_layout.count():
            item = self.esync_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        clean_text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw_text)
        for line in clean_text.splitlines():
            if not line.strip(): continue
            lbl = QLabel(line.strip())
            self.esync_layout.addWidget(lbl)

    def shutdown_workers(self):
        if self.fw_worker: self.fw_worker.stop()
        if self.boot_worker: self.boot_worker.stop()
        if self.esync_worker: self.esync_worker.stop()