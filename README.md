# VirtualScroll

**A lightweight Windows desktop utility that simulates mouse wheel scrolling through customizable keyboard shortcuts and mouse gestures as a workaround for a broken scroll wheel.**

Runs silently in the **Windows System Tray** upon startup without cluttering your desktop with windows. Clicking the tray icon opens a modern graphical settings interface (GUI) where you can customize your preferred hotkeys and scroll parameters.

---

## 🌟 Features

### 🖥️ Settings GUI & System Tray Integration
- **Silent Startup**: Starts directly in the system tray upon launch or Windows boot without interrupting your work.
- **System Tray Interaction**: Left/double clicking the tray icon or selecting *"Open Settings / GUI"* from the context menu opens the settings window.
- **Customizable Hotkeys**:
  - **Modifier Key**: Right Ctrl, Left Ctrl, Right Alt, Left Alt, Right Shift, Left Shift, Either Ctrl/Alt/Shift, or None (Arrow keys only).
  - **Direction Keys**: Up / Down Arrow Keys, Page Up / Page Down, W / S, I / K.
- **Scroll Step & Speed**: Customize lines scrolled per trigger (1 - 20 lines).
- **Persistent Preferences**: Saves all your settings automatically to `config.json`.
- **Minimize to Tray**: Closing (X) the settings window withdraws it back to the system tray while keeping background scroll simulation active.

### ⌨️ Keyboard Scrolling (Mode 1)
- **Smooth scrolling** when shortcut keys are held down.
- Built-in debounce protection against key-repeat flooding.

### 🖱️ Mouse Gestures & Extra Buttons (Mode 2)
| Input | Action |
|-------|--------|
| **Mouse Button 4** (Back) | Scroll Up |
| **Mouse Button 5** (Forward) | Scroll Down |
| **Right-Click held + Vertical Drag** | Directional Scroll |

- Does not interfere with standard right-click functionality (passes through normally if no mouse movement is detected).

---

## 🚀 Installation & Usage

### Prerequisites
- Python 3.8 or higher
- Windows 10 / 11

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run application (starts silently in system tray)
python virtual_scroll.py
```

---

## 📦 Building Standalone Executable (.exe)

To compile a standalone `.exe` without console windows:

```bash
# Run the automated build script
build.bat
```

Output: `dist/VirtualScroll_App.exe`

---

## 🔄 Adding to Windows Startup

1. Press `Win + R`
2. Type `shell:startup` and press Enter
3. Copy `dist/VirtualScroll_App.exe` (or a shortcut to it) into the opened folder.

The application will now automatically launch in the background every time Windows boots.

---

## 📄 License

MIT License
