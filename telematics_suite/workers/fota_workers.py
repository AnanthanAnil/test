import os
import sys
import json
import shutil
import zipfile
import subprocess
import re
import html
import time
from PyQt6.QtCore import QThread, pyqtSignal

class FOTAWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    state_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, device, local_zip_path, skip_push=False):
        super().__init__()
        self.device = device
        self.local_zip_path = local_zip_path
        self.skip_push = skip_push
        self.running = True
        self.process = None

    def run(self):
        prefix = f"adb -s {self.device}"
        target_dir = "/data/emmc/misc/SW_Update_Package"
        filename = os.path.basename(self.local_zip_path)
        remote_path = f"{target_dir}/{filename}"

        try:
            if not self.skip_push:
                self.log_signal.emit(f"[FOTA] Creating directory on target: {target_dir}")
                subprocess.run(f'{prefix} shell "mkdir -p {target_dir}"', shell=True, check=True)
                self.log_signal.emit(f"[FOTA] Pushing {filename} to target... This may take time.")
                push_res = subprocess.run(
                    f'{prefix} push "{self.local_zip_path}" "{remote_path}"',
                    shell=True, capture_output=True, text=True
                )
                if push_res.returncode != 0:
                    self.finished_signal.emit(False, f"Push Failed: {push_res.stderr.strip()}")
                    return
                self.log_signal.emit(f"[FOTA] Delta package pushed successfully.")

            self.log_signal.emit(f"[FOTA] Launching ota_client session...")
            ota_cmd = f'{prefix} shell "echo -e \\"1\\n{remote_path}\\n2\\n\\" | /oemapp/harman_test_apps/fota/ota_client"'
            self.process = subprocess.Popen(
                ota_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )

            while self.running:
                line = self.process.stdout.readline()
                if not line:
                    break
                raw_line = line.strip()
                self.log_signal.emit(raw_line)

                pct_match = re.search(r'Percentage:\s*([0-9]+)', raw_line, re.IGNORECASE)
                if pct_match:
                    self.progress_signal.emit(int(pct_match.group(1)))

                info_match = re.search(r'Information:\s*([A-Za-z0-9_]+)', raw_line, re.IGNORECASE)
                exit_match = re.search(r'Exit State:\s*([A-Za-z0-9_]+)', raw_line, re.IGNORECASE)
                if info_match or exit_match:
                    self.state_signal.emit(info_match.group(1) if info_match else "",
                                           exit_match.group(1) if exit_match else "")

                if "UPDATE_COMPLETE" in raw_line or "UPDATE_COMPLETE_SWITCH_PENDING" in raw_line:
                    self.progress_signal.emit(100)
                    self.finished_signal.emit(True, "FOTA Update successfully installed on inactive partition.")
                    return

            self.process.wait()
            self.finished_signal.emit(True, "FOTA execution completed.")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

    def stop(self):
        self.running = False
        if self.process:
            try:
                if self.process.stdout:
                    self.process.stdout.close()
                if sys.platform == 'win32':
                    subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.process.pid)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    self.process.terminate()
            except Exception:
                pass


class AutomationWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool)

    def __init__(self, device, script_lines):
        super().__init__()
        self.device = device
        self.script_lines = [line for line in script_lines if line.strip() and not line.strip().startswith("#")]
        self.running = True

    def run(self):
        total = len(self.script_lines)
        if total == 0:
            self.finished_signal.emit(True)
            return

        prefix = f"adb -s {self.device}" if self.device else "adb"

        for idx, cmd in enumerate(self.script_lines):
            if not self.running:
                self.log_signal.emit("<span style='color:#FFEA00;'>[Automation] Aborted by user.</span>")
                break
            clean_cmd = cmd.strip()
            self.log_signal.emit(
                f"<br><span style='color:#B2BEB5; font-weight:bold;'>[STEP {idx+1}/{total}] Executing:</span> "
                f"<span style='color:#FFFFFF;'>{clean_cmd}</span>"
            )

            if clean_cmd.upper().startswith("SLEEP "):
                try:
                    time.sleep(int(clean_cmd.split()[1]))
                except Exception:
                    self.log_signal.emit("<span style='color:#ff4757;'>[Error] Invalid SLEEP syntax.</span>")
            else:
                actual_cmd = clean_cmd if clean_cmd.startswith("adb") else f"{prefix} shell {clean_cmd}"
                try:
                    res = subprocess.run(
                        actual_cmd, shell=True, capture_output=True, text=True, timeout=60,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                    )
                    if res.stdout:
                        self.log_signal.emit(f"<span style='color:#9CA3AF;'>{html.escape(res.stdout.strip())}</span>")
                    if res.stderr:
                        self.log_signal.emit(f"<span style='color:#ff4757;'>{html.escape(res.stderr.strip())}</span>")
                except Exception as e:
                    self.log_signal.emit(f"<span style='color:#ff4757;'>[Exception] {str(e)}</span>")

            self.progress_signal.emit(int(((idx + 1) / total) * 100))

        self.finished_signal.emit(True)

    def stop(self):
        self.running = False


class DeltaBuilderWorker(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, device, package_type, output_zip_path, nad_zip_path=None,
                 ioc_a_path=None, ioc_b_path=None, nad_target_ver="", ioc_target_ver="",
                 downgrade_allowed=True, compat_matrix_dict=None, push_to_device=True):
        super().__init__()
        self.device = device
        self.package_type = package_type
        self.output_zip_path = output_zip_path
        self.nad_zip_path = nad_zip_path
        self.ioc_a_path = ioc_a_path
        self.ioc_b_path = ioc_b_path
        self.nad_target_ver = nad_target_ver
        self.ioc_target_ver = ioc_target_ver
        self.downgrade_allowed = downgrade_allowed
        self.compat_matrix_dict = compat_matrix_dict or {}
        self.push_to_device = push_to_device

    def run(self):
        try:
            staging_dir = os.path.join(os.path.dirname(self.output_zip_path), "DeltaPackage_Staging")
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir)
            delta_folder = os.path.join(staging_dir, "DeltaPackage")
            os.makedirs(delta_folder, exist_ok=True)
            self.log_signal.emit(f"[Builder] Staging directory initialized: {delta_folder}")

            if self.package_type in ["NAD_ONLY", "NAD_IOC"]:
                if not self.nad_zip_path or not os.path.exists(self.nad_zip_path):
                    self.finished_signal.emit(False, "NAD zip file missing.")
                    return
                shutil.copyfile(self.nad_zip_path, os.path.join(delta_folder, "update.zip"))
                self.log_signal.emit("[Builder] Integrated update.zip")

            if self.package_type in ["IOC_ONLY", "NAD_IOC"]:
                ioc_dir = os.path.join(delta_folder, "IOC_SWDL")
                os.makedirs(ioc_dir, exist_ok=True)
                if not self.ioc_a_path or not self.ioc_b_path:
                    self.finished_signal.emit(False, "IOC binaries missing.")
                    return
                shutil.copyfile(self.ioc_a_path, os.path.join(ioc_dir, "TATA_5G_TCU_AS_IOC_AppA.bin"))
                shutil.copyfile(self.ioc_b_path, os.path.join(ioc_dir, "TATA_5G_TCU_AS_IOC_AppB.bin"))
                self.log_signal.emit("[Builder] Integrated IOC binaries")

            matrix_payload = {
                "update_package": {
                    "NADTargetVersion": self.nad_target_ver if self.package_type != "IOC_ONLY" else "",
                    "IOCTargetVersion": self.ioc_target_ver if self.package_type != "NAD_ONLY" else "",
                    "downgrade_allowed": self.downgrade_allowed
                },
                "compatibility_matrix": self.compat_matrix_dict
            }
            with open(os.path.join(delta_folder, "compatibility_matrix.json"), "w", encoding="utf-8") as f:
                json.dump(matrix_payload, f, indent=4)

            with zipfile.ZipFile(self.output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(delta_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        zipf.write(file_path, os.path.relpath(file_path, delta_folder))
            shutil.rmtree(staging_dir)

            if self.push_to_device and self.device:
                self.log_signal.emit(f"[Builder] Pushing to target...")
                subprocess.run(f'adb -s {self.device} shell "mkdir -p /data/emmc/misc/SW_Update_Package"', shell=True, check=True)
                push_res = subprocess.run(
                    f'adb -s {self.device} push "{self.output_zip_path}" "/data/emmc/misc/SW_Update_Package/{os.path.basename(self.output_zip_path)}"',
                    shell=True, capture_output=True, text=True
                )
                if push_res.returncode != 0:
                    self.finished_signal.emit(False, f"Push Failed: {push_res.stderr.strip()}")
                    return
            self.finished_signal.emit(True, f"Delta package built and pushed.")
        except Exception as e:
            self.finished_signal.emit(False, str(e))