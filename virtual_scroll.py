"""
VirtualScroll - Mouse Scroll Workaround Utility
================================================
A lightweight Windows desktop application that runs in the system tray and
simulates mouse wheel scrolling through global keyboard shortcuts and mouse
gestures, designed as a workaround for a broken mouse scroll wheel.

Modes:
  Mode 1 (Keyboard): Alt + Up/Down Arrow to scroll
  Mode 2 (Mouse):    Right-Click held + vertical mouse movement to scroll,
                     or Mouse Button 4/5 to scroll

Author: VirtualScroll Project
License: MIT
"""

import threading
import time
import atexit
import ctypes
from enum import Enum, auto

from pynput import keyboard, mouse
from pynput.mouse import Controller as MouseController
import pystray
from PIL import Image, ImageDraw


# ─────────────────────────────────────────────
#  Constants & Configuration
# ─────────────────────────────────────────────

SCROLL_AMOUNT = 3          # Number of lines to scroll per trigger
SCROLL_INTERVAL = 0.05     # Repeat interval when key is held down (seconds)
DEBOUNCE_MS = 50           # Key-repeat flooding protection (milliseconds)
GESTURE_THRESHOLD = 5      # Mouse gesture activation threshold (pixels)
GESTURE_SCROLL_RATIO = 0.4 # Mouse movement to scroll conversion ratio
APP_NAME = "VirtualScroll"
ICON_SIZE = 64


# ─────────────────────────────────────────────
#  Enums
# ─────────────────────────────────────────────

class AppState(Enum):
    """Application state."""
    RUNNING = auto()
    PAUSED = auto()


class ScrollMode(Enum):
    """Scroll simulation mode."""
    KEYBOARD = auto()   # Mode 1: Alt + Arrow Keys
    MOUSE = auto()      # Mode 2: Right-Click + Gesture / Mouse Buttons


# ─────────────────────────────────────────────
#  ScrollSimulator
# ─────────────────────────────────────────────

class ScrollSimulator:
    """
    Core scroll simulation class.
    Produces scroll events using pynput.mouse.Controller.
    """

    def __init__(self, scroll_amount: int = SCROLL_AMOUNT):
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
#  KeyboardScrollHandler (Mode 1)
# ─────────────────────────────────────────────

class KeyboardScrollHandler:
    """
    Mode 1: Scroll simulation via Alt + Up/Down Arrow keys.
    Provides smooth scrolling when keys are held down.
    Prevents key-repeat flooding with a debounce mechanism.
    """

    def __init__(self, simulator: ScrollSimulator, get_state_fn):
        self._simulator = simulator
        self._get_state = get_state_fn
        self._listener = None
        self._lock = threading.Lock()

        # Track active scroll direction
        self._scrolling_up = False
        self._scrolling_down = False
        self._scroll_thread_up = None
        self._scroll_thread_down = None

        # Alt key state
        self._alt_pressed = False

        # Debounce
        self._last_scroll_time = 0

    def start(self):
        """Start the keyboard listener."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            suppress=False  # Does not block normal key inputs
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """Stop the keyboard listener."""
        self._scrolling_up = False
        self._scrolling_down = False
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key):
        """Key press event handler."""
        # Skip processing if app is paused
        if self._get_state() != AppState.RUNNING:
            return

        # Track Alt key state
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self._alt_pressed = True
            return

        # Only proceed if Alt is held
        if not self._alt_pressed:
            return

        if key == keyboard.Key.up:
            self._start_scroll_up()
        elif key == keyboard.Key.down:
            self._start_scroll_down()

    def _on_release(self, key):
        """Key release event handler."""
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self._alt_pressed = False
            self._stop_all_scrolling()
            return

        if key == keyboard.Key.up:
            self._scrolling_up = False
        elif key == keyboard.Key.down:
            self._scrolling_down = False

    def _start_scroll_up(self):
        """Start upward scrolling (smooth scrolling thread)."""
        with self._lock:
            if self._scrolling_up:
                return
            self._scrolling_up = True

        thread = threading.Thread(target=self._scroll_loop, args=("up",), daemon=True)
        self._scroll_thread_up = thread
        thread.start()

    def _start_scroll_down(self):
        """Start downward scrolling (smooth scrolling thread)."""
        with self._lock:
            if self._scrolling_down:
                return
            self._scrolling_down = True

        thread = threading.Thread(target=self._scroll_loop, args=("down",), daemon=True)
        self._scroll_thread_down = thread
        thread.start()

    def _scroll_loop(self, direction: str):
        """
        Continuous scroll loop. Runs as long as the key is held down.
        Prevents flooding with debounce.
        """
        while True:
            # State check
            if direction == "up" and not self._scrolling_up:
                break
            if direction == "down" and not self._scrolling_down:
                break
            if self._get_state() != AppState.RUNNING:
                break

            # Debounce check
            now = time.time() * 1000  # in milliseconds
            if now - self._last_scroll_time < DEBOUNCE_MS:
                time.sleep(SCROLL_INTERVAL)
                continue

            self._last_scroll_time = now

            # Perform scroll
            if direction == "up":
                self._simulator.scroll_up()
            else:
                self._simulator.scroll_down()

            time.sleep(SCROLL_INTERVAL)

    def _stop_all_scrolling(self):
        """Stop all active scrolling."""
        self._scrolling_up = False
        self._scrolling_down = False


# ─────────────────────────────────────────────
#  MouseGestureHandler (Mode 2)
# ─────────────────────────────────────────────

class MouseGestureHandler:
    """
    Mode 2: Scroll simulation via mouse gestures and extra buttons.

    Option A: Mouse Button 4 (back) -> scroll up, Button 5 (forward) -> scroll down
    Option B: Right-click held + vertical mouse movement -> scroll

    Does not interfere with normal right-click usage: if no movement is
    detected, the right-click event passes through normally.
    """

    def __init__(self, simulator: ScrollSimulator, get_state_fn):
        self._simulator = simulator
        self._get_state = get_state_fn
        self._listener = None
        self._lock = threading.Lock()

        # Right-click gesture state
        self._right_pressed = False
        self._gesture_active = False
        self._gesture_start_y = 0
        self._gesture_last_y = 0
        self._accumulated_dy = 0.0

    def start(self):
        """Start the mouse listener."""
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
            self._listener.stop()
            self._listener = None

    def _on_click(self, x, y, button, pressed):
        """Mouse click event handler."""
        if self._get_state() != AppState.RUNNING:
            return

        # Mouse Button 4/5 scroll (Option A)
        if button == mouse.Button.x1:  # Button 4 (back)
            if pressed:
                self._simulator.scroll_up()
            return False  # Suppress original event

        if button == mouse.Button.x2:  # Button 5 (forward)
            if pressed:
                self._simulator.scroll_down()
            return False  # Suppress original event

        # Right-click gesture start/stop (Option B)
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
                # If gesture was active, suppress the right-click event
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

        # Check total movement - is it enough to qualify as a gesture?
        total_movement = abs(y - self._gesture_start_y)
        if total_movement > GESTURE_THRESHOLD:
            self._gesture_active = True

        if self._gesture_active:
            # Convert mouse movement to scroll
            self._accumulated_dy += dy * GESTURE_SCROLL_RATIO
            scroll_lines = int(self._accumulated_dy)
            if scroll_lines != 0:
                # positive dy = mouse moved down = scroll down
                self._simulator.scroll(-scroll_lines)
                self._accumulated_dy -= scroll_lines


# ─────────────────────────────────────────────
#  TrayManager
# ─────────────────────────────────────────────

class TrayManager:
    """
    Windows System Tray integration.
    Provides a dynamic icon (green = active, red = paused) and context menu.
    """

    def __init__(self, app):
        """
        Args:
            app: VirtualScrollApp reference (for state and control access)
        """
        self._app = app
        self._icon = None

    def _create_icon_image(self, color: str) -> Image.Image:
        """
        Create a tray icon with the specified color.
        Draws a simple scroll wheel symbol.
        """
        img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Background circle
        bg_color = (46, 204, 113) if color == "green" else (231, 76, 60)
        draw.ellipse([4, 4, ICON_SIZE - 4, ICON_SIZE - 4], fill=bg_color)

        # Inner circle (scroll wheel symbol)
        inner_margin = 16
        draw.ellipse(
            [inner_margin, inner_margin,
             ICON_SIZE - inner_margin, ICON_SIZE - inner_margin],
            fill=(255, 255, 255, 200)
        )

        # Center arrow marks (up and down)
        center_x = ICON_SIZE // 2
        center_y = ICON_SIZE // 2
        arrow_color = bg_color

        # Up arrow
        draw.polygon([
            (center_x, center_y - 10),
            (center_x - 6, center_y - 3),
            (center_x + 6, center_y - 3)
        ], fill=arrow_color)

        # Down arrow
        draw.polygon([
            (center_x, center_y + 10),
            (center_x - 6, center_y + 3),
            (center_x + 6, center_y + 3)
        ], fill=arrow_color)

        return img

    def _get_status_text(self, item=None) -> str:
        """Return current status as text."""
        state = "Running" if self._app.state == AppState.RUNNING else "Paused"
        mode_names = []
        if ScrollMode.KEYBOARD in self._app.active_modes:
            mode_names.append("Keyboard")
        if ScrollMode.MOUSE in self._app.active_modes:
            mode_names.append("Mouse")
        modes = " + ".join(mode_names) if mode_names else "None"
        return f"[{state}] Modes: {modes}"

    def _build_menu(self) -> pystray.Menu:
        """Build the tray context menu."""
        return pystray.Menu(
            pystray.MenuItem(
                self._get_status_text,
                action=None,
                enabled=False
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "Pause" if self._app.state == AppState.RUNNING else "Resume",
                self._on_toggle
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                lambda item: "[x] Keyboard Mode (Alt+Arrows)" if ScrollMode.KEYBOARD in self._app.active_modes else "[ ] Keyboard Mode (Alt+Arrows)",
                self._on_toggle_keyboard
            ),
            pystray.MenuItem(
                lambda item: "[x] Mouse Mode (RClick+Drag / Btn4/5)" if ScrollMode.MOUSE in self._app.active_modes else "[ ] Mouse Mode (RClick+Drag / Btn4/5)",
                self._on_toggle_mouse
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit)
        )

    def _on_toggle(self, icon, item):
        """Toggle the application state (Running <-> Paused)."""
        if self._app.state == AppState.RUNNING:
            self._app.pause()
        else:
            self._app.resume()
        self._update_icon()

    def _on_toggle_keyboard(self, icon, item):
        """Toggle keyboard mode."""
        self._app.toggle_mode(ScrollMode.KEYBOARD)
        self._update_icon()

    def _on_toggle_mouse(self, icon, item):
        """Toggle mouse mode."""
        self._app.toggle_mode(ScrollMode.MOUSE)
        self._update_icon()

    def _on_exit(self, icon, item):
        """Exit the application."""
        self._app.shutdown()
        icon.stop()

    def _update_icon(self):
        """Update the tray icon based on current state."""
        if self._icon:
            color = "green" if self._app.state == AppState.RUNNING else "red"
            self._icon.icon = self._create_icon_image(color)

    def run(self):
        """
        Create and run the system tray icon.
        This method blocks - must be called from the main thread.
        """
        self._icon = pystray.Icon(
            APP_NAME,
            icon=self._create_icon_image("green"),
            title=f"{APP_NAME} - Running",
            menu=self._build_menu()
        )
        self._icon.run()


# ─────────────────────────────────────────────
#  VirtualScrollApp (Main Controller)
# ─────────────────────────────────────────────

class VirtualScrollApp:
    """
    Main application class that coordinates all components.
    Provides graceful shutdown, mode management, and state management.
    """

    def __init__(self):
        self.state = AppState.RUNNING
        self.active_modes = {ScrollMode.KEYBOARD, ScrollMode.MOUSE}
        self._lock = threading.Lock()

        # Components
        self._simulator = ScrollSimulator()
        self._keyboard_handler = KeyboardScrollHandler(self._simulator, self._get_state)
        self._mouse_handler = MouseGestureHandler(self._simulator, self._get_state)
        self._tray_manager = TrayManager(self)

        # Register cleanup for graceful shutdown
        atexit.register(self._cleanup)

    def _get_state(self) -> AppState:
        """Thread-safe state access."""
        return self.state

    def pause(self):
        """Pause the application (stop scroll simulation)."""
        with self._lock:
            self.state = AppState.PAUSED

    def resume(self):
        """Resume the application."""
        with self._lock:
            self.state = AppState.RUNNING

    def toggle_mode(self, mode: ScrollMode):
        """Enable or disable the specified mode."""
        with self._lock:
            if mode in self.active_modes:
                self.active_modes.discard(mode)
                # Stop the relevant handler
                if mode == ScrollMode.KEYBOARD:
                    self._keyboard_handler.stop()
                elif mode == ScrollMode.MOUSE:
                    self._mouse_handler.stop()
            else:
                self.active_modes.add(mode)
                # Start the relevant handler
                if mode == ScrollMode.KEYBOARD:
                    self._keyboard_handler.start()
                elif mode == ScrollMode.MOUSE:
                    self._mouse_handler.start()

    def shutdown(self):
        """Shut down the application cleanly."""
        self.state = AppState.PAUSED
        self._cleanup()

    def _cleanup(self):
        """Cleanly stop all listeners and threads."""
        self._keyboard_handler.stop()
        self._mouse_handler.stop()

    def run(self):
        """
        Start the application.
        Keyboard and mouse handlers run in separate threads,
        tray manager runs in the main thread.
        """
        print(f"[{APP_NAME}] Starting...")
        print(f"[{APP_NAME}] Mode 1: Alt + Up/Down Arrow -> Scroll")
        print(f"[{APP_NAME}] Mode 2: Right-Click + Drag / Mouse Btn 4/5 -> Scroll")
        print(f"[{APP_NAME}] Running in system tray. Right-click tray icon for options.")

        # Start handlers
        if ScrollMode.KEYBOARD in self.active_modes:
            self._keyboard_handler.start()

        if ScrollMode.MOUSE in self.active_modes:
            self._mouse_handler.start()

        # Run tray manager in the main thread (blocks)
        try:
            self._tray_manager.run()
        except KeyboardInterrupt:
            self.shutdown()


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────

def main():
    """Start the application."""
    # Set DPI awareness for high-resolution displays on Windows
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = VirtualScrollApp()
    app.run()


if __name__ == "__main__":
    main()
