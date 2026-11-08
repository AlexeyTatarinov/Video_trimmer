# Video Trimmer

**Cut a small video in seconds, then forget about it.**

Big video editors come with a huge feature set, and every job starts as a project: you import media, build a timeline, learn where things are and why they behave the way they do. That is far too much when all you need is to cut a piece out of a short video. Video Trimmer was made for exactly that case: right-click a video, pick the parts you want to keep, save, done. No projects, no timeline, no effects, nothing to learn.

Created by [Oleksii Tatarinov](https://github.com/AlexeyTatarinov).

## Features

- **Open a video** with a button, by double-clicking it from the "Open with" menu, or straight from the right-click menu of any common video format (see [Installation](#installation)).
- **Pick the parts to keep** with a range slider. Dragging a handle shows the frame at that exact point, so you see precisely where the cut will be.
- **Several segments from one video.** "Add segment" creates a card for the current range. Cards can be reordered, edited (click a card), and deleted. Overlapping ranges and repeats are allowed.
- **Every segment is saved as its own file** (`name_part1`, `name_part2`, ...) next to your choice of folder.
- **Two cutting modes:**
  - **Fast** (default): no re-encoding, nearly instant; cut points snap to the nearest keyframes.
  - **Precise**: re-encodes, frame-accurate, slower.
- **Full-screen preview**: double-click the video. Move the mouse to the bottom edge for the segment controls, to the top edge for the exit and Export buttons. Esc leaves full screen, Space plays and pauses.
- **Sound, mute and volume** in the preview.
- **Light and dark glass-style themes**, interface in English, Russian and Ukrainian.
- **Settings** (gear button):
  - language and theme;
  - *Close the program automatically after export* (off by default);
  - *Move the original video to the Recycle Bin after a successful export* (on by default).

Nothing else. That is the point.

## Installation

1. Download `VideoTrimmer-Setup-<version>.exe` from the [Releases](https://github.com/AlexeyTatarinov/Video_trimmer/releases) page.
2. Run it and choose where to install. Administrator rights are not needed; the program is installed for your user account.
3. Keep the option **right-click menu and "Open with"** ticked (it is on by default). After that, right-clicking any video file (`.mp4 .m4v .mkv .mov .avi .webm .wmv .flv .mpg .mpeg .ts .mts .m2ts .3gp .ogv .vob .mxf`) offers **Trim with Video Trimmer**, and the program is listed under **Open with**. On Windows 11 the item may be under *Show more options*. The default program of your video files is not changed.

ffmpeg is bundled with the installer, so nothing else has to be installed and no internet connection is needed.

### Uninstall

Open *Settings → Apps → Installed apps*, find **Video Trimmer** and choose *Uninstall* (or use the *Uninstall Video Trimmer* shortcut in the Start menu). The uninstaller removes the program, its shortcuts and every right-click and "Open with" entry it added. Your videos are never touched. Small settings (theme, language) stay in the user registry hive and can be ignored.

## Usage

1. Open a video (button, right-click menu, or "Open with").
2. Move the two handles of the range slider, or type exact times in the Start and End fields. "Start here" and "End here" take the current playback position.
3. Press **Add segment**. Repeat for every part you want.
4. Choose **Fast** or **Precise**, press **Save** and pick an output folder.
5. If *Move the original video to the Recycle Bin* is on (default), the original goes to the Recycle Bin after all files were saved successfully. It is never removed if anything failed, and you can restore it from the Recycle Bin.

Tip: in fast mode the saved clips can start slightly earlier than the chosen point because they begin at a keyframe. Use Precise when you need exact cuts.

## Running from source

Requirements: Python 3.10+, ffmpeg and ffprobe in `PATH`, and `pip install -r requirements.txt`.

- Windows without commands: double-click `run.bat` (downloads a local ffmpeg if missing, sets up a virtual environment, starts the GUI; Python 3 must be installed).
- GUI: `python -m video_trimmer [VIDEO]` with `PYTHONPATH=src`. An optional video path is opened at start.
- Self-check: `python -m video_trimmer --selftest`.
- Command line, one joined file: `python -m video_trimmer.cli INPUT OUTPUT --range 10-20 --range 0:30-0:45 --mode fast`
- Command line, one file per range (overlaps allowed): `python -m video_trimmer.cli INPUT OUTPUT_FOLDER --separate --range 10-20 --range 15-30`

If `run.bat` cannot download ffmpeg, download `ffmpeg-master-latest-win64-gpl.zip` from the BtbN FFmpeg-Builds releases on GitHub, unpack it and copy the `bin` folder to `tools\ffmpeg\bin` next to `run.bat`.

## Development

- Tests: `QT_QPA_PLATFORM=offscreen VIDEO_TRIMMER_NO_AUDIO=1 python -m pytest -q`
- The specification is in `spec.md`.
- The app icon is original artwork, generated by `python scripts/make_icon.py` into `src/video_trimmer/assets/`.
- The installer and release are built by GitHub Actions (`.github/workflows/release.yml`) when a `v*` tag is pushed: PyInstaller build, Inno Setup installer, automatic install/uninstall check.

## License and third-party software

Video Trimmer is released under the MIT license (see `LICENSE`).

The installer bundles a GPL build of [FFmpeg](https://ffmpeg.org/) (from the BtbN FFmpeg-Builds project) and uses Qt for Python (PySide6, LGPL) and send2trash. Licenses and source links are listed in `THIRD_PARTY_NOTICES.md`. FFmpeg is run as a separate program and is not linked into Video Trimmer.
