import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
                             QPushButton, QTextEdit, QProgressBar, QFileDialog, QMessageBox)
from workers.fota_workers import AutomationWorker

class AutomationTab(QWidget):
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.auto_worker = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 10, 0, 0)
        main_layout.setSpacing(20)

        # Left Column: Script Editor
        left_col = QVBoxLayout()
        edit_card = QFrame()
        edit_card.setProperty("class", "panel")
        edit_layout = QVBoxLayout(edit_card)
        
        lbl_ed = QLabel("BATCH SCRIPT EDITOR")
        lbl_ed.setProperty("class", "sectionHeader")
        edit_layout.addWidget(lbl_ed)

        self.txt_script_editor = QTextEdit()
        self.txt_script_editor.setObjectName("MonospacePanel")
        edit_layout.addWidget(self.txt_script_editor)

        btn_row = QHBoxLayout()
        btn_load = QPushButton("LOAD SCRIPT")
        btn_load.clicked.connect(self.load_script)
        btn_save = QPushButton("SAVE SCRIPT")
        btn_save.clicked.connect(self.save_script)
        
        self.btn_run_auto = QPushButton("RUN AUTOMATION")
        self.btn_run_auto.setProperty("class", "primaryBtn")
        self.btn_run_auto.clicked.connect(self.run_automation)
        
        self.btn_stop_auto = QPushButton("STOP")
        self.btn_stop_auto.setProperty("class", "dangerBtn")
        self.btn_stop_auto.clicked.connect(self.stop_automation)
        self.btn_stop_auto.setEnabled(False)
        
        btn_row.addWidget(btn_load)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(self.btn_run_auto)
        btn_row.addWidget(self.btn_stop_auto)

        edit_layout.addLayout(btn_row)
        left_col.addWidget(edit_card)
        main_layout.addLayout(left_col, stretch=1)

        # Right Column: Execution Output
        right_col = QVBoxLayout()
        out_card = QFrame()
        out_card.setProperty("class", "panel")
        out_layout = QVBoxLayout(out_card)
        
        lbl_out = QLabel("EXECUTION OUTPUT")
        lbl_out.setProperty("class", "sectionHeader")
        out_layout.addWidget(lbl_out)

        self.auto_progress = QProgressBar()
        self.auto_progress.setRange(0, 100)
        out_layout.addWidget(self.auto_progress)

        self.txt_auto_output = QTextEdit()
        self.txt_auto_output.setObjectName("MonospacePanel")
        self.txt_auto_output.setReadOnly(True)
        # Prevent memory bloat from massive logs
        self.txt_auto_output.document().setMaximumBlockCount(1500)
        out_layout.addWidget(self.txt_auto_output)

        btn_clear_out = QPushButton("CLEAR")
        btn_clear_out.clicked.connect(self.txt_auto_output.clear)
        out_layout.addWidget(btn_clear_out)
        
        right_col.addWidget(out_card)
        main_layout.addLayout(right_col, stretch=1)

    def load_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Script", "", "Text Files (*.txt);;All Files (*)")
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.txt_script_editor.setPlainText(f.read())

    def save_script(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Script", "automation_script.txt", "Text Files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_script_editor.toPlainText())

    def run_automation(self):
        device = self.dashboard.current_device_name
        script_text = self.txt_script_editor.toPlainText()
        
        if not device:
            QMessageBox.warning(self, "No Device", "Please connect a device first.")
            return
            
        if not script_text.strip():
            return

        self.txt_auto_output.clear()
        self.auto_progress.setValue(0)
        self.btn_run_auto.setEnabled(False)
        self.btn_stop_auto.setEnabled(True)

        lines = script_text.splitlines()
        self.auto_worker = AutomationWorker(device, lines)
        self.auto_worker.log_signal.connect(self.txt_auto_output.append)
        self.auto_worker.progress_signal.connect(self.auto_progress.setValue)
        self.auto_worker.finished_signal.connect(self.on_automation_finished)
        self.auto_worker.start()

    def stop_automation(self):
        if self.auto_worker:
            self.auto_worker.stop()

    def on_automation_finished(self, success):
        self.btn_run_auto.setEnabled(True)
        self.btn_stop_auto.setEnabled(False)

    def shutdown_workers(self):
        if self.auto_worker:
            self.auto_worker.stop()