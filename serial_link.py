"""pyserial wrapper with background reader thread."""
import threading
import time

import serial
import serial.tools.list_ports


def list_ports():
    return [(p.device, p.description) for p in serial.tools.list_ports.comports()]


class Link:
    def __init__(self, on_line):
        self.on_line = on_line
        self.ser = None
        self._stop = threading.Event()
        self._t = None

    @property
    def is_open(self):
        return self.ser is not None and self.ser.is_open

    def open(self, port, baud=115200):
        self.close()
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self._stop.clear()
        self._t = threading.Thread(target=self._read, daemon=True)
        self._t.start()

    def _read(self):
        buf = b""
        while not self._stop.is_set():
            try:
                chunk = self.ser.read(256)
            except Exception as e:  # noqa: BLE001
                self.on_line("[serial error] %s" % e)
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.on_line(line.decode("utf-8", "replace").rstrip("\r"))

    def write_line(self, s):
        if self.is_open:
            self.ser.write((s + "\n").encode())

    def close(self):
        self._stop.set()
        if self._t:
            self._t.join(timeout=1)
            self._t = None
        if self.ser:
            try:
                self.ser.close()
            except Exception:  # noqa: BLE001
                pass
            self.ser = None
        time.sleep(0.05)
