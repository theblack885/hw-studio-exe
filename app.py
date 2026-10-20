"""Hardware Studio (EXE) - kisi bhi board ko code se control karo. Modern light UI."""
import json
import os
import queue
import re
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

import ai
import serial_link
import toolchain

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("dark-blue")

AQUA = "#0F766E"
VIOLET = "#7C3AED"
ROSE = "#E11D48"
BG = "#F4F7FF"
CARD = "#FFFFFF"
MUTED = "#5B6478"

SETTINGS = os.path.join(toolchain.app_dir(), "settings.json")

DEFAULT_CODE = """void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(500);
  digitalWrite(LED_BUILTIN, LOW);
  delay(500);
}
"""


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_settings(d):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:  # noqa: BLE001
        pass


class Plotter(tk.Canvas):
    """Chhota live line chart - serial se aaye numbers plot karta hai."""

    def __init__(self, master, **kw):
        super().__init__(master, bg=CARD, highlightthickness=0, **kw)
        self.data = []

    def push(self, v):
        self.data.append(v)
        self.data = self.data[-300:]
        self.redraw()

    def clear(self):
        self.data = []
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if len(self.data) < 2 or w < 10:
            return
        lo, hi = min(self.data), max(self.data)
        if hi == lo:
            hi = lo + 1
        pts = []
        for i, v in enumerate(self.data):
            x = 8 + (w - 16) * i / (len(self.data) - 1)
            y = h - 8 - (h - 16) * (v - lo) / (hi - lo)
            pts += [x, y]
        for k in range(1, 4):
            y = h * k / 4
            self.create_line(0, y, w, y, fill="#E5E9F5")
        self.create_line(*pts, fill=AQUA, width=2, smooth=True)
        self.create_text(w - 6, 8, text="%g" % hi, fill=MUTED, anchor="ne")
        self.create_text(w - 6, h - 8, text="%g" % lo, fill=MUTED, anchor="se")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Hardware Studio")
        self.geometry("1180x760")
        self.configure(fg_color=BG)
        self.cfg = load_settings()
        self.q = queue.Queue()
        self.chat_hist = []
        self.last_compile_error = ""
        self.link = serial_link.Link(lambda s: self.q.put(("serial", s)))
        self.tc = toolchain.Toolchain(lambda s: self.q.put(("log", s)))

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sidebar()
        self.pages = {}
        for name, fn in [("Device", self._device), ("Pins", self._pins), ("Code", self._code),
                         ("AI", self._ai), ("Serial", self._serial)]:
            f = ctk.CTkFrame(self, fg_color="transparent")
            f.grid(row=0, column=1, sticky="nsew", padx=18, pady=18)
            fn(f)
            self.pages[name] = f
        self.show("Device")
        self.refresh_ports()
        self.after(60, self._pump)

    # ---------- layout ----------
    def _sidebar(self):
        s = ctk.CTkFrame(self, width=190, fg_color=CARD, corner_radius=0)
        s.grid(row=0, column=0, sticky="ns")
        ctk.CTkLabel(s, text="Hardware\nStudio", font=("Segoe UI", 24, "bold"),
                     text_color=AQUA, justify="left").pack(anchor="w", padx=20, pady=(24, 18))
        self.nav = {}
        for n in ["Device", "Pins", "Code", "AI", "Serial"]:
            b = ctk.CTkButton(s, text=n, anchor="w", height=42, corner_radius=14,
                              fg_color="transparent", hover_color="#E5E9F5",
                              command=lambda n=n: self.show(n))
            b.pack(fill="x", padx=12, pady=3)
            self.nav[n] = b
        self.status = ctk.CTkLabel(s, text="Connect nahi hai", text_color=ROSE, wraplength=160, justify="left")
        self.status.pack(side="bottom", anchor="w", padx=16, pady=16)

    def show(self, name):
        for n, f in self.pages.items():
            f.grid_remove()
            self.nav[n].configure(fg_color="transparent")
        self.pages[name].grid()
        self.nav[name].configure(fg_color="#DDE5FA")

    def card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=22, **kw)

    def head(self, parent, t, sub=""):
        ctk.CTkLabel(parent, text=t, font=("Segoe UI", 28, "bold")).pack(anchor="w")
        if sub:
            ctk.CTkLabel(parent, text=sub, text_color=MUTED).pack(anchor="w", pady=(0, 12))

    # ---------- device ----------
    def _device(self, p):
        self.head(p, "Device", "Board chuno, port chuno, connect karo")
        c = self.card(p)
        c.pack(fill="x", pady=6)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=16)
        self.board_var = ctk.StringVar(value=self.cfg.get("board", "Arduino Uno"))
        ctk.CTkOptionMenu(row, values=list(toolchain.BOARDS), variable=self.board_var, width=260,
                          command=lambda _: self._save()).pack(side="left", padx=(0, 10))
        self.port_var = ctk.StringVar(value="")
        self.port_menu = ctk.CTkOptionMenu(row, values=["-"], variable=self.port_var, width=260)
        self.port_menu.pack(side="left", padx=(0, 10))
        ctk.CTkButton(row, text="Refresh", width=80, command=self.refresh_ports).pack(side="left", padx=4)
        self.baud_var = ctk.StringVar(value="115200")
        ctk.CTkOptionMenu(row, values=["9600", "57600", "115200", "921600"], variable=self.baud_var,
                          width=100).pack(side="left", padx=4)
        self.conn_btn = ctk.CTkButton(row, text="Connect", fg_color=AQUA, text_color="#FFFFFF",
                                      hover_color="#0B5F58", command=self.toggle_conn)
        self.conn_btn.pack(side="left", padx=10)

        c2 = self.card(p)
        c2.pack(fill="x", pady=6)
        ctk.CTkLabel(c2, text="Toolchain (har board ke liye)", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(c2, text="Pehli baar board ka core install hota hai (internet chahiye). Uske baad compile + upload seedha.",
                     text_color=MUTED).pack(anchor="w", padx=16)
        r = ctk.CTkFrame(c2, fg_color="transparent")
        r.pack(fill="x", padx=16, pady=14)
        ctk.CTkButton(r, text="Board core install karo", command=self.install_core).pack(side="left", padx=(0, 8))
        self.lib_entry = ctk.CTkEntry(r, placeholder_text="Library naam (jaise DHT sensor library)", width=300)
        self.lib_entry.pack(side="left", padx=4)
        ctk.CTkButton(r, text="Library install", command=self.install_lib).pack(side="left", padx=4)

        c3 = self.card(p)
        c3.pack(fill="both", expand=True, pady=6)
        ctk.CTkLabel(c3, text="Log", font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        self.log_box = ctk.CTkTextbox(c3, fg_color="#F1F4FC", font=("Consolas", 12))
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(2, 14))

    def refresh_ports(self):
        ports = serial_link.list_ports()
        vals = [p for p, _ in ports] or ["-"]
        self.port_menu.configure(values=vals)
        if self.port_var.get() not in vals:
            self.port_var.set(vals[0])

    def toggle_conn(self):
        if self.link.is_open:
            self.link.close()
            self.conn_btn.configure(text="Connect")
            self.set_status("Disconnected", ROSE)
            return
        port = self.port_var.get()
        if port in ("", "-"):
            self.log("Koi port nahi mila")
            return
        try:
            self.link.open(port, int(self.baud_var.get()))
            self.conn_btn.configure(text="Disconnect")
            self.set_status("Connected: %s" % port, AQUA)
        except Exception as e:  # noqa: BLE001
            self.log("Connect error: %s" % e)

    def set_status(self, t, col):
        self.status.configure(text=t, text_color=col)

    def _save(self):
        self.cfg.update(board=self.board_var.get(), key=self.key_entry.get() if hasattr(self, "key_entry") else self.cfg.get("key", ""),
                        model=self.model_entry.get() if hasattr(self, "model_entry") else self.cfg.get("model", "claude-sonnet-5-5"))
        save_settings(self.cfg)

    def log(self, s):
        self.q.put(("log", s))

    def bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def install_core(self):
        b = self.board_var.get()
        self.bg(lambda: (self.log("Core install: %s" % b),
                         self.log("OK" if self.tc.ensure_core(b) else "Fail")))

    def install_lib(self):
        n = self.lib_entry.get().strip()
        if n:
            self.bg(lambda: self.log("Library OK" if self.tc.install_lib(n) else "Library fail"))

    # ---------- pins ----------
    def _pins(self, p):
        self.head(p, "Pins", "Bridge firmware wale board ko seedha control (firmware/hw_bridge)")
        c = self.card(p)
        c.pack(fill="x", pady=6)
        r = ctk.CTkFrame(c, fg_color="transparent")
        r.pack(fill="x", padx=16, pady=16)
        self.pin_entry = ctk.CTkEntry(r, width=90, placeholder_text="Pin")
        self.pin_entry.insert(0, "13")
        self.pin_entry.pack(side="left", padx=(0, 8))
        for t, cmd in [("HIGH", "DW {p} 1"), ("LOW", "DW {p} 0"), ("Read", "DR {p}"), ("Analog", "AR {p}")]:
            ctk.CTkButton(r, text=t, width=80, command=lambda c=cmd: self.pin_cmd(c)).pack(side="left", padx=4)
        ctk.CTkButton(r, text="Bridge firmware daalo", fg_color=VIOLET, hover_color="#6D28D9",
                      command=self.flash_bridge).pack(side="right")

        c2 = self.card(p)
        c2.pack(fill="x", pady=6)
        self.pwm = ctk.CTkSlider(c2, from_=0, to=255, number_of_steps=255)
        self.pwm.set(128)
        ctk.CTkLabel(c2, text="PWM (0-255)").pack(anchor="w", padx=16, pady=(14, 0))
        self.pwm.pack(fill="x", padx=16, pady=6)
        self.pwm.bind("<ButtonRelease-1>", lambda e: self.pin_cmd("PWM {p} %d" % int(self.pwm.get())))
        self.srv = ctk.CTkSlider(c2, from_=0, to=180, number_of_steps=180)
        self.srv.set(90)
        ctk.CTkLabel(c2, text="Servo (0-180)").pack(anchor="w", padx=16, pady=(8, 0))
        self.srv.pack(fill="x", padx=16, pady=(6, 16))
        self.srv.bind("<ButtonRelease-1>", lambda e: self.pin_cmd("SERVO {p} %d" % int(self.srv.get())))

        c3 = self.card(p)
        c3.pack(fill="x", pady=6)
        r3 = ctk.CTkFrame(c3, fg_color="transparent")
        r3.pack(fill="x", padx=16, pady=14)
        ctk.CTkLabel(r3, text="Live analog stream").pack(side="left")
        ctk.CTkButton(r3, text="Start", width=70, command=lambda: self.pin_cmd("STREAM {p} 100")).pack(side="left", padx=8)
        ctk.CTkButton(r3, text="Stop", width=70, fg_color="#64748B", command=lambda: self.link.write_line("STREAM OFF")).pack(side="left")
        ctk.CTkLabel(r3, text="Graph Serial tab me", text_color=MUTED).pack(side="left", padx=12)

    def pin_cmd(self, tpl):
        if not self.link.is_open:
            self.log("Pehle Device tab me connect karo")
            return
        cmd = tpl.format(p=self.pin_entry.get().strip())
        self.link.write_line(cmd)
        self.log("> " + cmd)

    def flash_bridge(self):
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, "firmware", "hw_bridge", "hw_bridge.ino")
        if not os.path.exists(path):
            path = os.path.join(getattr(__import__("sys"), "_MEIPASS", here), "firmware", "hw_bridge", "hw_bridge.ino")
        with open(path, encoding="utf-8") as f:
            code = f.read()
        self.code_box.delete("1.0", "end")
        self.code_box.insert("1.0", code)
        self.show("Code")
        self.log("Bridge code editor me aa gaya. 'Compile + Upload' dabao.")
        self.bg(lambda: self.tc.install_lib("Servo"))

    # ---------- code ----------
    def _code(self, p):
        self.head(p, "Code", "Likho ya AI se paste karo, phir seedha board me daalo")
        self.code_box = ctk.CTkTextbox(p, fg_color=CARD, corner_radius=22, font=("Consolas", 13))
        self.code_box.pack(fill="both", expand=True, pady=6)
        self.code_box.insert("1.0", DEFAULT_CODE)
        r = ctk.CTkFrame(p, fg_color="transparent")
        r.pack(fill="x", pady=6)
        ctk.CTkButton(r, text="Compile", command=lambda: self.build(False)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(r, text="Compile + Upload", fg_color=AQUA, text_color="#FFFFFF", hover_color="#0B5F58",
                      command=lambda: self.build(True)).pack(side="left", padx=4)
        ctk.CTkButton(r, text="Error AI se fix karwao", fg_color=VIOLET, hover_color="#6D28D9",
                      command=self.ai_fix).pack(side="left", padx=4)
        ctk.CTkButton(r, text="Open .ino", fg_color="#64748B", command=self.open_file).pack(side="right", padx=4)
        ctk.CTkButton(r, text="Save .ino", fg_color="#64748B", command=self.save_file).pack(side="right", padx=4)

    def open_file(self):
        f = filedialog.askopenfilename(filetypes=[("Sketch", "*.ino *.cpp *.c *.txt"), ("All", "*.*")])
        if f:
            with open(f, encoding="utf-8", errors="replace") as fh:
                self.code_box.delete("1.0", "end")
                self.code_box.insert("1.0", fh.read())

    def save_file(self):
        f = filedialog.asksaveasfilename(defaultextension=".ino")
        if f:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(self.code_box.get("1.0", "end"))

    def build(self, do_upload):
        code = self.code_box.get("1.0", "end")
        board = self.board_var.get()
        fqbn, core, url = toolchain.BOARDS[board]
        port = self.port_var.get()
        if do_upload and (port in ("", "-")):
            self.log("Upload ke liye port chuno")
            self.show("Device")
            return
        was_open = self.link.is_open
        if was_open:
            self.link.close()
            self.conn_btn.configure(text="Connect")
        self.show("Device")

        def job():
            self.log("=== %s | %s ===" % (board, "compile+upload" if do_upload else "compile"))
            if do_upload:
                rc, out = self.tc.compile_upload(fqbn, port, code, url)
            else:
                rc, out = self.tc.compile(fqbn, code, url)
            if rc == 0:
                self.last_compile_error = ""
                self.log("SUCCESS")
            else:
                self.last_compile_error = out[-3500:]
                self.log("FAIL. Core/library missing ho to Device tab se install karo, ya 'Error AI se fix karwao' dabao.")
        self.bg(job)

    def ai_fix(self):
        if not self.last_compile_error:
            self.log("Koi compile error saved nahi hai")
            return
        code = self.code_box.get("1.0", "end")
        self.show("AI")
        self.send_ai("Ye code compile nahi hua. Error padho aur poora sudhaara hua code do.\n\nCODE:\n```cpp\n%s\n```\n\nERROR:\n%s"
                     % (code, self.last_compile_error))

    # ---------- AI ----------
    def _ai(self, p):
        self.head(p, "AI Assistant", "Kisi bhi hardware ka code mango - ye batayega paste kahan karna hai")
        self.chat_box = ctk.CTkTextbox(p, fg_color=CARD, corner_radius=22, wrap="word", font=("Segoe UI", 13))
        self.chat_box.pack(fill="both", expand=True, pady=6)
        self.chat_box.insert("end", "Try karo:\n- Arduino Uno me 3 LED chaser banao\n- ESP32 se WiFi par relay on/off\n- DHT11 temperature OLED par dikhao\n\n")
        self.chat_box.configure(state="disabled")
        r = ctk.CTkFrame(p, fg_color="transparent")
        r.pack(fill="x", pady=4)
        self.ai_in = ctk.CTkEntry(r, placeholder_text="Kya banana hai?", height=40)
        self.ai_in.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ai_in.bind("<Return>", lambda e: self.send_ai(self.ai_in.get()))
        ctk.CTkButton(r, text="Send", width=80, height=40, command=lambda: self.send_ai(self.ai_in.get())).pack(side="left")
        ctk.CTkButton(r, text="Code editor me daalo", width=160, height=40, fg_color=VIOLET, hover_color="#6D28D9",
                      command=self.ai_to_editor).pack(side="left", padx=8)
        s = ctk.CTkFrame(p, fg_color="transparent")
        s.pack(fill="x", pady=2)
        self.key_entry = ctk.CTkEntry(s, placeholder_text="API key", show="*", width=360)
        self.key_entry.insert(0, self.cfg.get("key", ""))
        self.key_entry.pack(side="left", padx=(0, 8))
        self.model_entry = ctk.CTkEntry(s, width=200)
        self.model_entry.insert(0, self.cfg.get("model", "claude-sonnet-5-5"))
        self.model_entry.pack(side="left", padx=4)
        ctk.CTkButton(s, text="Save", width=70, fg_color="#64748B", command=self._save).pack(side="left", padx=4)

    def chat_add(self, who, text):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", "%s:\n%s\n\n" % (who, text))
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def send_ai(self, text):
        text = text.strip()
        if not text:
            return
        self._save()
        self.ai_in.delete(0, "end")
        self.chat_add("Aap", text if len(text) < 600 else text[:600] + " ...")
        self.chat_hist.append(("user", text))
        ctx = "Board: %s\nPort: %s\nEditor code:\n%s" % (
            self.board_var.get(), self.port_var.get(), self.code_box.get("1.0", "end")[:6000])
        hist = list(self.chat_hist)

        def job():
            r = ai.ask(self.cfg.get("key", ""), self.cfg.get("model", "claude-sonnet-5-5"), hist, ctx)
            self.q.put(("ai", r))
        self.chat_add("AI", "soch raha hu...")
        self.bg(job)

    def ai_to_editor(self):
        last = next((t for r, t in reversed(self.chat_hist) if r == "assistant"), "")
        code = ai.extract_code(last)
        if not code:
            self.log("AI ke jawab me code block nahi mila")
            return
        self.code_box.delete("1.0", "end")
        self.code_box.insert("1.0", code)
        fq = ai.extract_fqbn(last)
        if fq:
            for name, (f, _, _) in toolchain.BOARDS.items():
                if f == fq:
                    self.board_var.set(name)
        self.show("Code")

    # ---------- serial ----------
    def _serial(self, p):
        self.head(p, "Serial Monitor + Plotter")
        self.plot = Plotter(p, height=180)
        self.plot.pack(fill="x", pady=6)
        self.ser_box = ctk.CTkTextbox(p, fg_color=CARD, corner_radius=22, font=("Consolas", 12))
        self.ser_box.pack(fill="both", expand=True, pady=6)
        r = ctk.CTkFrame(p, fg_color="transparent")
        r.pack(fill="x")
        self.ser_in = ctk.CTkEntry(r, placeholder_text="Command bhejo", height=38)
        self.ser_in.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.ser_in.bind("<Return>", lambda e: self.ser_send())
        ctk.CTkButton(r, text="Send", width=80, command=self.ser_send).pack(side="left")
        ctk.CTkButton(r, text="Clear", width=70, fg_color="#64748B",
                      command=lambda: (self.ser_box.delete("1.0", "end"), self.plot.clear())).pack(side="left", padx=6)

    def ser_send(self):
        t = self.ser_in.get()
        if t and self.link.is_open:
            self.link.write_line(t)
            self.ser_box.insert("end", "> %s\n" % t)
            self.ser_in.delete(0, "end")

    # ---------- event pump ----------
    def _pump(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log_box.insert("end", val + "\n")
                    self.log_box.see("end")
                elif kind == "serial":
                    self.ser_box.insert("end", val + "\n")
                    self.ser_box.see("end")
                    m = re.search(r"(-?\d+(?:\.\d+)?)\s*$", val)
                    if m:
                        self.plot.push(float(m.group(1)))
                elif kind == "ai":
                    self.chat_hist.append(("assistant", val))
                    self.chat_add("AI", val)
        except queue.Empty:
            pass
        self.after(60, self._pump)


if __name__ == "__main__":
    App().mainloop()
