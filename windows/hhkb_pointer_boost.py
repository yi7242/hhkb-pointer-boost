#!/usr/bin/env python3
"""Windows tray app that changes pointer speed while a chosen key is held."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import signal
import sys
import threading
import winreg
from ctypes import wintypes
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "HHKB Pointer Boost"
RUN_VALUE_NAME = "HHKBPointerBoost"
TRAY_CLASS_NAME = "HHKBPointerBoostTrayWindow"
SETTINGS_DIR = Path(os.environ.get("LOCALAPPDATA", Path(__file__).parent)) / "HHKBPointerBoost"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
ICON_FILE = Path(__file__).with_name("hhkb_pointer_boost.ico")

SPI_GETMOUSESPEED = 0x0070
SPI_SETMOUSESPEED = 0x0071
SPIF_SENDCHANGE = 0x0002
ERROR_ALREADY_EXISTS = 183

KEY_CHOICES: dict[str, int] = {
    "左Alt": 0xA4,
    "右Alt": 0xA5,
    "左Shift": 0xA0,
    "右Shift": 0xA1,
    "左Ctrl": 0xA2,
    "右Ctrl": 0xA3,
    "CapsLock": 0x14,
    "ScrollLock": 0x91,
    "F13（専用キー向け）": 0x7C,
    "F14（専用キー向け）": 0x7D,
    "マウス戻るボタン": 0x05,
    "マウス進むボタン": 0x06,
}

DEFAULTS = {
    "enabled": True,
    "trigger": "左Alt",
    "normal_speed": 8,
    "boost_speed": 12,
    "poll_ms": 16,
}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
user32.GetAsyncKeyState.restype = wintypes.SHORT
user32.SystemParametersInfoW.argtypes = (
    wintypes.UINT,
    wintypes.UINT,
    wintypes.LPVOID,
    wintypes.UINT,
)
user32.SystemParametersInfoW.restype = wintypes.BOOL

kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL


def get_pointer_speed() -> int:
    speed = ctypes.c_int()
    if not user32.SystemParametersInfoW(
        SPI_GETMOUSESPEED, 0, ctypes.byref(speed), 0
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return speed.value


def set_pointer_speed(speed: int) -> None:
    speed = max(1, min(20, int(speed)))
    if not user32.SystemParametersInfoW(
        SPI_SETMOUSESPEED, 0, ctypes.c_void_p(speed), SPIF_SENDCHANGE
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def load_settings() -> dict:
    settings = DEFAULTS.copy()
    settings["normal_speed"] = get_pointer_speed()
    try:
        loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            settings.update({key: loaded[key] for key in DEFAULTS if key in loaded})
    except (OSError, ValueError, TypeError):
        pass

    if settings["trigger"] not in KEY_CHOICES:
        settings["trigger"] = DEFAULTS["trigger"]
    settings["normal_speed"] = max(1, min(20, int(settings["normal_speed"])))
    settings["boost_speed"] = max(1, min(20, int(settings["boost_speed"])))
    settings["poll_ms"] = max(16, min(100, int(settings["poll_ms"])))
    settings["enabled"] = bool(settings["enabled"])
    return settings


def save_settings(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    saved = {key: settings[key] for key in DEFAULTS}
    SETTINGS_FILE.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def pythonw_path() -> Path:
    candidates = [
        Path(sys._base_executable).with_name("pythonw.exe"),
        Path(sys.executable).with_name("pythonw.exe"),
    ]
    return next((path for path in candidates if path.exists()), Path(sys.executable))


def startup_command() -> str:
    return f'"{pythonw_path()}" "{Path(__file__).resolve()}" --startup'


def is_startup_enabled() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return str(Path(__file__).resolve()).lower() in value.lower()
    except OSError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass


# Native tray icon ---------------------------------------------------------
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
NIM_ADD = 0x00000000
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
IDI_APPLICATION = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
TRAY_ICON_SIZE = 32
CMD_TOGGLE = 1001
CMD_SETTINGS = 1002
CMD_EXIT = 1003
LRESULT = ctypes.c_ssize_t


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


user32.RegisterClassW.argtypes = (ctypes.POINTER(WNDCLASSW),)
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = (
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
)
user32.CreateWindowExW.restype = wintypes.HWND
user32.LoadIconW.argtypes = (wintypes.HINSTANCE, ctypes.c_void_p)
user32.LoadIconW.restype = wintypes.HICON
user32.LoadImageW.argtypes = (
    wintypes.HINSTANCE,
    wintypes.LPCWSTR,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
)
user32.LoadImageW.restype = wintypes.HANDLE
user32.DestroyIcon.argtypes = (wintypes.HICON,)
user32.DestroyIcon.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
)
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = LRESULT
user32.DefWindowProcW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.DefWindowProcW.restype = LRESULT
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = (
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_size_t,
    wintypes.LPCWSTR,
)
user32.AppendMenuW.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.TrackPopupMenu.argtypes = (
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.LPVOID,
)
user32.TrackPopupMenu.restype = wintypes.UINT
user32.DestroyMenu.argtypes = (wintypes.HMENU,)
user32.DestroyMenu.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = (wintypes.HWND,)
user32.DestroyWindow.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = (ctypes.c_int,)
user32.PostMessageW.argtypes = (
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)
user32.PostMessageW.restype = wintypes.BOOL
user32.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
user32.FindWindowW.restype = wintypes.HWND
user32.RegisterWindowMessageW.argtypes = (wintypes.LPCWSTR,)
user32.RegisterWindowMessageW.restype = wintypes.UINT
shell32.Shell_NotifyIconW.argtypes = (
    wintypes.DWORD,
    ctypes.POINTER(NOTIFYICONDATAW),
)
shell32.Shell_NotifyIconW.restype = wintypes.BOOL


class TrayIcon:
    def __init__(self, commands: queue.Queue, enabled_getter) -> None:
        self.commands = commands
        self.enabled_getter = enabled_getter
        self.hwnd = None
        self.nid = None
        self.icon = None
        self.added = False
        self.ready = threading.Event()
        self._wndproc_ref = WNDPROC(self._wndproc)
        self.taskbar_created_message = user32.RegisterWindowMessageW("TaskbarCreated")

    def start(self) -> None:
        threading.Thread(target=self._run, name="tray-icon", daemon=True).start()
        self.ready.wait(timeout=3)

    def _run(self) -> None:
        hinstance = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinstance
        wc.lpszClassName = TRAY_CLASS_NAME
        user32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(
            0, TRAY_CLASS_NAME, APP_NAME, 0, 0, 0, 0, 0, None, None, hinstance, None
        )
        if not self.hwnd:
            self.ready.set()
            return

        self.icon = self._create_hhkb_icon()
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAY
        self.nid.hIcon = self.icon
        self.nid.szTip = "HHKB Boost — ダブルクリックで設定"
        self.added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid)))
        self.ready.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    @staticmethod
    def _create_hhkb_icon():
        """Load the color H+ icon generated by make_hhkb_icon.py."""
        # A monochrome icon that only inverts the background is drawn blank on
        # the Windows 11 taskbar, so use a 32-bit color icon with alpha.
        icon = user32.LoadImageW(
            None,
            str(ICON_FILE),
            IMAGE_ICON,
            TRAY_ICON_SIZE,
            TRAY_ICON_SIZE,
            LR_LOADFROMFILE,
        )
        return icon or user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    def _show_menu(self) -> None:
        menu = user32.CreatePopupMenu()
        toggle_flags = MF_STRING | (MF_CHECKED if self.enabled_getter() else 0)
        user32.AppendMenuW(menu, toggle_flags, CMD_TOGGLE, "有効")
        user32.AppendMenuW(menu, MF_STRING, CMD_SETTINGS, "設定を開く")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_EXIT, "終了")
        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        command = user32.TrackPopupMenu(
            menu,
            TPM_RETURNCMD | TPM_RIGHTBUTTON,
            point.x,
            point.y,
            0,
            self.hwnd,
            None,
        )
        user32.DestroyMenu(menu)
        if command == CMD_TOGGLE:
            self.commands.put("toggle")
        elif command == CMD_SETTINGS:
            self.commands.put("show")
        elif command == CMD_EXIT:
            self.commands.put("exit")

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == self.taskbar_created_message and self.nid is not None:
            self.added = bool(
                shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid))
            )
            return 0
        if msg == WM_TRAY:
            if lparam == WM_LBUTTONDBLCLK:
                self.commands.put("show")
                return 0
            if lparam == WM_RBUTTONUP:
                self._show_menu()
                return 0
        if msg == WM_CLOSE:
            if self.nid is not None:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            if self.icon:
                user32.DestroyIcon(self.icon)
                self.icon = None
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def stop(self) -> None:
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)


class PointerBoostApp:
    def __init__(self, show_on_start: bool) -> None:
        self.settings = load_settings()
        self.commands: queue.Queue[str] = queue.Queue()
        self.boosted = False
        self.exiting = False

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        if ICON_FILE.exists():
            self.root.iconbitmap(default=str(ICON_FILE))
        self.root.geometry("470x540")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.enabled_var = tk.BooleanVar(value=self.settings["enabled"])
        self.trigger_var = tk.StringVar(value=self.settings["trigger"])
        self.normal_var = tk.IntVar(value=self.settings["normal_speed"])
        self.boost_var = tk.IntVar(value=self.settings["boost_speed"])
        self.poll_var = tk.StringVar(value=str(self.settings["poll_ms"]))
        self.startup_var = tk.BooleanVar(value=is_startup_enabled())
        self.current_label = tk.StringVar()
        self.status_label = tk.StringVar()

        self._build_ui()
        self.tray = TrayIcon(self.commands, lambda: self.settings["enabled"])
        self.tray.start()

        # A restricted launch context can block notification-area registration.
        # Never leave the app invisible in that case.
        if not self.tray.added:
            show_on_start = True

        if show_on_start:
            self.show_window()
        else:
            self.root.withdraw()

        self.root.after(100, self._process_commands)
        self.root.after(self._poll_interval(), self._poll_trigger)
        self.root.after(500, self._refresh_status)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer, text="HHKB Pointer Boost", font=("Segoe UI", 16, "bold")
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="指定キーを押している間だけ、Windowsのポインター感度を切り替えます。",
        ).pack(anchor="w", pady=(3, 14))

        state_box = ttk.LabelFrame(outer, text="現在の状態", padding=12)
        state_box.pack(fill="x", pady=(0, 12))
        ttk.Label(state_box, textvariable=self.current_label).pack(anchor="w")
        ttk.Label(state_box, textvariable=self.status_label).pack(anchor="w", pady=(4, 0))

        settings_box = ttk.LabelFrame(outer, text="設定", padding=12)
        settings_box.pack(fill="x")

        ttk.Checkbutton(
            settings_box, text="ポインター加速を有効にする", variable=self.enabled_var
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(settings_box, text="押している間のキー").grid(
            row=1, column=0, sticky="w", pady=5
        )
        trigger_combo = ttk.Combobox(
            settings_box,
            textvariable=self.trigger_var,
            values=list(KEY_CHOICES),
            state="readonly",
            width=24,
        )
        trigger_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)

        ttk.Label(settings_box, text="通常時の感度").grid(
            row=2, column=0, sticky="w", pady=5
        )
        tk.Scale(
            settings_box,
            from_=1,
            to=20,
            orient="horizontal",
            variable=self.normal_var,
            showvalue=True,
            resolution=1,
            length=230,
        ).grid(row=2, column=1, columnspan=2, sticky="ew")

        ttk.Label(settings_box, text="キー押下中の感度").grid(
            row=3, column=0, sticky="w", pady=5
        )
        tk.Scale(
            settings_box,
            from_=1,
            to=20,
            orient="horizontal",
            variable=self.boost_var,
            showvalue=True,
            resolution=1,
            length=230,
        ).grid(row=3, column=1, columnspan=2, sticky="ew")

        ttk.Label(settings_box, text="反応間隔").grid(
            row=4, column=0, sticky="w", pady=5
        )
        ttk.Combobox(
            settings_box,
            textvariable=self.poll_var,
            values=("16", "30", "50", "100"),
            state="readonly",
            width=8,
        ).grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(settings_box, text="ms（小さいほど素早い）").grid(
            row=4, column=2, sticky="w", padx=(6, 0)
        )

        ttk.Checkbutton(
            settings_box,
            text="Windowsログイン時に自動起動する",
            variable=self.startup_var,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(10, 0))
        settings_box.columnconfigure(1, weight=1)

        ttk.Label(
            outer,
            text=(
                "ヒント: Ctrl・Shift・Altにはアプリ側の副作用があります。"
                "専用キーにできるならF13が最も安全です。"
            ),
            foreground="#555555",
            wraplength=425,
        ).pack(anchor="w", pady=(12, 12))

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="適用", command=self.apply_settings).pack(
            side="right"
        )
        ttk.Button(buttons, text="閉じる", command=self.hide_window).pack(
            side="right", padx=(0, 8)
        )
        ttk.Button(buttons, text="終了", command=self.exit_app).pack(side="left")

        ttk.Label(
            outer,
            text="ウィンドウを閉じても、システムトレイで動作を続けます。",
            foreground="#666666",
        ).pack(anchor="w", pady=(14, 0))

    def apply_settings(self) -> None:
        try:
            self.settings.update(
                enabled=bool(self.enabled_var.get()),
                trigger=self.trigger_var.get(),
                normal_speed=int(self.normal_var.get()),
                boost_speed=int(self.boost_var.get()),
                poll_ms=max(16, min(100, int(self.poll_var.get()))),
            )
            save_settings(self.settings)
            set_startup_enabled(bool(self.startup_var.get()))
            pressed = self._trigger_is_down()
            self.boosted = bool(self.settings["enabled"] and pressed)
            set_pointer_speed(
                self.settings["boost_speed"]
                if self.boosted
                else self.settings["normal_speed"]
            )
            self._refresh_status()
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"設定を保存できませんでした。\n\n{exc}")

    def _poll_interval(self) -> int:
        # Sub-15 ms timers can push the Tk event loop into a busy spin on
        # Windows, so never poll faster than 16 ms; idle slowly while disabled.
        if not self.settings["enabled"]:
            return 500
        return max(16, int(self.settings["poll_ms"]))

    def _trigger_is_down(self) -> bool:
        vk = KEY_CHOICES[self.settings["trigger"]]
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def _poll_trigger(self) -> None:
        if self.exiting:
            return
        pressed = self._trigger_is_down()
        should_boost = bool(self.settings["enabled"] and pressed)
        if should_boost != self.boosted:
            set_pointer_speed(
                self.settings["boost_speed"]
                if should_boost
                else self.settings["normal_speed"]
            )
            self.boosted = should_boost
        self.root.after(self._poll_interval(), self._poll_trigger)

    def _refresh_status(self) -> None:
        if self.exiting:
            return
        if self.root.state() == "withdrawn":
            # Nobody sees the labels while hidden; refresh lazily.
            self.root.after(2000, self._refresh_status)
            return
        try:
            speed = get_pointer_speed()
            self.current_label.set(f"現在のWindows感度:  {speed} / 20")
        except OSError:
            self.current_label.set("現在のWindows感度: 取得できません")
        if not self.settings["enabled"]:
            state = "オフ"
        elif self.boosted:
            state = f"加速中（{self.settings['trigger']}）"
        else:
            state = f"通常（{self.settings['trigger']}待機中）"
        self.status_label.set(f"動作状態:  {state}")
        self.root.after(500, self._refresh_status)

    def _process_commands(self) -> None:
        if self.exiting:
            return
        while True:
            try:
                command = self.commands.get_nowait()
            except queue.Empty:
                break
            if command == "show":
                self.show_window()
            elif command == "toggle":
                self.settings["enabled"] = not self.settings["enabled"]
                self.enabled_var.set(self.settings["enabled"])
                save_settings(self.settings)
                if not self.settings["enabled"]:
                    self.boosted = False
                    set_pointer_speed(self.settings["normal_speed"])
            elif command == "exit":
                self.exit_app()
                return
        self.root.after(100, self._process_commands)

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))

    def hide_window(self) -> None:
        self.root.withdraw()

    def exit_app(self) -> None:
        if self.exiting:
            return
        self.exiting = True
        try:
            set_pointer_speed(self.settings["normal_speed"])
        finally:
            self.tray.stop()
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--startup", action="store_true", help="非表示で起動")
    parser.add_argument("--show", action="store_true", help="設定画面を表示")
    return parser.parse_args()


def main() -> int:
    if sys.platform != "win32":
        print("このスクリプトはWindows版です。Macでは mac/build.sh でアプリを作ってください。", file=sys.stderr)
        return 1

    args = parse_args()
    mutex_name = "Local\\HHKBPointerBoostSingleInstance"
    mutex = kernel32.CreateMutexW(None, False, mutex_name)
    if not mutex:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        hwnd = user32.FindWindowW(TRAY_CLASS_NAME, APP_NAME)
        if hwnd:
            user32.PostMessageW(hwnd, WM_TRAY, 0, WM_LBUTTONDBLCLK)
        kernel32.CloseHandle(mutex)
        return 0

    app = PointerBoostApp(show_on_start=not args.startup or args.show)

    def stop(_signum, _frame):
        app.commands.put("exit")

    signal.signal(signal.SIGTERM, stop)
    try:
        app.run()
    finally:
        if not app.exiting:
            app.exit_app()
        kernel32.CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
