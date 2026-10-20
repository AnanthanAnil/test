import os
import re
import json
import time
import shutil
import tempfile
import threading
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Sequence
from PyQt6.QtCore import QThread, pyqtSignal

# Device constants
HARMAN_APPS = "/oemapp/harman_test_apps"
VIN_DID = "F190"
SERIAL_DID = "F18C"
FUEL_DID = "5543"
FUEL_CONFIRM_DID = "5404"
DID_PAYLOAD_LIMIT = 24

PROVISIONING_ENDPOINT = "devicedata.upgbeta.tmpv.tatamotors.io"
CERT_REMOTE = "/store/config_store/claimCertificate.pem.crt"
KEY_REMOTE = "/store/config_store/claimPrivate.pem.key"
PROVISION_CLIENT_REMOTE = "/usrdata/provision_client"
RESET_SCRIPT_REMOTE = "/usrdata/reset_script.sh"
PROVISION_CONFIG_REMOTE = "/store/key_store/ProvisionConfig.json"
APP_CONFIG_PV_REMOTE = "/store/config_store/app_config_pv.json"
APP_CONFIG_EV_REMOTE = "/store/config_store/app_config_ev.json"
STORAGE_IDS = ("rw.fs.pv_claimcrt.cert", "rw.fs.pv_claimcrt.rsa_key")

ESYNC_START_CMD = "/oemapp/esync/start.sh"
LCM_MODE_CMD = '(echo -e \\"2\\"; sleep 1; echo -e \\"-1\\") | /oemapp/tos_testapp/test_lcmmodechange'
RESET_CMD = "cd /usrdata && sh ./reset_script.sh"
RESET_TIMEOUT_SECONDS = 60
RESET_WAIT_SECONDS = 300

ALLOWED_LCU_MODES = ("PROVISION", "AUTHORIZED_MODE")
FORBIDDEN_LCU_MODES = ("FACTORY",)
FUEL_BYTE = {"PV": "01", "EV": "02"}
FUEL_FROM_VALUE = {1: "PV", 2: "EV"}

_DATA_BYTE_RE = re.compile(r"Data Byte\[(\d+)\]\s*:\s*0x([0-9A-Fa-f]{1,2})")
_LCM_MODE_RE = re.compile(r"Current Mode\s*:\s*'([^']+)'")

LOG_INFO = "info"
LOG_OK = "ok"
LOG_WARN = "warn"
LOG_ERROR = "error"
IGNITION_TIMEOUT_SECONDS = 60.0

def cflags() -> int:
    import sys
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

def run_adb(device: str, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["adb", "-s", device, *args], capture_output=True, text=True, timeout=timeout, creationflags=cflags())

def run_shell(device: str, cmd: str, timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(f'adb -s {device} shell "{cmd}"', shell=True, capture_output=True, text=True, timeout=timeout, creationflags=cflags())

def diag_call(device: str, payload: str, timeout: float = 20) -> subprocess.CompletedProcess:
    cmd = (
        f'adb -s {device} shell "BIN={HARMAN_APPS}/DiagService_client/DiagService_client; '
        f'[ -f $BIN ] || BIN={HARMAN_APPS}/diagService_client/diagService_client; '
        f'(echo -e \\"{payload}\\"; sleep 1; echo -e \\"-1\\") | $BIN"'
    )
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, creationflags=cflags())

def pad_hex24(text: str) -> str:
    padded = text.ljust(DID_PAYLOAD_LIMIT, "\x00")[:DID_PAYLOAD_LIMIT]
    return "\\n".join(f"{ord(c):02X}" for c in padded)

def read_did_payload(did: str) -> str:
    return f"12\\n14\\n{did}"

def write_ascii_payload(did: str, text: str) -> str:
    return f"13\\n15\\n{did}\\n{DID_PAYLOAD_LIMIT}\\n{pad_hex24(text)}"

def write_fuel_payload(fuel: str) -> str:
    return f"13\\n15\\n{FUEL_DID}\\n1\\n{FUEL_BYTE[fuel]}"

def parse_data_bytes(stdout: str) -> list[int]:
    pairs = [(int(idx), int(val, 16)) for idx, val in _DATA_BYTE_RE.findall(stdout)]
    return [value for _, value in sorted(pairs)]

def parse_ascii_did(stdout: str) -> Optional[str]:
    data = parse_data_bytes(stdout)
    if not data: return None
    return bytes(data).rstrip(b"\x00").decode("ascii", errors="replace").strip()

def parse_fuel_value(stdout: str) -> Optional[int]:
    data = parse_data_bytes(stdout)
    return data[0] if data else None

def fuel_label(value: Optional[int]) -> str:
    if value is None: return "No response"
    return FUEL_FROM_VALUE.get(value, f"0x{value:02X}")

def parse_lcm_mode(stdout: str) -> str:
    match = _LCM_MODE_RE.search(stdout)
    return match.group(1) if match else "Not Found"

def inverse_fuel(fuel: str) -> str:
    return "EV" if fuel == "PV" else "PV"

def verdict_pass(ignition_ok: bool, expected: str, actual: str, lcu: str) -> bool:
    return ignition_ok and actual == expected and lcu in ALLOWED_LCU_MODES and lcu not in FORBIDDEN_LCU_MODES

class ProvisioningError(RuntimeError): pass

class IgnitionRequest:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.ok = False
    def complete(self, ok: bool) -> None:
        self.ok = ok
        self.done.set()

@dataclass
class ProvisioningInputs:
    vin: str
    serial: str
    fuel: str
    cert: str
    key: str
    provision_client: str
    reset_script: str
    app_config_pv: str
    app_config_ev: str
    endpoint: str = PROVISIONING_ENDPOINT

@dataclass
class TestRunConfig:
    mode: str
    iterations: int

class _BaseWorker(QThread):
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int)
    ignition_requested = pyqtSignal(object)
    did_read_signal = pyqtSignal(dict)

    def __init__(self, device: str):
        super().__init__()
        self.device = device
        self._stop_requested = False

    def request_stop(self) -> None: self._stop_requested = True
    def log(self, level: str, message: str) -> None: self.log_signal.emit(level, message)
    def _diag(self, payload: str) -> subprocess.CompletedProcess: return diag_call(self.device, payload)
    def _read_ascii_did(self, did: str) -> Optional[str]: return parse_ascii_did(self._diag(read_did_payload(did)).stdout)
    def _read_fuel_label(self) -> str: return fuel_label(parse_fuel_value(self._diag(read_did_payload(FUEL_DID)).stdout))

    def _read_identity(self, source: str, attempts: int = 5, retry_seconds: float = 10.0) -> str:
        label = "No response"
        for attempt in range(1, attempts + 1):
            payload = read_did_payload(FUEL_CONFIRM_DID)
            data = parse_data_bytes(self._diag(payload).stdout)
            if not data: status, label = "NO RESPONSE", "No response"
            elif all(b == 0xFF for b in data): status, label = "NOT READY (0xFF)", "Not Ready"
            else: status, label = "OK", fuel_label(data[0])
            self.did_read_signal.emit({
                "time": datetime.now().strftime("%H:%M:%S"), "source": source, "attempt": attempt,
                "payload": payload.replace("\\n", " "), "raw": " ".join(f"{b:02X}" for b in data) or "-",
                "label": label, "status": status
            })
            if status == "OK" or attempt == attempts or not self._sleep(retry_seconds): break
        return label

    def _wait_for_boot(self, timeout: float = 300.0) -> bool:
        deadline = time.monotonic() + timeout
        announced = False
        while time.monotonic() < deadline:
            try: state = run_shell(self.device, "systemctl is-system-running", timeout=15).stdout.strip()
            except subprocess.TimeoutExpired: state = ""
            if state in ("running", "degraded"): return True
            if not announced:
                self.log(LOG_WARN, f"Board still booting (state: {state or 'unknown'}); waiting...")
                announced = True
            if not self._sleep(5): return False
        self.log(LOG_ERROR, "Board did not finish booting within 5 minutes")
        return False

    def _read_lcm_mode(self) -> str: return parse_lcm_mode(run_shell(self.device, LCM_MODE_CMD, timeout=15).stdout)
    def _reset_device(self) -> None:
        try: run_shell(self.device, RESET_CMD, timeout=RESET_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired: self.log(LOG_WARN, "reset_script.sh timed out")

    def _sleep(self, seconds: float) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop_requested: return False
            time.sleep(max(0.0, min(1.0, end - time.monotonic())))
        return True

    def _request_ignition(self) -> bool:
        req = IgnitionRequest()
        self.ignition_requested.emit(req)
        deadline = time.monotonic() + IGNITION_TIMEOUT_SECONDS
        while not self._stop_requested and not req.done.is_set() and time.monotonic() < deadline:
            req.done.wait(0.5)
        return req.done.is_set() and req.ok


class ProvisioningWorker(_BaseWorker):
    result_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, device: str, inputs: ProvisioningInputs) -> None:
        super().__init__(device)
        self.inputs = inputs
        self.checks = {}
        self._tmp_dir = ""

    def run(self) -> None:
        self._tmp_dir = tempfile.mkdtemp(prefix="prov_")
        ok, message = False, ""
        try:
            if not self._wait_for_boot(): raise ProvisioningError("Board did not finish booting")
            self._phase1_prechecks()
            self.progress_signal.emit(25)
            self._phase2_staging()
            self.progress_signal.emit(50)
            self._phase3_reset_and_power_cycle()
            self.progress_signal.emit(75)
            self._phase4_verification()
            self.progress_signal.emit(100)
            ok, message = True, "Board provisioning completed and verified."
        except ProvisioningError as e: message = str(e)
        except Exception as e: message = f"Unexpected error: {e}"
        finally: shutil.rmtree(self._tmp_dir, ignore_errors=True)

        self.log(LOG_OK if ok else LOG_ERROR, message)
        self.result_signal.emit({"ok": ok, "message": message, "checks": self.checks})
        self.finished_signal.emit(ok, message)

    def _push(self, local: str, remote: str) -> None:
        if not local or not os.path.isfile(local): raise ProvisioningError(f"Missing local file: {local}")
        if run_adb(self.device, "push", local, remote, timeout=120).returncode != 0: raise ProvisioningError(f"Push to {remote} failed")
        self.log(LOG_INFO, f"Pushed {os.path.basename(local)} -> {remote}")

    def _pull(self, remote: str, local: str) -> None:
        if run_adb(self.device, "pull", remote, local, timeout=60).returncode != 0 or not os.path.isfile(local): raise ProvisioningError(f"Pull of {remote} failed")

    def _phase1_prechecks(self) -> None:
        inp = self.inputs
        for did, label, expected in ((VIN_DID, "VIN", inp.vin), (SERIAL_DID, "Serial", inp.serial)):
            current = self._read_ascii_did(did)
            if current == expected:
                self.log(LOG_OK, f"{label} ({did}) already matches")
                continue
            self._diag(write_ascii_payload(did, expected))
            if self._read_ascii_did(did) != expected: raise ProvisioningError(f"{label} write not verified")
            self.log(LOG_OK, f"{label} written and verified")
        self.checks["vin"], self.checks["serial"] = inp.vin, inp.serial
        self._diag(write_fuel_payload(inp.fuel))
        self.log(LOG_OK, f"Target fuel type {inp.fuel} written")
        self.checks["fuel_written"] = inp.fuel

    def _phase2_staging(self) -> None:
        inp = self.inputs
        self._push(inp.cert, CERT_REMOTE)
        self._push(inp.key, KEY_REMOTE)
        self._push(inp.provision_client, PROVISION_CLIENT_REMOTE)
        self._push(inp.reset_script, RESET_SCRIPT_REMOTE)
        run_shell(self.device, "chmod 777 /store/config_store/* /usrdata/*", timeout=30)
        menu = f"1\\n{CERT_REMOTE}\\n{STORAGE_IDS[0]}\\n1\\n{KEY_REMOTE}\\n{STORAGE_IDS[1]}\\n-1\\n"
        run_shell(self.device, f'cd /usrdata && echo -e \\"{menu}\\" | ./provision_client', timeout=60)
        self.checks["storage_ids"] = list(STORAGE_IDS)
        self._push(inp.app_config_pv, APP_CONFIG_PV_REMOTE)
        self._push(inp.app_config_ev, APP_CONFIG_EV_REMOTE)
        run_shell(self.device, "chmod 777 /store/config_store/app_config*.json", timeout=30)
        
        local = os.path.join(self._tmp_dir, "ProvisionConfig.json")
        self._pull(PROVISION_CONFIG_REMOTE, local)
        with open(local, "r", encoding="utf-8") as f: data = json.load(f)
        data["ProvisioningEndpoint"] = self.inputs.endpoint
        with open(local, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)
        self._push(local, PROVISION_CONFIG_REMOTE)

    def _phase3_reset_and_power_cycle(self) -> None:
        self._reset_device()
        if not self._sleep(RESET_WAIT_SECONDS): raise ProvisioningError("Stopped by user")
        if not self._request_ignition(): raise ProvisioningError("Ignition cycle failed")
        self.checks["ignition"] = "OK"

    def _phase4_verification(self) -> None:
        if not self._wait_for_boot(): raise ProvisioningError("Board did not finish booting")
        mode = self._read_lcm_mode()
        self.checks["lcm_mode"] = mode
        if mode != "PROVISION": raise ProvisioningError(f"LCM mode is '{mode}'")
        actual = self._read_identity("Provisioning")
        self.checks["did_5404"] = actual
        if actual != self.inputs.fuel: raise ProvisioningError(f"DID {FUEL_CONFIRM_DID} is '{actual}'")
        esync = run_shell(self.device, ESYNC_START_CMD, timeout=60)
        status = run_shell(self.device, "systemctl is-active aws", timeout=15).stdout.strip()
        if status != "active":
            run_shell(self.device, "systemctl restart aws", timeout=60)
            self._sleep(5)
            if run_shell(self.device, "systemctl is-active aws", timeout=15).stdout.strip() != "active": raise ProvisioningError("aws service failed")


class ProvisioningTestRunnerWorker(_BaseWorker):
    row_signal = pyqtSignal(dict)
    finished_signal = pyqtSignal(bool, dict)

    def __init__(self, device: str, config: TestRunConfig, fallback_fuel: str) -> None:
        super().__init__(device)
        self.config = config
        self.fallback_fuel = fallback_fuel

    def run(self) -> None:
        started = time.monotonic()
        rows, board_fuel = [], self.fallback_fuel
        try:
            if not self._wait_for_boot(): raise ProvisioningError("Boot failed")
            board_fuel = self._read_identity("Baseline")
            if board_fuel not in ("PV", "EV"): board_fuel = self.fallback_fuel

            name, write_fuel, expected = ("Happy Flow", board_fuel, board_fuel) if self.config.mode == "happy" else ("Negative Flow", inverse_fuel(board_fuel), board_fuel)

            for iteration in range(1, self.config.iterations + 1):
                if self._stop_requested: break
                flow_start = time.monotonic()
                self._diag(write_fuel_payload(write_fuel))
                self._reset_device()
                if not self._sleep(RESET_WAIT_SECONDS): break
                ignition_ok = self._request_ignition()
                if self._stop_requested or not self._wait_for_boot(): break
                
                lcu = self._read_lcm_mode()
                actual = self._read_identity(name)
                passed = verdict_pass(ignition_ok, expected, actual, lcu)
                self._diag(write_fuel_payload(board_fuel))
                
                row = {
                    "iteration": iteration, "flow": name, "written": write_fuel,
                    "expected": expected, "actual": actual, "lcu": lcu,
                    "ignition_ok": ignition_ok, "duration_sec": round(time.monotonic() - flow_start, 1),
                    "verdict": "PASS" if passed else "FAIL",
                }
                rows.append(row)
                self.row_signal.emit(row)
                self.progress_signal.emit(int(iteration * 100 / self.config.iterations))
        except Exception as e: self.log(LOG_ERROR, f"Aborted: {e}")

        completed = not self._stop_requested and len(rows) == self.config.iterations
        self.finished_signal.emit(completed, {"rows": rows, "board_fuel": board_fuel, "total_elapsed_sec": time.monotonic() - started, "completed": completed})


class DidReadWorker(_BaseWorker):
    finished_signal = pyqtSignal(str)
    def run(self) -> None:
        label = self._read_identity("Manual", attempts=5, retry_seconds=5.0)
        self.finished_signal.emit(label)


class DidWriteWorker(_BaseWorker):
    finished_signal = pyqtSignal(bool, str)
    def __init__(self, device: str, kind: str, value: str) -> None:
        super().__init__(device)
        self.kind, self.value = kind, value

    def run(self) -> None:
        ok, message = False, ""
        try:
            if self.kind == "fuel":
                self._diag(write_fuel_payload(self.value))
                ok = self._read_fuel_label() == self.value
            else:
                did = VIN_DID if self.kind == "vin" else SERIAL_DID
                self._diag(write_ascii_payload(did, self.value))
                ok = self._read_ascii_did(did) == self.value
        except subprocess.TimeoutExpired: pass
        self.finished_signal.emit(ok, message)