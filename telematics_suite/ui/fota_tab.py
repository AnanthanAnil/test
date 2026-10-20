import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QLineEdit, QComboBox, QProgressBar, QTextEdit, QGridLayout, QFileDialog)
from workers.fota_workers import FOTAWorker, DeltaBuilderWorker

class FotaTab(QWidget):
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.fota_worker = None
        self.builder_worker = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 10, 0, 0)
        main_layout.setSpacing(16)

        left_pane = QVBoxLayout()
        left_pane.addWidget(self.create_builder_card())

        cfg_card = QFrame()
        cfg_card.setProperty("class", "panel")
        cfg_layout = QVBoxLayout(cfg_card)
        
        lbl = QLabel("DELTA UPDATE MANAGER")
        lbl.setProperty("class", "sectionHeader")
        cfg_layout.addWidget(lbl)

        r1 = QHBoxLayout()
        self.input_fota_pkg = QLineEdit()
        btn_browse = QPushButton("BROWSE")
        btn_browse.clicked.connect(lambda: self.browse_file(self.input_fota_pkg, "ZIP (*.zip)"))
        r1.addWidget(QLabel("DELTA PACKAGE (.ZIP):"))
        r1.addWidget(self.input_fota_pkg)
        r1.addWidget(btn_browse)
        cfg_layout.addLayout(r1)

        r2 = QHBoxLayout()
        self.btn_fota_start = QPushButton("START FULL FOTA PIPELINE")
        self.btn_fota_start.setProperty("class", "primaryBtn")
        self.btn_fota_start.clicked.connect(self.start_fota)
        r2.addWidget(self.btn_fota_start)
        cfg_layout.addLayout(r2)
        
        left_pane.addWidget(cfg_card)
        main_layout.addLayout(left_pane, stretch=1)

        right_pane = QVBoxLayout()
        f_log_card = QFrame()
        f_log_card.setProperty("class", "panel")
        fl_layout = QVBoxLayout(f_log_card)
        
        fl_hdr = QLabel("FOTA LIVE OUTPUT STREAM")
        fl_hdr.setProperty("class", "sectionHeader")
        fl_layout.addWidget(fl_hdr)

        self.fota_progress = QProgressBar()
        fl_layout.addWidget(self.fota_progress)

        self.fota_output = QTextEdit()
        self.fota_output.setObjectName("MonospacePanel")
        self.fota_output.setReadOnly(True)
        fl_layout.addWidget(self.fota_output)
        
        right_pane.addWidget(f_log_card)
        main_layout.addLayout(right_pane, stretch=1)

    def create_builder_card(self):
        card = QFrame()
        card.setProperty("class", "panel")
        layout = QVBoxLayout(card)
        
        header = QLabel("PACKAGE GENERATOR")
        header.setProperty("class", "sectionHeader")
        layout.addWidget(header)

        self.cb_builder_type = QComboBox()
        self.cb_builder_type.addItems(["NAD_IOC", "NAD_ONLY", "IOC_ONLY"])
        layout.addWidget(self.cb_builder_type)

        self.in_b_nad = QLineEdit()
        btn_browse = QPushButton("BROWSE NAD")
        btn_browse.clicked.connect(lambda: self.browse_file(self.in_b_nad, "ZIP Files (*.zip)"))
        
        row = QHBoxLayout()
        row.addWidget(self.in_b_nad)
        row.addWidget(btn_browse)
        layout.addLayout(row)
        
        return card

    def browse_file(self, target, file_filter):
        p, _ = QFileDialog.getOpenFileName(self, "Select", "", file_filter)
        if p: target.setText(p)

    def start_fota(self):
        device = self.dashboard.current_device_name
        pkg = self.input_fota_pkg.text().strip()
        if not device or not pkg: return
        
        self.fota_output.clear()
        self.fota_worker = FOTAWorker(device, pkg)
        self.fota_worker.log_signal.connect(self.fota_output.append)
        self.fota_worker.progress_signal.connect(self.fota_progress.setValue)
        self.fota_worker.start()

    def shutdown_workers(self):
        if self.fota_worker: self.fota_worker.stop()
        if self.builder_worker: self.builder_worker.stop()