# Video Trimmer

Instant video trimming: open a video, pick the parts to keep with the slider, save.

## Requirements
- Python 3.10+
- ffmpeg and ffprobe available in PATH (Windows: `winget install Gyan.FFmpeg`)
- `pip install -r requirements.txt` (PySide6)

## Run
- Windows, no commands: double-click `run.bat` (installs Python and ffmpeg via winget if missing, then starts the GUI).
- GUI: `python -m video_trimmer` (from the `src` folder, or set `PYTHONPATH=src`)
- CLI: `python -m video_trimmer.cli INPUT OUTPUT --range 10-20 --range 0:30-0:45 --mode fast`

## Modes
- fast (default): no re-encoding, instant; cut points snap to keyframes.
- precise: re-encodes, frame-accurate, slower.

## Tests
`QT_QPA_PLATFORM=offscreen python -m pytest -q`

See `spec.md` (Russian) for the specification.
