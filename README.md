# VirtualScroll

**A lightweight Windows desktop utility that simulates mouse wheel scrolling as a workaround for a broken scroll wheel.**

Runs silently in the system tray. Provides scroll simulation through keyboard shortcuts and mouse gestures.

---

## Features

### Mode 1 — Keyboard Scroll
| Shortcut | Action |
|----------|--------|
| `Right Ctrl + Up Arrow` | Scroll up |
| `Right Ctrl + Down Arrow` | Scroll down |

- **Smooth scrolling** when keys are held down
- Key-repeat flooding protection (debounce)

### Mode 2 — Mouse Gesture & Extra Buttons
| Input | Action |
|-------|--------|
| **Mouse Button 4** (back) | Scroll up |
| **Mouse Button 5** (forward) | Scroll down |
| **Right-Click held + mouse movement** | Scroll (up/down) |

- Does not interfere with normal right-click usage
- Gesture threshold prevents accidental triggers

### System Tray
- Green icon = Active
- Red icon = Paused
- Right-click menu: Pause/Resume, Mode toggle, Exit

---

## Installation

### Requirements
- Python 3.8 or higher
- Windows 10/11

### Steps

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the application
python virtual_scroll.py
```

---

## Building an Executable

To create a standalone `.exe` file:

```bash
# Using the automated build script
build.bat

# Or manually
pyinstaller --onefile --noconsole --name VirtualScroll virtual_scroll.py
```

Output: `dist/VirtualScroll.exe`

---

## Adding to Windows Startup

1. Press `Win + R`
2. Type `shell:startup` and press Enter
3. Copy `VirtualScroll.exe` into the opened folder

The application will start automatically on every system boot.

---

## Configuration

You can customize the behavior by editing the constants at the top of `virtual_scroll.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `SCROLL_AMOUNT` | 3 | Lines to scroll per trigger |
| `SCROLL_INTERVAL` | 0.05s | Repeat interval when key is held |
| `DEBOUNCE_MS` | 50ms | Flooding protection duration |
| `GESTURE_THRESHOLD` | 5px | Gesture activation threshold |
| `GESTURE_SCROLL_RATIO` | 0.4 | Mouse movement to scroll ratio |

---

## Technical Details

- **Low resource usage:** ~15-20 MB RAM, negligible CPU
- **Zero input latency:** pynput listeners run in separate threads
- **Thread-safe:** All state changes are protected with locks
- **Graceful shutdown:** All listeners and threads are cleanly stopped on exit

---

## License

MIT License
