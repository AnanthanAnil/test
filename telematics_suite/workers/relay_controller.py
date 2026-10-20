import time
from PyQt6.QtCore import QObject, pyqtSignal

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

class RelayController(QObject):
    connection_status = pyqtSignal(bool, str)
    channel_updated = pyqtSignal(int, bool)

    def __init__(self):
        super().__init__()
        self.relay_ser = None
        self.relay_states = {1: True, 2: True, 3: True, 4: True}

    def find_esp32_c3_port(self):
        if not SERIAL_AVAILABLE: return None
        for port in serial.tools.list_ports.comports():
            if port.vid == 0x303A: return port.device
        for port in serial.tools.list_ports.comports():
            desc = port.description.lower()
            if any(k in desc for k in ["usb serial", "ch340", "cp210", "esp", "jtag"]):
                return port.device
        return None

    def connect_serial(self):
        if not SERIAL_AVAILABLE:
            self.connection_status.emit(False, "pyserial not installed")
            return
            
        port_name = self.find_esp32_c3_port()
        if not port_name:
            self.connection_status.emit(False, "Not Found")
            return
            
        try:
            if self.relay_ser and self.relay_ser.is_open:
                self.relay_ser.close()
            # Non-blocking operations initialized
            self.relay_ser = serial.Serial(port_name, 115200, timeout=0.5, write_timeout=0.5)
            self.relay_ser.dtr = True
            time.sleep(1.5)  # Required to allow ESP32 CDC to reset
            self.connection_status.emit(True, port_name)
        except Exception as e:
            self.relay_ser = None
            self.connection_status.emit(False, str(e))

    def _send_command(self, cmd: str):
        if self.relay_ser and self.relay_ser.is_open:
            try:
                self.relay_ser.write((cmd + "\n").encode())
            except Exception:
                self.connection_status.emit(False, "Write Error")

    def set_channel(self, ch: int, power_on: bool):
        cmd = f"R{ch}_OFF" if power_on else f"R{ch}_ON"
        self._send_command(cmd)
        self.relay_states[ch] = power_on
        self.channel_updated.emit(ch, power_on)

    def toggle_master(self):
        any_on = any(self.relay_states.values())
        target_power = not any_on
        cmd = "ALL_OFF" if target_power else "ALL_ON"
        self._send_command(cmd)
        
        for ch in self.relay_states:
            self.relay_states[ch] = target_power
            self.channel_updated.emit(ch, target_power)

    def shutdown(self):
        if self.relay_ser and self.relay_ser.is_open:
            self.relay_ser.close()