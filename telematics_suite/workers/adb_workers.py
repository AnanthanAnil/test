import sys
import subprocess
import re
import time
from PyQt6.QtCore import QThread, pyqtSignal

class ADBWorker(QThread):
    output_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, command, filter_keyword=""):
        super().__init__()
        self.command = command
        self.filter_keyword = filter_keyword
        self.process = None
        self.is_running = True

    def run(self):
        try:
            self.process = subprocess.Popen(
                self.command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                shell=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            while self.is_running:
                line = self.process.stdout.readline()
                if not line:
                    break
                stripped = line.strip()
                if not self.filter_keyword or self.filter_keyword.lower() in stripped.lower():
                    self.output_signal.emit(stripped)
            self.process.wait()
        except Exception as e:
            if self.is_running:
                self.output_signal.emit(f"[Error]: {str(e)}")
        finally:
            self.finished_signal.emit()

    def stop(self):
        self.is_running = False
        if self.process:
            try:
                if self.process.stdout:
                    self.process.stdout.close()
                if sys.platform == 'win32':
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self.process.terminate()
                    self.process.kill()
            except Exception:
                pass


class SilentFetchWorker(QThread):
    result_signal = pyqtSignal(str)

    def __init__(self, command):
        super().__init__()
        self.command = command

    def run(self):
        try:
            res = subprocess.run(
                self.command, shell=True, capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            output = res.stdout.strip()
            if not output and res.stderr:
                output = res.stderr.strip()
            self.result_signal.emit(output if output else "No output returned.")
        except Exception as e:
            self.result_signal.emit(f"Error fetching data:\n{str(e)}")


class HardwareMonitorWorker(QThread):
    stats_signal = pyqtSignal(float, float, str)

    def __init__(self, get_status_callback, interval=1.0):
        super().__init__()
        self.get_status_callback = get_status_callback
        self.interval = interval
        self.running = True
        self.is_paused = False
        self.prev_total = 0
        self.prev_idle = 0

    def run(self):
        while self.running:
            if self.is_paused:
                time.sleep(self.interval)
                continue
            is_connected, device = self.get_status_callback()
            if not is_connected or not device:
                self.stats_signal.emit(-1.0, -1.0, "--- Device Offline ---")
                time.sleep(self.interval)
                continue

            prefix = f"adb -s {device} shell"
            try:
                proc_res = subprocess.check_output(f"{prefix} cat /proc/stat", shell=True, text=True, stderr=subprocess.DEVNULL)
                fields = [float(x) for x in proc_res.strip().split("\n")[0].split()[1:]]
                idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
                total = sum(fields)
                cpu_pct = 0.0
                if self.prev_total > 0:
                    delta_total = total - self.prev_total
                    delta_idle = idle - self.prev_idle
                    if delta_total > 0:
                        cpu_pct = max(0.0, min(100.0, (1.0 - (delta_idle / delta_total)) * 100.0))
                self.prev_total = total
                self.prev_idle = idle

                ram_res = subprocess.check_output(f"{prefix} cat /proc/meminfo", shell=True, text=True, stderr=subprocess.DEVNULL)
                mem_total, mem_avail = 1, 1
                for line in ram_res.splitlines():
                    if "MemTotal:" in line:
                        mem_total = int(re.sub(r'\D', '', line))
                    if "MemAvailable:" in line or "MemFree:" in line:
                        mem_avail = int(re.sub(r'\D', '', line))
                ram_pct = 100.0 * (1.0 - (mem_avail / max(mem_total, 1)))

                top_res = subprocess.check_output(f"{prefix} \"top -b -n 1 | head -n 12\"", shell=True, text=True, stderr=subprocess.DEVNULL)
                self.stats_signal.emit(cpu_pct, ram_pct, top_res)
            except Exception:
                self.stats_signal.emit(-1.0, -1.0, "--- Device Query Failed ---")
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        self.wait()


class PingMonitorWorker(QThread):
    ping_signal = pyqtSignal(bool, bool)

    def __init__(self, get_status_callback, interval=2.0):
        super().__init__()
        self.get_status_callback = get_status_callback
        self.interval = interval
        self.running = True
        self.is_paused = True

    def run(self):
        while self.running:
            if self.is_paused:
                time.sleep(self.interval)
                continue
            is_connected, device = self.get_status_callback()
            if not is_connected or not device:
                self.ping_signal.emit(False, False)
                time.sleep(self.interval)
                continue
            prefix = f"adb -s {device} shell"
            cmd_dns = f"{prefix} ping -c 1 -W 1 8.8.8.8"
            res_dns = subprocess.run(cmd_dns, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd_web = f"{prefix} ping -c 1 -W 1 google.com"
            res_web = subprocess.run(cmd_web, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.ping_signal.emit((res_dns.returncode == 0), (res_web.returncode == 0))
            time.sleep(self.interval)

    def stop(self):
        self.running = False


class ThermalMonitorWorker(QThread):
    thermal_signal = pyqtSignal(dict)
    ZONE_PREFIXES = ("cpuss", "tsens-max", "mdmss", "mdmq6", "pmx75", "ethphy", "sys-therm")

    def __init__(self, get_status_callback, interval=2.0):
        super().__init__()
        self.get_status_callback = get_status_callback
        self.interval = interval
        self.running = True

    def run(self):
        shell_script = (
            'for z in /sys/class/thermal/thermal_zone*; do '
            'echo $(cat $z/type 2>/dev/null):$(cat $z/temp 2>/dev/null); '
            'done'
        )
        while self.running:
            is_connected, device = self.get_status_callback()
            if not is_connected or not device:
                time.sleep(self.interval)
                continue
            try:
                cmd = f'adb -s {device} shell "{shell_script}"'
                res = subprocess.check_output(
                    cmd, shell=True, text=True, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                zones = {}
                for line in res.splitlines():
                    line = line.strip()
                    if ":" not in line:
                        continue
                    name, _, raw_temp = line.partition(":")
                    name = name.strip()
                    raw_temp = raw_temp.strip()
                    if not name or not name.startswith(self.ZONE_PREFIXES):
                        continue
                    if not re.match(r'^-?\d+$', raw_temp):
                        continue
                    temp_c = int(raw_temp) / 1000.0
                    if temp_c <= 0:
                        continue
                    zones[name] = temp_c
                if zones:
                    self.thermal_signal.emit(zones)
            except Exception:
                pass
            time.sleep(self.interval)

    def stop(self):
        self.running = False
        self.wait()


class FirmwareFetchWorker(QThread):
    info_signal = pyqtSignal(dict)
    BOOT_WAIT_SECONDS = 300
    FETCH_ATTEMPTS = 6
    FETCH_RETRY_SECONDS = 10
    IDENTITY_KEYS = ("VIN:", "Serial Number:", "IMEI:", "ICCID:")

    def __init__(self, device):
        super().__init__()
        self.device = device
        self._root_done = False

    @staticmethod
    def _is_not_ready(value):
        return bool(value) and re.fullmatch(r'[Ff]+', value.strip()) is not None

    def _wait_for_boot(self):
        deadline = time.monotonic() + self.BOOT_WAIT_SECONDS
        while time.monotonic() < deadline:
            try:
                state = subprocess.run(
                    f'adb -s {self.device} shell "systemctl is-system-running"', shell=True,
                    capture_output=True, text=True, timeout=15,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                ).stdout.strip()
            except Exception:
                state = ""
            if state in ("running", "degraded"):
                return
            time.sleep(5)

    def run(self):
        if not self.device or self.device == "None":
            return
        self._wait_for_boot()
        parsed = {}
        for attempt in range(self.FETCH_ATTEMPTS):
            parsed = self._collect_once() or {}
            if not any(self._is_not_ready(parsed.get(key)) for key in self.IDENTITY_KEYS):
                break
            time.sleep(self.FETCH_RETRY_SECONDS)
        for key in self.IDENTITY_KEYS:
            if self._is_not_ready(parsed.get(key)):
                parsed[key] = "Not Ready"
        self.info_signal.emit(parsed)

    def _collect_once(self):
        prefix = f"adb -s {self.device}"
        parsed_data = {}
        if not self._root_done:
            try:
                subprocess.run(f"{prefix} root", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(f"{prefix} wait-for-device", shell=True, timeout=8)
            except Exception:
                pass
            self._root_done = True
        time.sleep(1)

        try:
            res = subprocess.check_output(f"{prefix} shell cat /etc/tos-project-revision", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in res.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    parsed_data[k.strip() + ":"] = v.strip()
        except Exception:
            pass

        try:
            vid_res = subprocess.check_output(f"{prefix} shell cat /store/config_store/config-0.json", shell=True, text=True, stderr=subprocess.DEVNULL)
            match = re.search(r'"clientId"\s*:\s*"([^"]+)"', vid_res)
            if match:
                parsed_data["VID:"] = match.group(1)
        except Exception:
            parsed_data["VID:"] = "Not Found"

        habl_cmd = (
            f'{prefix} shell "BIN=\\"/oemapp/harman_test_apps/habl/habl_test_client\\"; '
            f'[ ! -f \\"$BIN\\" ] && BIN=\\"/oemapp/harman_test_apps/habl/habl_client\\"; '
            f'(echo 4; sleep 1; echo -1) | \\"$BIN\\""'
        )

        try:
            res = subprocess.run(habl_cmd, shell=True, capture_output=True, text=True, timeout=6)
            combined_output = res.stdout + ("\n" + res.stderr if res.stderr else "")
            clean_habl_out = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', combined_output)
            match = re.search(r'Current\s+System\s+State\s*[:=]\s*([A-Za-z0-9_]+)', clean_habl_out, re.IGNORECASE)
            if not match:
                match = re.search(r'System\s+State\s*[:=]\s*([A-Za-z0-9_]+)', clean_habl_out, re.IGNORECASE)
            parsed_data["HABL System State:"] = match.group(1).strip() if match else "Not Found"
        except subprocess.TimeoutExpired:
            parsed_data["HABL System State:"] = "Timeout"
        except Exception:
            parsed_data["HABL System State:"] = "Error"

        commands = [
            ("LCM Current Mode:", r"Current Mode\s*:\s*'([^']+)'", f'{prefix} shell "(echo -e \\"2\\"; sleep 1; echo -e \\"-1\\") | /oemapp/tos_testapp/test_lcmmodechange"'),
            ("ICCID:", r'Get ICCID Info:\s*([A-Za-z0-9]+)', f'{prefix} shell "(echo -e \\"8\\n1\\"; sleep 1; echo -e \\"-1\\") | /oemapp/harman_test_apps/datacall/datacall_client"'),
            ("IOC Version:", r'IOC SW Version:([A-Za-z0-9]+)', f'{prefix} shell "(echo -e \\"7\\"; sleep 1; echo -e \\"-1\\") | /oemapp/harman_test_apps/fota/ota_client"')
        ]

        for key, regex, cmd in commands:
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                match = re.search(regex, res.stdout)
                if match:
                    parsed_data[key] = match.group(1)
            except Exception:
                pass

        try:
            cmd = f'{prefix} shell "(echo -e \\"10\\n14\\n12\\"; sleep 1; echo -e \\"-1\\") | /oemapp/harman_test_apps/dm_client/dm_client"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=9)
            vin_match = re.search(r'VIN\s*=\s*([A-Za-z0-9_]+)', res.stdout)
            if vin_match:
                parsed_data["VIN:"] = vin_match.group(1)
            imei_match = re.search(r'IMEI\s*:\s*([A-Za-z0-9]+)', res.stdout)
            if imei_match:
                parsed_data["IMEI:"] = imei_match.group(1)
            serial_match = re.search(r'device serial number\s*:\s*([A-Za-z0-9_]+)', res.stdout, re.IGNORECASE)
            if serial_match:
                parsed_data["Serial Number:"] = serial_match.group(1)
        except Exception:
            pass

        try:
            check_path = f"{prefix} shell \"ls /oemapp/harman_test_apps/DiagService_client/DiagService_client\""
            path_res = subprocess.run(check_path, shell=True, capture_output=True, text=True)
            target_bin = "DiagService_client/DiagService_client"
            if "No such file" in path_res.stderr or "No such file" in path_res.stdout:
                target_bin = "diagService_client/diagService_client"
            cmd = f'{prefix} shell "(echo -e \\"12\\n14\\n5543\\"; sleep 1; echo -e \\"-1\\") | /oemapp/harman_test_apps/{target_bin}"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=6)
            fuel_val = "Not Present"
            data_match = re.search(r'Data Byte\[0\]\s*:\s*0x([0-9A-Fa-f]+)', res.stdout)
            if data_match:
                hex_val = data_match.group(1)
                if hex_val == "01":
                    fuel_val = "PV"
                elif hex_val == "02":
                    fuel_val = "EV"
            parsed_data["Fuel Type:"] = fuel_val
        except Exception:
            pass

        return parsed_data