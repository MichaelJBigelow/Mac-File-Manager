# Mac File Manager

A small macOS app, written in Python with Tkinter, that helps free up disk space.

- **Duplicate Files** finds files with the same contents in a folder you choose, whatever
  their names are. You can then reveal them in Finder or move the extra copies to the Trash.
- **Developer Leftovers** finds caches, logs, old versions, uninstalled apps' data and
  project build folders left by **Android Studio**, **Visual Studio Code**, **Gradle** and
  **Unity**, and shows how much space each one uses.

Nothing is ever deleted outright. Items you remove go to the Trash, so you can put them back
until you empty it.

## Requirements

- macOS 11 or later. Moving items to the Trash uses `/usr/bin/trash` on macOS 15 and later,
  and asks Finder on older versions (macOS then asks once for permission to control Finder).
- Python 3.9 or later with Tkinter. Any of these works:
  - Python from [python.org](https://www.python.org/downloads/macos/) (includes Tkinter)
  - Homebrew: `brew install python python-tk`
  - The Python that comes with the Xcode Command Line Tools (`/usr/bin/python3`). Its Tk is
    old, so the two above look better.

There are no other dependencies.

## Run it

Double-click **Mac File Manager.app** in the repository folder. The app opens without a
Terminal window.

The app is a small launcher that runs the code in `src`, so keep it in the repository folder.
It looks for Python in `/opt/homebrew/bin`, `/usr/local/bin`, the python.org framework, and
then `/usr/bin`. To use a different Python, run the launcher from a terminal with `MFM_PYTHON`
set:

```bash
MFM_PYTHON=/path/to/python3 "./Mac File Manager.app/Contents/MacOS/Mac File Manager"
```

If the app doesn't open, read `~/Library/Logs/Mac File Manager/launcher.log`.

If you downloaded the repository as a ZIP instead of cloning it, macOS quarantines the app and
won't open it from the ZIP's folder. Clone with git, or remove the quarantine flag:

```bash
xattr -dr com.apple.quarantine "Mac File Manager.app"
```

To run it from a terminal instead:

```bash
PYTHONPATH=src python3 -m mac_file_manager
```

While it runs, the Dock and menu bar show it as "Python", because it runs on the Python
installation's own app.

## What the Developer Leftovers tab finds

| Tool | Where it looks |
| --- | --- |
| Android Studio | Per-version settings, caches and logs in `~/Library/…/Google/AndroidStudio*` (versions older than the newest are marked *Old version*), data from Android Studio 4.0 and earlier, `~/.android` and the SDK in `~/Library/Android/sdk` |
| Visual Studio Code | Caches and logs in `~/Library/Application Support/Code`, `~/Library/Caches/com.microsoft.VSCode*`, extensions, and workspace data for project folders that no longer exist. VS Code Insiders too. |
| Gradle | `~/.gradle`: caches for each Gradle version, shared caches in older formats, wrapper downloads, daemon logs and downloaded JDKs |
| Unity | `~/Library/Unity` (package cache, Asset Store downloads), Unity logs and caches, and Unity Hub caches |

If you choose a **Projects folder**, it also lists build folders inside the projects there:
`build`, `.gradle`, `.kotlin` and `.cxx` in Gradle and Android projects, `Library`, `Temp`,
`obj` and `Logs` in Unity projects, and `.vscode-test` in VS Code extension projects.

Each item has a type:

- **Cache**, **Logs**, **Build output**: re-created automatically when needed.
- **Old version**: data for a version older than the newest one on this Mac.
- **Orphaned**: data for a project that no longer exists.
- **App not installed**: data from an app that isn't in `/Applications` or `~/Applications`
  and that Spotlight can't find anywhere else.
- **In use**: still used by an installed tool, such as the Android SDK. Hidden unless you
  turn on *Show items still in use*.

## Project layout

```
Mac File Manager.app/      Launcher (a shell script inside a macOS app bundle)
src/mac_file_manager/
    duplicates.py          Duplicate search (size, then a partial hash, then a full SHA-256)
    leftovers.py           Where each tool keeps its data and how it is classified
    fsutils.py             Sizes, Reveal in Finder, Move to Trash
    app.py                 Main window
    ui/                    The two tabs and shared widgets
tests/                     Unit tests
```

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
