# Video Trimmer

Instant video trimming: open a video, pick the parts to keep with the slider, save.

## Requirements
- Python 3.10+
- ffmpeg and ffprobe available in PATH (Windows: `winget install Gyan.FFmpeg`)
- `pip install -r requirements.txt` (PySide6)

## Run
- Windows, no commands: double-click `run.bat` (downloads a local ffmpeg if missing, sets up dependencies, then starts the GUI; Python 3 must be installed).
- GUI: `python -m video_trimmer` (from the `src` folder, or set `PYTHONPATH=src`)
- CLI (one joined file): `python -m video_trimmer.cli INPUT OUTPUT --range 10-20 --range 0:30-0:45 --mode fast`
- CLI (separate file per range, overlaps allowed): `python -m video_trimmer.cli INPUT OUTPUT_FOLDER --separate --range 10-20 --range 15-30`

## Modes
- fast (default): no re-encoding, instant; cut points snap to keyframes.
- precise: re-encodes, frame-accurate, slower.

## Tests
`QT_QPA_PLATFORM=offscreen python -m pytest -q`

See `spec.md` (Russian) for the specification.

## v0.2
- Each segment is saved as a separate file (`name_part1`, `name_part2`, ...); overlaps and duplicates are allowed.
- Preview jumps to the frame of the handle being dragged; audio, mute and volume.
- Light and dark glass themes (toggle in the window).

## ffmpeg on Windows (manual)
If `run.bat` cannot download ffmpeg, download `ffmpeg-master-latest-win64-gpl.zip` from the BtbN FFmpeg-Builds releases on GitHub, unpack it and copy the `bin` folder to `tools\ffmpeg\bin` next to `run.bat` (the file `tools\ffmpeg\bin\ffmpeg.exe` must exist).

## Icon
The app icon (original design) lives in `src/video_trimmer/assets/` (`icon.png`, `icon.ico`) and is installed for every window at startup. To regenerate it: `python scripts/make_icon.py`.
