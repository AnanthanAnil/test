import time
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QMessageBox)
from PyQt6.QtGui import QShortcut, QKeySequence
from .custom_widgets import ToggleSwitch

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

class RelayTab(QWidget):
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.relay_ser = None
        self.relay_states = {1: True, 2: True, 3: True, 4: True}
        self.relay_channel_widgets = {}
        self._build_ui()
        self.setup_shortcuts()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 10, 0, 0)
        
        card = QFrame()
        card.setProperty("class", "panel")
        card.setFixedWidth(360)
        c_layout = QVBoxLayout(card)

        hdr = QLabel("IGN CONTROL")
        hdr.setProperty("class", "sectionHeader")
        c_layout.addWidget(hdr)

        self.lbl_relay_port = QLabel("Port: Scanning...")
        c_layout.addWidget(self.lbl_relay_port)

        channels_frame = QFrame()
        channels_frame.setStyleSheet("background-color: #0E0E10; border: 1px solid #28282E; border-radius: 8px;")
        ch_layout = QVBoxLayout(channels_frame)

        for ch in range(1, 5):
            row = QHBoxLayout()
            name_lbl = QLabel(f"Device {ch} [Key {ch}]:")
            st_lbl = QLabel("ON")
            st_lbl.setStyleSheet("color: #10b981; font-weight: bold;")
            
            switch = ToggleSwitch()
            switch.setChecked(True)
            switch.clicked.connect(lambda on, c=ch: self.relay_set_channel(c, on))
            
            row.addWidget(name_lbl)
            row.addWidget(st_lbl)
            row.addStretch()
            row.addWidget(switch)
            
            ch_layout.addLayout(row)
            self.relay_channel_widgets[ch] = (st_lbl, switch)

        c_layout.addWidget(channels_frame)

        self.btn_master = QPushButton("ALL OFF (Ctrl+A)")
        self.btn_master.setProperty("class", "dangerBtn")
        self.btn_master.clicked.connect(self.relay_master_toggle)
        c_layout.addWidget(self.btn_master)

        btn_rescan = QPushButton("RESCAN / RECONNECT")
        btn_rescan.clicked.connect(self.relay_connect_serial)
        c_layout.addWidget(btn_rescan)
        
        main_layout.addWidget(card)
        main_layout.addStretch()

    def setup_shortcuts(self):
        for ch in range(1, 5):
            sc = QShortcut(QKeySequence(str(ch)), self)
            sc.activated.connect(lambda c=ch: self.relay_set_channel(c, not self.relay_states.get(c, True)))
        
        sc_master = QShortcut(QKeySequence("Ctrl+A"), self)
        sc_master.activated.connect(self.relay_master_toggle)

    def relay_connect_serial(self):
        if not SERIAL_AVAILABLE:
            self.lbl_relay_port.setText("pyserial not installed")
            return
            
        port_name = next((p.device for p in serial.tools.list_ports.comports() if p.vid == 0x303A), None)
        if not port_name:
            self.lbl_relay_port.setText("Port: Not Found")
            return
            
        try:
            if self.relay_ser and self.relay_ser.is_open: self.relay_ser.close()
            self.relay_ser = serial.Serial(port_name, 115200, timeout=1)
            self.relay_ser.dtr = True
            self.lbl_relay_port.setText(f"Connected ({port_name})")
        except Exception:
            self.relay_ser = None
            self.lbl_relay_port.setText("Port: Error Opening")

    def relay_set_channel(self, ch, power_on):
        cmd = f"R{ch}_OFF" if power_on else f"R{ch}_ON"
        if self.relay_ser and self.relay_ser.is_open:
            self.relay_ser.write((cmd + "\n").encode())
            
        self.relay_states[ch] = power_on
        lbl, switch = self.relay_channel_widgets[ch]
        
        switch.blockSignals(True)
        switch.setChecked(power_on)
        switch.blockSignals(False)
        
        lbl.setText("ON" if power_on else "OFF")
        lbl.setStyleSheet(f"color: {'#10b981' if power_on else '#ef4444'}; font-weight: bold;")

    def relay_master_toggle(self):
        any_on = any(self.relay_states.values())
        target = not any_on
        cmd = "ALL_OFF" if target else "ALL_ON"
        
        if self.relay_ser and self.relay_ser.is_open:
            self.relay_ser.write((cmd + "\n").encode())
            
        for ch in self.relay_states:
            self.relay_set_channel(ch, target)

    def shutdown_workers(self):
        if self.relay_ser and self.relay_ser.is_open:
            self.relay_ser.close()