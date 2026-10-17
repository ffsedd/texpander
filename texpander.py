#!/usr/bin/env python3
"""Select and paste text snippets into the active X11 window.

Dependencies: rofi or zenity, xsel, xdotool
Environment:
    TEXPANDER_DIR       Snippet directory (default: ~/.texpander)
    TEXPANDER_SELECTOR  auto, rofi, zenity (default: auto)
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(os.environ.get("TEXPANDER_DIR", "~/.texpander")).expanduser()
SELECTOR = os.environ.get("TEXPANDER_SELECTOR", "auto")


def run(*args: str, input_data: bytes | None = None) -> bytes:
    """Execute a command and return its stdout."""
    result = subprocess.run(
        args,
        input=input_data,
        capture_output=True,
        check=True,
    )
    return result.stdout


def check_dependencies() -> str:
    """Validate X11 dependencies and select the GUI backend."""
    if not os.environ.get("DISPLAY"):
        raise RuntimeError("An X11 session is required")

    for cmd in ("xsel", "xdotool"):
        if not shutil.which(cmd):
            raise RuntimeError(f"Missing dependency: {cmd}")

    if SELECTOR == "auto":
        for cmd in ("rofi", "zenity"):
            if shutil.which(cmd):
                return cmd

        raise RuntimeError("Install rofi or zenity")

    if SELECTOR not in ("rofi", "zenity"):
        raise ValueError(f"Invalid selector: {SELECTOR}")

    if not shutil.which(SELECTOR):
        raise RuntimeError(f"Missing selector: {SELECTOR}")

    return SELECTOR


def find_snippets(base_dir: Path) -> list[Path]:
    """Discover files recursively, following symlinks without directory loops."""
    base_dir.mkdir(parents=True, exist_ok=True)

    snippets: list[Path] = []
    visited: set[tuple[int, int]] = set()

    def onerror(error: OSError) -> None:
        raise error

    for root, dirs, files in os.walk(base_dir, followlinks=True, onerror=onerror):
        directory = Path(root)
        stat = directory.stat()
        identity = (stat.st_dev, stat.st_ino)

        if identity in visited:
            dirs.clear()
            continue

        visited.add(identity)

        for name in files:
            path = directory / name

            if path.is_file():
                snippets.append(path)

    return sorted(
        snippets,
        key=lambda path: str(path.relative_to(base_dir)).casefold(),
    )


def get_target_window() -> str:
    """Get the currently focused X11 window ID."""
    return run("xdotool", "getwindowfocus").decode().strip()


def select_rofi(snippets: list[Path], base_dir: Path) -> Path | None:
    """Select a snippet using Rofi fuzzy search."""
    names = [str(path.relative_to(base_dir)) for path in snippets]
    data = ("\n".join(names) + "\n").encode("utf-8")

    result = subprocess.run(
        [
            "rofi",
            "-dmenu",
            "-i",
            "-no-custom",
            "-format",
            "i",
            "-p",
            "Snippet",
            "-l",
            "15",
        ],
        input=data,
        capture_output=True,
        check=False,
    )

    if result.returncode == 1:
        return None

    if result.returncode != 0:
        raise RuntimeError(f"Rofi failed: {result.stderr.decode(errors='replace')}")

    index = int(result.stdout.strip())
    return snippets[index]


def select_zenity(snippets: list[Path], base_dir: Path) -> Path | None:
    """Select a snippet using a Zenity list dialog."""
    names = [str(path.relative_to(base_dir)) for path in snippets]

    result = subprocess.run(
        [
            "zenity",
            "--list",
            "--title=Texpander",
            "--width=450",
            "--height=500",
            "--column=Snippet",
        ],
        input=("\n".join(names) + "\n").encode("utf-8"),
        capture_output=True,
        check=False,
    )

    if result.returncode == 1:
        return None

    if result.returncode != 0:
        raise RuntimeError(f"Zenity failed: {result.stderr.decode(errors='replace')}")

    name = result.stdout.decode("utf-8").rstrip("\n")

    return next(
        (path for path in snippets if str(path.relative_to(base_dir)) == name),
        None,
    )


def select_snippet(snippets: list[Path], base_dir: Path, selector: str) -> Path | None:
    """Select a snippet with the configured GUI."""
    if any("\n" in str(path.relative_to(base_dir)) for path in snippets):
        raise ValueError("Snippet filenames containing newlines are unsupported")

    if selector == "rofi":
        return select_rofi(snippets, base_dir)

    return select_zenity(snippets, base_dir)


def paste_snippet(path: Path, window: str) -> None:
    """Copy a snippet to the clipboard and paste into the target window."""
    if not path.is_file():
        raise FileNotFoundError(path)

    content = path.read_bytes()

    # Set clipboard without modifying the snippet contents.
    run("xsel", "--clipboard", "--input", input_data=content)

    # Return focus to the application active before the selector.
    run("xdotool", "windowactivate", "--sync", window)

    time.sleep(0.15)

    # Paste using Ctrl+V, releasing any held shortcut modifiers.
    run("xdotool", "key", "--clearmodifiers", "ctrl+v")

    # The snippet remains in the clipboard.


def main() -> int:
    """Run the snippet-selection and paste workflow."""
    selector = check_dependencies()
    window = get_target_window()
    snippets = find_snippets(BASE_DIR)

    if not snippets:
        raise RuntimeError(f"No snippets found in {BASE_DIR}")

    snippet = select_snippet(snippets, BASE_DIR, selector)

    if snippet is None:
        return 0

    paste_snippet(snippet, window)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"texpander: {exc}", file=sys.stderr)
        sys.exit(1)
