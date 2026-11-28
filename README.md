# Mac File Manager

A small macOS app, written in Python with Tkinter, that helps software engineers get back the
disk space their tools use up.

It is made mainly for developers. IDEs and build tools keep large amounts of cached data on a
Mac: per-version IDE caches and settings, dependency and build caches, downloaded SDKs and
toolchains, emulator images, logs, and build folders in every project. Much of it is left
behind when a tool updates to a new version or is uninstalled, and it can easily add up to
tens of gigabytes. macOS's own storage settings don't say which tool it belongs to or whether
it is safe to remove.

- **Developer Leftovers** finds the caches, logs, old versions, uninstalled apps' data and
  project build folders left by **Android Studio**, **Visual Studio Code**, **Gradle** and
  **Unity**. It shows how much space each item uses and what kind of data it is, so you can
  tell what is safe to remove.
- **Duplicate Files** finds files with the same contents in a folder you choose, whatever
  their names are. You can then reveal them in Finder or move the extra copies to the Trash.

Nothing is ever deleted outright. Items you remove go to the Trash, so you can put them back
until you empty it.

The interface follows Material Design 3, in light or dark to match your Mac's appearance when
the app opens.

## Requirements

- macOS 11 or later. Moving items to the Trash uses `/usr/bin/trash` on macOS 15 and later,
  and asks Finder on older versions (macOS then asks once for permission to control Finder).
- Python 3.9 or later with Tk 8.6 or later. Either of these works:
  - Python from [python.org](https://www.python.org/downloads/macos/) (includes Tk)
  - Homebrew: `brew install python python-tk`

  The Python that comes with the Xcode Command Line Tools (`/usr/bin/python3`) has Tk 8.5,
  which draws empty windows on current macOS, so it isn't supported.

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

To run it from a terminal instead (the Dock then shows it as "Python"):

```bash
PYTHONPATH=src python3 -m mac_file_manager
```

So that the Dock and menu bar show **Mac File Manager** and its icon rather than "Python", the
launcher copies the executable that Python runs GUI programs with into the app as
`Contents/MacOS/mfm-python` and signs the copy ad hoc (macOS stops a copy of a signed
executable from running otherwise). It does this on the first launch and again whenever that
Python changes. git ignores the copy. If the copy can't be made, the app still opens, shown as
"Python".

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
Mac File Manager.app/      Launcher (a shell script inside a macOS app bundle) and app icon
src/mac_file_manager/
    duplicates.py          Duplicate search (size, then a partial hash, then a full SHA-256)
    leftovers.py           Where each tool keeps its data and how it is classified
    fsutils.py             Sizes, Reveal in Finder, Move to Trash
    app.py                 Main window
    ui/theme.py            Material Design 3 colors, type and ttk styles
    ui/images.py           Draws the theme's rounded shapes and the app icon as PNG images
    ui/                    The two tabs and shared widgets
tools/make_icon.py         Rebuilds Contents/Resources/AppIcon.icns
tests/                     Unit tests
```

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
