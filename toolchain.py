"""arduino-cli wrapper: compile + upload + core/library install, har tarah ke board ke liye."""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

CLI_URLS = {
    "win32": "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip",
    "linux": "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Linux_64bit.tar.gz",
    "darwin": "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_macOS_64bit.tar.gz",
}

# Aam boards: naam -> (FQBN, core, extra core index url)
BOARDS = {
    "Arduino Uno": ("arduino:avr:uno", "arduino:avr", ""),
    "Arduino Nano (new bootloader)": ("arduino:avr:nano", "arduino:avr", ""),
    "Arduino Nano (old bootloader)": ("arduino:avr:nano:cpu=atmega328old", "arduino:avr", ""),
    "Arduino Mega 2560": ("arduino:avr:mega", "arduino:avr", ""),
    "Arduino Leonardo": ("arduino:avr:leonardo", "arduino:avr", ""),
    "ESP32 Dev Module": (
        "esp32:esp32:esp32", "esp32:esp32",
        "https://espressif.github.io/arduino-esp32/package_esp32_index.json"),
    "ESP8266 NodeMCU": (
        "esp8266:esp8266:nodemcuv2", "esp8266:esp8266",
        "https://arduino.esp8266.com/stable/package_esp8266com_index.json"),
    "Raspberry Pi Pico": (
        "rp2040:rp2040:rpipico", "rp2040:rp2040",
        "https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json"),
    "STM32 Nucleo/Blue Pill": (
        "STMicroelectronics:stm32:GenF1", "STMicroelectronics:stm32",
        "https://github.com/stm32duino/BoardManagerFiles/raw/main/package_stmicroelectronics_index.json"),
}


def app_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "HardwareStudio")
    os.makedirs(d, exist_ok=True)
    return d


def find_cli():
    exe = "arduino-cli.exe" if sys.platform == "win32" else "arduino-cli"
    local = os.path.join(app_dir(), "bin", exe)
    if os.path.exists(local):
        return local
    return shutil.which("arduino-cli")


def download_cli(log):
    key = "win32" if sys.platform == "win32" else ("darwin" if sys.platform == "darwin" else "linux")
    url = CLI_URLS[key]
    bindir = os.path.join(app_dir(), "bin")
    os.makedirs(bindir, exist_ok=True)
    arc = os.path.join(bindir, os.path.basename(url))
    log("arduino-cli download ho raha hai...")
    urllib.request.urlretrieve(url, arc)
    if arc.endswith(".zip"):
        with zipfile.ZipFile(arc) as z:
            z.extractall(bindir)
    else:
        import tarfile
        with tarfile.open(arc) as t:
            t.extractall(bindir)
    os.remove(arc)
    log("arduino-cli tayyar.")
    return find_cli()


def run(args, log, cwd=None):
    """Command chalao, output line-by-line log karo, (returncode, full_output) lautao."""
    log("$ " + " ".join(args))
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, cwd=cwd, creationflags=flags)
    out = []
    for line in p.stdout:
        line = line.rstrip()
        out.append(line)
        log(line)
    p.wait()
    return p.returncode, "\n".join(out)


class Toolchain:
    def __init__(self, log):
        self.log = log
        self.cli = find_cli()

    def ensure(self):
        if not self.cli:
            self.cli = download_cli(self.log)
        return self.cli

    def ensure_core(self, board_name):
        fqbn, core, url = BOARDS[board_name]
        cli = self.ensure()
        cmd = [cli, "core", "update-index"]
        if url:
            cmd += ["--additional-urls", url]
        run(cmd, self.log)
        cmd = [cli, "core", "install", core]
        if url:
            cmd += ["--additional-urls", url]
        return run(cmd, self.log)[0] == 0

    def install_lib(self, name):
        return run([self.ensure(), "lib", "install", name], self.log)[0] == 0

    def sketch_dir(self, name, code):
        d = os.path.join(app_dir(), "workspace", name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name + ".ino"), "w", encoding="utf-8") as f:
            f.write(code)
        return d

    def compile(self, fqbn, code, extra_url="", name="sketch"):
        d = self.sketch_dir(name, code)
        cmd = [self.ensure(), "compile", "--fqbn", fqbn, d]
        if extra_url:
            cmd += ["--additional-urls", extra_url]
        return run(cmd, self.log)

    def upload(self, fqbn, port, code, name="sketch"):
        d = self.sketch_dir(name, code)
        return run([self.ensure(), "upload", "-p", port, "--fqbn", fqbn, d], self.log)

    def compile_upload(self, fqbn, port, code, extra_url="", name="sketch"):
        rc, out = self.compile(fqbn, code, extra_url, name)
        if rc != 0:
            return rc, out
        return self.upload(fqbn, port, code, name)

    def list_boards(self):
        rc, out = run([self.ensure(), "board", "list", "--format", "json"], lambda s: None)
        try:
            data = json.loads(out)
            items = data.get("detected_ports", data) if isinstance(data, dict) else data
            return [i["port"]["address"] for i in items if "port" in i]
        except Exception:  # noqa: BLE001
            return []
