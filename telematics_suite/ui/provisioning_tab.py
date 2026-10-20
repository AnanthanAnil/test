from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton,
    QLineEdit, QComboBox, QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit
)
from PyQt6.QtCore import Qt
from workers.provisioning_worker import ProvisioningWorker, ProvisioningTestRunnerWorker, TestRunConfig, DidReadWorker, ProvisioningInputs

class ProvisioningTab(QWidget):
    def __init__(self, parent_dashboard):
        super().__init__()
        self.dashboard = parent_dashboard
        self._prov_worker = None
        self._test_worker = None
        
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 10, 0, 0)
        main_layout.setSpacing(16)

        row1 = QHBoxLayout()
        row1.addWidget(self._build_prov_card(), stretch=1)
        row1.addWidget(self._build_test_card(), stretch=1)
        main_layout.addLayout(row1, stretch=0)

        row2 = QHBoxLayout()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setObjectName("MonospacePanel")
        row2.addWidget(self.log_view)
        main_layout.addLayout(row2, stretch=1)

    def _build_prov_card(self):
        card = QFrame()
        card.setProperty("class", "panel")
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel("BOARD PROVISIONING"))
        
        self.vin_input = QLineEdit()
        self.vin_input.setPlaceholderText("Enter VIN")
        self.serial_input = QLineEdit()
        self.serial_input.setPlaceholderText("Enter Serial")
        
        layout.addWidget(self.vin_input)
        layout.addWidget(self.serial_input)
        
        btn_start = QPushButton("START PROVISIONING")
        btn_start.setProperty("class", "primaryBtn")
        btn_start.clicked.connect(self.start_provisioning)
        layout.addWidget(btn_start)
        
        self.prov_progress = QProgressBar()
        layout.addWidget(self.prov_progress)
        return card

    def _build_test_card(self):
        card = QFrame()
        card.setProperty("class", "panel")
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel("PROVISIONING FLOW TESTING"))
        
        self.results_table = QTableWidget(0, 7)
        self.results_table.setHorizontalHeaderLabels(["Iter", "Test Flow", "Duration", "Expected", "Actual", "LCU Mode", "Verdict"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.results_table)
        return card

    def log(self, level, msg):
        self.log_view.append(f"[{level}] {msg}")

    def start_provisioning(self):
        device = self.dashboard.current_device_name
        if not device:
            self.log("ERROR", "No device connected")
            return
            
        inputs = ProvisioningInputs(
            vin=self.vin_input.text(), serial=self.serial_input.text(), fuel="PV",
            cert="", key="", provision_client="", reset_script="", app_config_pv="", app_config_ev=""
        )
        
        self._prov_worker = ProvisioningWorker(device, inputs)
        self._prov_worker.log_signal.connect(self.log)
        self._prov_worker.progress_signal.connect(self.prov_progress.setValue)
        self._prov_worker.start()

    def shutdown_workers(self):
        if self._prov_worker: self._prov_worker.request_stop()
        if self._test_worker: self._test_worker.request_stop()