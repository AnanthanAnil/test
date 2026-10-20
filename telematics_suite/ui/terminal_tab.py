import html
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, 
                             QPushButton, QTextEdit, QLineEdit, QApplication)
from workers.adb_workers import ADBWorker

class TerminalTab(QWidget):
    def __init__(self, dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.active_worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        
        frame = QFrame()
        frame.setProperty("class", "panel")
        f_layout = QVBoxLayout(frame)
        f_layout.setSpacing(12)

        bar = QHBoxLayout()
        header = QLabel("INTEGRATED TERMINAL OUTPUT")
        header.setProperty("class", "sectionHeader")
        bar.addWidget(header)
        bar.addStretch()

        btn_copy = QPushButton("COPY")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.console_output.toPlainText()))
        btn_clear = QPushButton("CLEAR")
        btn_clear.clicked.connect(self.clear_console)
        bar.addWidget(btn_copy)
        bar.addWidget(btn_clear)
        f_layout.addLayout(bar)

        logcat_row = QHBoxLayout()
        lbl_filter = QLabel("LOGCAT FILTER:")
        self.input_logcat_filter = QLineEdit()
        
        btn_logcat = QPushButton("STREAM LOGCAT")
        btn_logcat.setProperty("class", "primaryBtn")
        btn_logcat.clicked.connect(self.run_logcat)

        self.btn_stop_term = QPushButton("STOP PROCESS")
        self.btn_stop_term.setProperty("class", "dangerBtn")
        self.btn_stop_term.clicked.connect(self.stop_terminal_process)
        self.btn_stop_term.setEnabled(False)

        logcat_row.addWidget(lbl_filter)
        logcat_row.addWidget(self.input_logcat_filter)
        logcat_row.addWidget(btn_logcat)
        logcat_row.addWidget(self.btn_stop_term)
        f_layout.addLayout(logcat_row)

        self.console_output = QTextEdit()
        self.console_output.setObjectName("MonospacePanel")
        self.console_output.setReadOnly(True)
        # Prevent UI freezing during heavy logcat drops
        self.console_output.document().setMaximumBlockCount(2000)
        f_layout.addWidget(self.console_output)

        input_row = QHBoxLayout()
        prefix = QLabel("PS TCU:\\>")
        prefix.setStyleSheet("color: #B2BEB5; font-weight: bold; font-family: 'Consolas', monospace; padding-left: 4px; font-size: 12px; background-color: transparent;")
        
        self.cmd_input = QLineEdit()
        self.cmd_input.setObjectName("PowerShellInput")
        self.cmd_input.returnPressed.connect(self.execute_custom_command)
        
        input_row.addWidget(prefix)
        input_row.addWidget(self.cmd_input)
        f_layout.addLayout(input_row)

        layout.addWidget(frame)

    def log(self, message):
        if message.startswith("\n>"):
            clean_cmd = message.replace('\n> ', '')
            formatted = f"<br><span style='color: #B2BEB5; font-weight: bold;'>PS TCU:\\&gt;</span> <span style='color: #F3F4F6;'>{html.escape(clean_cmd)}</span>"
        elif "<span" not in message:
            escaped = html.escape(message)
            lower = escaped.lower()
            if any(k in lower for k in ["error", "fail", "denied", "not found", "no space"]):
                formatted = f"<span style='color: #ef4444;'>{escaped}</span>" 
            elif "warn" in lower:
                formatted = f"<span style='color: #F59E0B;'>{escaped}</span>" 
            elif any(k in lower for k in ["success", "ok", "done"]):
                formatted = f"<span style='color: #10B981;'>{escaped}</span>" 
            else:
                formatted = f"<span style='color: #D1D5DB;'>{escaped}</span>" 
        else:
            formatted = message

        self.console_output.append(formatted)
        
        # Auto-scroll to bottom safely
        sb = self.console_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_console(self):
        self.console_output.clear()

    def run_live_command(self, cmd_string):
        device = self.dashboard.current_device_name
        if device and cmd_string.startswith("adb ") and "-s" not in cmd_string:
            cmd_string = cmd_string.replace("adb ", f"adb -s {device} ", 1)
            
        self.log(f"\n> {cmd_string}")
        
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.stop()
            self.active_worker.wait()
            
        self.active_worker = ADBWorker(cmd_string)
        self.active_worker.output_signal.connect(self.log)
        self.btn_stop_term.setEnabled(True)
        self.active_worker.finished_signal.connect(lambda: self.btn_stop_term.setEnabled(False))
        self.active_worker.start()

    def execute_custom_command(self):
        cmd = self.cmd_input.text().strip()
        if not cmd: return
        self.cmd_input.clear()
        if not cmd.startswith("adb"): 
            cmd = f"adb shell {cmd}"
        self.run_live_command(cmd)

    def run_logcat(self):
        keyword = self.input_logcat_filter.text().strip()
        device = self.dashboard.current_device_name
        cmd = f"adb -s {device} logcat" if device else "adb logcat"
        
        self.log(f"\n> {cmd} (Filter: '{keyword}')")
        
        if self.active_worker and self.active_worker.isRunning():
            self.active_worker.stop()
            self.active_worker.wait()
            
        self.active_worker = ADBWorker(cmd, filter_keyword=keyword)
        self.active_worker.output_signal.connect(self.log)
        self.btn_stop_term.setEnabled(True)
        self.active_worker.finished_signal.connect(lambda: self.btn_stop_term.setEnabled(False))
        self.active_worker.start()

    def stop_terminal_process(self):
        if self.active_worker: 
            self.active_worker.stop()

    def shutdown_workers(self):
        if self.active_worker:
            self.active_worker.stop()