# Third-party notices

Video Trimmer (see `LICENSE` for its own license) uses and redistributes the
components below. The Windows installer bundles Python, Qt/PySide6 and an
ffmpeg build.

## Qt and PySide6 (LGPL-3.0)

The user interface and video preview use PySide6 (Qt for Python) and Qt 6,
licensed under the GNU Lesser General Public License v3 (LGPLv3).
The Qt libraries are shipped as separate, replaceable DLLs in the application
folder, so you can replace them with your own build of the same Qt version.

- Qt for Python: https://doc.qt.io/qtforpython-6/
- Qt source code: https://download.qt.io/ and https://code.qt.io/
- LGPLv3 text: https://www.gnu.org/licenses/lgpl-3.0.html
- Qt licensing: https://www.qt.io/licensing/

Qt Multimedia ships its own FFmpeg libraries (LGPL, DLLs such as
`avcodec-*.dll` inside the PySide6 folder) for video playback in the preview.
Their source is available from https://ffmpeg.org/ and https://download.qt.io/.

## FFmpeg (GPL build)

The installer bundles `ffmpeg.exe` and `ffprobe.exe` in the `ffmpeg` folder
next to `VideoTrimmer.exe`. Video Trimmer runs them as separate programs
(command-line processes); it does not link against them.

The binaries come from the automated Windows builds by BtbN, build variant
`win64-gpl` (`ffmpeg-master-latest-win64-gpl`). This build is configured with
`--enable-gpl` (and `--enable-version3`), so these binaries are licensed under
the GNU General Public License (GPL), version 3 or later. The exact license
text is in `ffmpeg\LICENSE.txt` in the application folder.

- FFmpeg project: https://ffmpeg.org/
- Build scripts and releases (BtbN): https://github.com/BtbN/FFmpeg-Builds
- FFmpeg source code: https://git.ffmpeg.org/ffmpeg.git
  (mirror: https://github.com/FFmpeg/FFmpeg). Run `ffmpeg -version` to see the
  exact version and configuration of the bundled binary.
- GPL text: https://www.gnu.org/licenses/gpl-3.0.html
- FFmpeg legal information: https://ffmpeg.org/legal.html

The source code of the bundled ffmpeg is available at the links above. If you
cannot obtain it there, open an issue in this project's repository.

## Send2Trash (BSD-3-Clause)

Used to move the original video to the Recycle Bin.
Copyright (c) Virgil Dupras and contributors.
https://github.com/arsenetar/send2trash

## Python (PSF License)

The installer contains the CPython runtime (via PyInstaller).
Copyright (c) Python Software Foundation.
https://docs.python.org/3/license.html

## PyInstaller (build tool)

The executable is built with PyInstaller (GPL-2.0-or-later with a special
exception that permits distributing the built program under any license).
https://pyinstaller.org/

## Inno Setup (build tool)

The installer is created with Inno Setup. https://jrsoftware.org/isinfo.php
