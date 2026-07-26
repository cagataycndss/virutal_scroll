"""
VirtualScroll - Mouse Scroll Workaround Utility with GUI & Customizable Hotkeys
==============================================================================
A lightweight Windows desktop application that runs in the system tray and
simulates mouse wheel scrolling through customizable global keyboard shortcuts
and mouse gestures.

Author: VirtualScroll Project
License: MIT
"""

import os
import sys
import json
import threading
import time
import atexit
import ctypes
from enum import Enum, auto

from pynput import keyboard, mouse
from pynput.mouse import Controller as MouseController
import pystray
from PIL import Image, ImageDraw

import tkinter as tk
from tkinter import ttk, messagebox


# ─────────────────────────────────────────────
#  Constants & Configuration Defaults
# ─────────────────────────────────────────────

APP_NAME = "VirtualScroll"
ICON_SIZE = 64

DEFAULT_CONFIG = {
    "modifier_key": "ctrl_r",       # ctrl_r, ctrl_l, alt_r, alt_l, shift_r, shift_l, ctrl, alt, shift, none
    "up_key": "up",                 # up, page_up, w, i
    "down_key": "down",             # down, page_down, s, k
    "scroll_amount": 3,             # lines per scroll trigger
    "scroll_interval": 0.05,        # seconds between repeated scroll triggers
    "debounce_ms": 50,              # ms protection against flooding
    "keyboard_mode_enabled": True,  # Mode 1 active
    "mouse_mode_enabled": True,     # Mode 2 active
    "gesture_threshold": 5,         # pixels before gesture triggers
    "gesture_scroll_ratio": 0.4     # mouse move px to scroll ratio
}

# Display mappings for UI Comboboxes
MODIFIER_OPTIONS = [
    ("Right Ctrl", "ctrl_r"),
    ("Left Ctrl", "ctrl_l"),
    ("Right Alt", "alt_r"),
    ("Left Alt", "alt_l"),
    ("Right Shift", "shift_r"),
    ("Left Shift", "shift_l"),
    ("Ctrl (Left or Right)", "ctrl"),
    ("Alt (Left or Right)", "alt"),
    ("Shift (Left or Right)", "shift"),
    ("None (Arrow Keys Only)", "none")
]

TRIGGER_OPTIONS = [
    ("Up / Down Arrow Keys", ("up", "down")),
    ("Page Up / Page Down Keys", ("page_up", "page_down")),
    ("W / S Keys", ("w", "s")),
    ("I / K Keys", ("i", "k"))
]


# ─────────────────────────────────────────────
#  ConfigManager
# ─────────────────────────────────────────────

class ConfigManager:
    """Manages loading and saving configuration to JSON."""

    def __init__(self, filename="config.json"):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        self.config_path = os.path.join(base_dir, filename)
        self.config = self.load_config()

    def load_config(self) -> dict:
        """Load settings from config.json or fall back to defaults."""
        config = DEFAULT_CONFIG.copy()
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    config.update(loaded)
            except Exception as e:
                print(f"[{APP_NAME}] Error loading config file: {e}")
        return config

    def save_config(self, new_settings: dict) -> bool:
        """Save updated settings to config.json."""
        self.config.update(new_settings)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[{APP_NAME}] Error saving config file: {e}")
            return False


# ─────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────

class AppState(Enum):
    """Application operational state."""
    RUNNING = auto()
    PAUSED = auto()


class ScrollMode(Enum):
    """Scroll simulation mode."""
    KEYBOARD = auto()   # Mode 1: Keyboard hotkeys
    MOUSE = auto()      # Mode 2: Right-Click + Gesture / Mouse Buttons


# ─────────────────────────────────────────────
#  ScrollSimulator
# ─────────────────────────────────────────────

class ScrollSimulator:
    """
    Core scroll simulation class.
    Produces scroll events using pynput.mouse.Controller.
    """

    def __init__(self, scroll_amount: int = 3):
        self._controller = MouseController()
        self.scroll_amount = scroll_amount

    def scroll_up(self, amount: int = None):
        """Simulate upward scroll."""
        amt = amount or self.scroll_amount
        self._controller.scroll(0, amt)

    def scroll_down(self, amount: int = None):
        """Simulate downward scroll."""
        amt = amount or self.scroll_amount
        self._controller.scroll(0, -amt)

    def scroll(self, dy: int):
        """
        General scroll function.
        dy > 0: scroll up, dy < 0: scroll down
        """
        self._controller.scroll(0, dy)


# ─────────────────────────────────────────────
#  KeyboardScrollHandler (Mode 1 - Customizable)
# ─────────────────────────────────────────────

class KeyboardScrollHandler:
    """
    Mode 1: Scroll simulation via customizable shortcut key combinations.
    Supports smooth scrolling when keys are held down and debounce protection.
    """

    def __init__(self, simulator: ScrollSimulator, get_state_fn, config: dict):
        self._simulator = simulator
        self._get_state = get_state_fn
        self._listener = None
        self._lock = threading.Lock()

        # Key configuration
        self.modifier_key = config.get("modifier_key", "ctrl_r")
        self.up_key = config.get("up_key", "up")
        self.down_key = config.get("down_key", "down")
        self.scroll_interval = config.get("scroll_interval", 0.05)
        self.debounce_ms = config.get("debounce_ms", 50)

        # Track state
        self._scrolling_up = False
        self._scrolling_down = False
        self._scroll_thread_up = None
        self._scroll_thread_down = None

        self._modifier_pressed = (self.modifier_key == "none")
        self._last_scroll_time = 0

    def update_config(self, config: dict):
        """Update hotkey configuration in real-time."""
        with self._lock:
            self.modifier_key = config.get("modifier_key", "ctrl_r")
            self.up_key = config.get("up_key", "up")
            self.down_key = config.get("down_key", "down")
            self.scroll_interval = config.get("scroll_interval", 0.05)
            self.debounce_ms = config.get("debounce_ms", 50)
            self._modifier_pressed = (self.modifier_key == "none")
            self._stop_all_scrolling()

    def start(self):
        """Start the keyboard listener."""
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """Stop the keyboard listener."""
        self._stop_all_scrolling()
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _is_modifier_key(self, key) -> bool:
        """Check if the pressed key matches the configured modifier key."""
        mod = self.modifier_key
        if mod == "none":
            return True
        elif mod == "ctrl_r":
            return key == keyboard.Key.ctrl_r
        elif mod == "ctrl_l":
            return key == keyboard.Key.ctrl_l
        elif mod == "alt_r":
            return key in (keyboard.Key.alt_r, keyboard.Key.alt_gr)
        elif mod == "alt_l":
            return key == keyboard.Key.alt_l
        elif mod == "shift_r":
            return key == keyboard.Key.shift_r
        elif mod == "shift_l":
            return key == keyboard.Key.shift_l
        elif mod == "ctrl":
            return key in (keyboard.Key.ctrl_r, keyboard.Key.ctrl_l)
        elif mod == "alt":
            return key in (keyboard.Key.alt_r, keyboard.Key.alt_l, keyboard.Key.alt_gr)
        elif mod == "shift":
            return key in (keyboard.Key.shift_r, keyboard.Key.shift_l)
        return False

    def _matches_trigger_key(self, key, target_name: str) -> bool:
        """Check if the pressed key matches a target trigger key name."""
        if target_name == "up":
            return key == keyboard.Key.up
        elif target_name == "down":
            return key == keyboard.Key.down
        elif target_name == "page_up":
            return key == keyboard.Key.page_up
        elif target_name == "page_down":
            return key == keyboard.Key.page_down
        else:
            if isinstance(key, keyboard.KeyCode) and key.char:
                return key.char.lower() == target_name.lower()
        return False

    def _on_press(self, key):
        """Key press handler."""
        if self._get_state() != AppState.RUNNING:
            return

        # Check modifier press
        if self.modifier_key != "none":
            if self._is_modifier_key(key):
                self._modifier_pressed = True
                return

            if not self._modifier_pressed:
                return

        # Check trigger key press
        if self._matches_trigger_key(key, self.up_key):
            self._start_scroll_up()
        elif self._matches_trigger_key(key, self.down_key):
            self._start_scroll_down()

    def _on_release(self, key):
        """Key release handler."""
        if self.modifier_key != "none" and self._is_modifier_key(key):
            self._modifier_pressed = False
            self._stop_all_scrolling()
            return

        if self._matches_trigger_key(key, self.up_key):
            self._scrolling_up = False
        elif self._matches_trigger_key(key, self.down_key):
            self._scrolling_down = False

    def _start_scroll_up(self):
        """Start smooth upward scrolling thread."""
        with self._lock:
            if self._scrolling_up:
                return
            self._scrolling_up = True

        thread = threading.Thread(target=self._scroll_loop, args=("up",), daemon=True)
        self._scroll_thread_up = thread
        thread.start()

    def _start_scroll_down(self):
        """Start smooth downward scrolling thread."""
        with self._lock:
            if self._scrolling_down:
                return
            self._scrolling_down = True

        thread = threading.Thread(target=self._scroll_loop, args=("down",), daemon=True)
        self._scroll_thread_down = thread
        thread.start()

    def _scroll_loop(self, direction: str):
        """Continuous scroll loop running while trigger key is held."""
        while True:
            if direction == "up" and not self._scrolling_up:
                break
            if direction == "down" and not self._scrolling_down:
                break
            if self._get_state() != AppState.RUNNING:
                break

            now = time.time() * 1000
            if now - self._last_scroll_time < self.debounce_ms:
                time.sleep(self.scroll_interval)
                continue

            self._last_scroll_time = now

            if direction == "up":
                self._simulator.scroll_up()
            else:
                self._simulator.scroll_down()

            time.sleep(self.scroll_interval)

    def _stop_all_scrolling(self):
        """Stop active scroll threads."""
        self._scrolling_up = False
        self._scrolling_down = False


# ─────────────────────────────────────────────
#  MouseGestureHandler (Mode 2)
# ─────────────────────────────────────────────

class MouseGestureHandler:
    """
    Mode 2: Scroll simulation via mouse gestures and extra buttons.
    """

    def __init__(self, simulator: ScrollSimulator, get_state_fn, config: dict):
        self._simulator = simulator
        self._get_state = get_state_fn
        self._listener = None

        self.threshold = config.get("gesture_threshold", 5)
        self.ratio = config.get("gesture_scroll_ratio", 0.4)

        self._right_pressed = False
        self._gesture_active = False
        self._gesture_start_y = 0
        self._gesture_last_y = 0
        self._accumulated_dy = 0.0

    def update_config(self, config: dict):
        """Update mouse gesture configuration."""
        self.threshold = config.get("gesture_threshold", 5)
        self.ratio = config.get("gesture_scroll_ratio", 0.4)

    def start(self):
        """Start the mouse listener."""
        if self._listener is not None:
            return
        self._listener = mouse.Listener(
            on_click=self._on_click,
            on_move=self._on_move,
            suppress=False
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """Stop the mouse listener."""
        self._right_pressed = False
        self._gesture_active = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None

    def _on_click(self, x, y, button, pressed):
        """Mouse click event handler."""
        if self._get_state() != AppState.RUNNING:
            return

        if button == mouse.Button.x1:  # Button 4 (back)
            if pressed:
                self._simulator.scroll_up()
            return False

        if button == mouse.Button.x2:  # Button 5 (forward)
            if pressed:
                self._simulator.scroll_down()
            return False

        if button == mouse.Button.right:
            if pressed:
                self._right_pressed = True
                self._gesture_start_y = y
                self._gesture_last_y = y
                self._gesture_active = False
                self._accumulated_dy = 0.0
            else:
                self._right_pressed = False
                was_gesture = self._gesture_active
                self._gesture_active = False
                if was_gesture:
                    return False

    def _on_move(self, x, y):
        """Mouse move event handler."""
        if self._get_state() != AppState.RUNNING:
            return

        if not self._right_pressed:
            return

        dy = y - self._gesture_last_y
        self._gesture_last_y = y

        total_movement = abs(y - self._gesture_start_y)
        if total_movement > self.threshold:
            self._gesture_active = True

        if self._gesture_active:
            self._accumulated_dy += dy * self.ratio
            scroll_lines = int(self._accumulated_dy)
            if scroll_lines != 0:
                self._simulator.scroll(-scroll_lines)
                self._accumulated_dy -= scroll_lines


# ─────────────────────────────────────────────
#  TrayManager
# ─────────────────────────────────────────────

class TrayManager:
    """
    Windows System Tray integration using pystray.
    Runs silently in background and triggers the Tkinter GUI on demand.
    """

    def __init__(self, app):
        self._app = app
        self._icon = None

    def _create_icon_image(self, color: str) -> Image.Image:
        """Generate a tray icon image."""
        img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        bg_color = (46, 204, 113) if color == "green" else (231, 76, 60)
        draw.ellipse([4, 4, ICON_SIZE - 4, ICON_SIZE - 4], fill=bg_color)

        inner_margin = 16
        draw.ellipse(
            [inner_margin, inner_margin, ICON_SIZE - inner_margin, ICON_SIZE - inner_margin],
            fill=(255, 255, 255, 220)
        )

        center_x = ICON_SIZE // 2
        center_y = ICON_SIZE // 2

        # Up arrow
        draw.polygon([
            (center_x, center_y - 10),
            (center_x - 6, center_y - 3),
            (center_x + 6, center_y - 3)
        ], fill=bg_color)

        # Down arrow
        draw.polygon([
            (center_x, center_y + 10),
            (center_x - 6, center_y + 3),
            (center_x + 6, center_y + 3)
        ], fill=bg_color)

        return img

    def _get_status_text(self, item=None) -> str:
        """Return status string for the tray menu."""
        state = "Running" if self._app.state == AppState.RUNNING else "Paused"
        return f"Status: [{state}]"

    def _build_menu(self) -> pystray.Menu:
        """Build context menu."""
        return pystray.Menu(
            pystray.MenuItem("Open Settings / GUI", self._on_open_gui, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(self._get_status_text, action=None, enabled=False),
            pystray.MenuItem(
                lambda item: "Pause" if self._app.state == AppState.RUNNING else "Resume",
                self._on_toggle_state
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit)
        )

    def _on_open_gui(self, icon=None, item=None):
        """Open/show the Tkinter Settings GUI."""
        self._app.show_gui()

    def _on_toggle_state(self, icon=None, item=None):
        """Toggle AppState (RUNNING <-> PAUSED)."""
        if self._app.state == AppState.RUNNING:
            self._app.pause()
        else:
            self._app.resume()
        self.update_icon()

    def _on_exit(self, icon=None, item=None):
        """Completely exit the application."""
        self._app.shutdown()

    def update_icon(self):
        """Update tray icon image according to current state."""
        if self._icon:
            color = "green" if self._app.state == AppState.RUNNING else "red"
            self._icon.icon = self._create_icon_image(color)

    def start(self):
        """Launch system tray icon on a background daemon thread."""
        self._icon = pystray.Icon(
            APP_NAME,
            icon=self._create_icon_image("green"),
            title=f"{APP_NAME} - Running",
            menu=self._build_menu()
        )
        # Use a background thread so Tkinter mainloop can run on main thread
        thread = threading.Thread(target=self._icon.run, daemon=True)
        thread.start()

    def stop(self):
        """Stop tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass


# ─────────────────────────────────────────────
#  VirtualScrollGUI (Tkinter Settings Window)
# ─────────────────────────────────────────────

class VirtualScrollGUI:
    """
    Tkinter-based Settings GUI window.
    Allows user to select custom shortcut keys and scroll parameters.
    """

    def __init__(self, root: tk.Tk, app):
        self.root = root
        self.app = app
        self.config_manager = app.config_manager

        self.root.title("VirtualScroll Settings")
        self.root.geometry("460x520")
        self.root.resizable(False, False)

        # Handle window close button (X) -> Hide to tray
        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self._init_styles()
        self._build_ui()
        self.load_settings_to_ui()

    def _init_styles(self):
        """Apply modern dark theme styling."""
        self.bg_color = "#1e1e2e"
        self.card_bg = "#282838"
        self.fg_color = "#cdd6f4"
        self.accent_color = "#89b4fa"
        self.button_bg = "#45475a"
        self.button_fg = "#ffffff"

        self.root.configure(bg=self.bg_color)

        style = ttk.Style()
        style.theme_use("clam")

        # Custom ttk styles
        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_bg, relief="flat", borderwidth=1)
        style.configure("TLabel", background=self.bg_color, foreground=self.fg_color, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.card_bg, foreground=self.fg_color, font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=self.bg_color, foreground=self.accent_color, font=("Segoe UI", 14, "bold"))
        style.configure("Header.TLabel", background=self.card_bg, foreground=self.accent_color, font=("Segoe UI", 11, "bold"))

        style.configure("TCheckbutton", background=self.card_bg, foreground=self.fg_color, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", self.card_bg)], foreground=[("active", self.accent_color)])

        style.configure("TCombobox", fieldbackground="#313244", background="#45475a", foreground=self.fg_color, font=("Segoe UI", 10))
        style.map("TCombobox", fieldbackground=[("readonly", "#313244")], foreground=[("readonly", self.fg_color)])

    def _build_ui(self):
        """Construct GUI layout."""
        # Main padding container
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Header Title
        title_label = ttk.Label(container, text=" VirtualScroll Settings", style="Title.TLabel")
        title_label.pack(anchor="w", pady=(0, 2))

        subtitle = ttk.Label(container, text="Customize your preferred shortcut keys and scroll parameters.", font=("Segoe UI", 9))
        subtitle.pack(anchor="w", pady=(0, 15))

        # ── Group 1: Shortcut Key Selection ──
        key_card = ttk.Frame(container, style="Card.TFrame", padding=15)
        key_card.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(key_card, text="⌨ Shortcut Key Combination", style="Header.TLabel").pack(anchor="w", pady=(0, 10))

        # Modifier Combobox
        mod_frame = ttk.Frame(key_card, style="Card.TFrame")
        mod_frame.pack(fill=tk.X, pady=4)
        ttk.Label(mod_frame, text="Modifier Key:", style="Card.TLabel").pack(side=tk.LEFT)

        self.mod_combo = ttk.Combobox(
            mod_frame,
            values=[label for label, _ in MODIFIER_OPTIONS],
            state="readonly",
            width=26
        )
        self.mod_combo.pack(side=tk.RIGHT)

        # Trigger Combobox
        trig_frame = ttk.Frame(key_card, style="Card.TFrame")
        trig_frame.pack(fill=tk.X, pady=4)
        ttk.Label(trig_frame, text="Scroll Direction Keys:", style="Card.TLabel").pack(side=tk.LEFT)

        self.trig_combo = ttk.Combobox(
            trig_frame,
            values=[label for label, _ in TRIGGER_OPTIONS],
            state="readonly",
            width=26
        )
        self.trig_combo.pack(side=tk.RIGHT)

        # ── Group 2: Scroll Speed & Modes ──
        opt_card = ttk.Frame(container, style="Card.TFrame", padding=15)
        opt_card.pack(fill=tk.X, pady=(0, 15))

        ttk.Label(opt_card, text="⚙ Scroll Speed & Modes", style="Header.TLabel").pack(anchor="w", pady=(0, 10))

        # Scroll Amount Spinbox
        amt_frame = ttk.Frame(opt_card, style="Card.TFrame")
        amt_frame.pack(fill=tk.X, pady=4)
        ttk.Label(amt_frame, text="Scroll Step (Lines per tick):", style="Card.TLabel").pack(side=tk.LEFT)

        self.amt_spin = tk.Spinbox(
            amt_frame,
            from_=1,
            to=20,
            width=6,
            bg="#313244",
            fg=self.fg_color,
            buttonbackground="#45475a",
            relief="flat",
            font=("Segoe UI", 10)
        )
        self.amt_spin.pack(side=tk.RIGHT)

        # Mode Checkboxes
        self.kb_var = tk.BooleanVar(value=True)
        self.kb_check = ttk.Checkbutton(
            opt_card,
            text="Enable Keyboard Mode (Hotkeys)",
            variable=self.kb_var
        )
        self.kb_check.pack(anchor="w", pady=(8, 2))

        self.mouse_var = tk.BooleanVar(value=True)
        self.mouse_check = ttk.Checkbutton(
            opt_card,
            text="Enable Mouse Mode (Right-Click Drag / Extra Buttons)",
            variable=self.mouse_var
        )
        self.mouse_check.pack(anchor="w", pady=2)

        # ── Footer Action Buttons ──
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        save_btn = tk.Button(
            btn_frame,
            text="✔ Save & Apply",
            command=self.save_and_apply,
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=15,
            pady=6,
            cursor="hand2"
        )
        save_btn.pack(side=tk.LEFT)

        hide_btn = tk.Button(
            btn_frame,
            text="📌 Minimize to Tray",
            command=self.hide_to_tray,
            bg=self.button_bg,
            fg=self.button_fg,
            activebackground="#585b70",
            font=("Segoe UI", 10),
            relief="flat",
            padx=15,
            pady=6,
            cursor="hand2"
        )
        hide_btn.pack(side=tk.RIGHT)

    def load_settings_to_ui(self):
        """Populate GUI controls with values from config_manager."""
        cfg = self.config_manager.config

        # Match modifier
        cur_mod = cfg.get("modifier_key", "ctrl_r")
        for idx, (label, val) in enumerate(MODIFIER_OPTIONS):
            if val == cur_mod:
                self.mod_combo.current(idx)
                break
        else:
            self.mod_combo.current(0)

        # Match trigger pair
        cur_up = cfg.get("up_key", "up")
        cur_down = cfg.get("down_key", "down")
        target_pair = (cur_up, cur_down)
        for idx, (label, pair) in enumerate(TRIGGER_OPTIONS):
            if pair == target_pair:
                self.trig_combo.current(idx)
                break
        else:
            self.trig_combo.current(0)

        # Scroll amount
        self.amt_spin.delete(0, tk.END)
        self.amt_spin.insert(0, str(cfg.get("scroll_amount", 3)))

        # Checkboxes
        self.kb_var.set(cfg.get("keyboard_mode_enabled", True))
        self.mouse_var.set(cfg.get("mouse_mode_enabled", True))

    def save_and_apply(self):
        """Save current UI values to config and notify VirtualScrollApp."""
        mod_idx = self.mod_combo.current()
        mod_val = MODIFIER_OPTIONS[mod_idx][1] if mod_idx >= 0 else "ctrl_r"

        trig_idx = self.trig_combo.current()
        up_val, down_val = TRIGGER_OPTIONS[trig_idx][1] if trig_idx >= 0 else ("up", "down")

        try:
            amt_val = int(self.amt_spin.get())
            if amt_val < 1:
                amt_val = 1
        except ValueError:
            amt_val = 3

        new_settings = {
            "modifier_key": mod_val,
            "up_key": up_val,
            "down_key": down_val,
            "scroll_amount": amt_val,
            "keyboard_mode_enabled": self.kb_var.get(),
            "mouse_mode_enabled": self.mouse_var.get()
        }

        if self.config_manager.save_config(new_settings):
            self.app.apply_updated_config()
            messagebox.showinfo("Success", "New shortcut and scroll settings saved and applied successfully!")
            self.hide_to_tray()
        else:
            messagebox.showerror("Error", "Failed to save configuration file.")

    def show(self):
        """Bring window to front."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide_to_tray(self):
        """Withdraw GUI window back to system tray."""
        self.root.withdraw()


# ─────────────────────────────────────────────
#  VirtualScrollApp (Main Controller)
# ─────────────────────────────────────────────

class VirtualScrollApp:
    """
    Main application controller managing background listeners, GUI,
    and system tray icon lifecycle.
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self.state = AppState.RUNNING
        self._lock = threading.Lock()

        # Config & Simulator
        self.config_manager = ConfigManager()
        cfg = self.config_manager.config

        self._simulator = ScrollSimulator(scroll_amount=cfg.get("scroll_amount", 3))

        # Active modes
        self.active_modes = set()
        if cfg.get("keyboard_mode_enabled", True):
            self.active_modes.add(ScrollMode.KEYBOARD)
        if cfg.get("mouse_mode_enabled", True):
            self.active_modes.add(ScrollMode.MOUSE)

        # Subsystems
        self._keyboard_handler = KeyboardScrollHandler(self._simulator, self._get_state, cfg)
        self._mouse_handler = MouseGestureHandler(self._simulator, self._get_state, cfg)
        self.tray_manager = TrayManager(self)
        self.gui = VirtualScrollGUI(self.root, self)

        # System cleanup
        atexit.register(self._cleanup)

    def _get_state(self) -> AppState:
        return self.state

    def pause(self):
        """Pause scroll simulation."""
        with self._lock:
            self.state = AppState.PAUSED
        self.tray_manager.update_icon()

    def resume(self):
        """Resume scroll simulation."""
        with self._lock:
            self.state = AppState.RUNNING
        self.tray_manager.update_icon()

    def apply_updated_config(self):
        """Apply new configuration dynamically."""
        cfg = self.config_manager.config
        self._simulator.scroll_amount = cfg.get("scroll_amount", 3)
        self._keyboard_handler.update_config(cfg)
        self._mouse_handler.update_config(cfg)

        with self._lock:
            self.active_modes.clear()
            if cfg.get("keyboard_mode_enabled", True):
                self.active_modes.add(ScrollMode.KEYBOARD)
                self._keyboard_handler.start()
            else:
                self._keyboard_handler.stop()

            if cfg.get("mouse_mode_enabled", True):
                self.active_modes.add(ScrollMode.MOUSE)
                self._mouse_handler.start()
            else:
                self._mouse_handler.stop()

    def show_gui(self):
        """Schedule showing the GUI on Tkinter main thread."""
        self.root.after(0, self.gui.show)

    def shutdown(self):
        """Shutdown application completely."""
        self.state = AppState.PAUSED
        self._cleanup()
        self.root.after(0, self.root.quit)

    def _cleanup(self):
        """Clean up threads and handlers."""
        self._keyboard_handler.stop()
        self._mouse_handler.stop()
        self.tray_manager.stop()

    def run(self):
        """Start background listeners, tray icon, and Tkinter event loop."""
        print(f"[{APP_NAME}] Starting...")
        print(f"[{APP_NAME}] Running in system tray. Click the tray icon to open settings.")

        # Start mode listeners
        if ScrollMode.KEYBOARD in self.active_modes:
            self._keyboard_handler.start()

        if ScrollMode.MOUSE in self.active_modes:
            self._mouse_handler.start()

        # Start tray manager
        self.tray_manager.start()

        # Hide GUI window initially (starts silently in tray)
        self.root.withdraw()

        # Run main Tkinter event loop (blocks main thread)
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.shutdown()


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────

def main():
    """Application entry point."""
    # High DPI awareness for modern Windows displays
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    app = VirtualScrollApp(root)
    app.run()


if __name__ == "__main__":
    main()
