"""Entry point: ``python -m video_trimmer [--selftest] [VIDEO]``."""
from __future__ import annotations

import argparse
import sys


def parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="video_trimmer", description="Video Trimmer: instant video trimming.")
    ap.add_argument("path", nargs="?", default=None, help="video file to open right after start")
    ap.add_argument("--selftest", action="store_true",
                    help="check ffmpeg, ffprobe, the icon and the window without showing it; "
                         "prints SELFTEST OK and exits 0, otherwise exits 1")
    ap.add_argument("--selftest-out", default=None, metavar="FILE",
                    help="with --selftest: also write the result line to FILE (windowed builds have no console)")
    ap.add_argument("--version", action="version", version=_version_text())
    args, _unknown = ap.parse_known_args(argv)
    return args


def _version_text() -> str:
    from video_trimmer import __version__
    return f"Video Trimmer {__version__}"


def main(argv: "list[str] | None" = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0] if sys.argv else "video_trimmer"])

    if args.selftest:
        from video_trimmer import selftest
        ok, message = selftest.run()
        return selftest.report(ok, message, args.selftest_out)

    from video_trimmer import icon
    from video_trimmer.ui.main_window import MainWindow

    icon.install(app)
    window = MainWindow()
    window.show()
    if args.path:
        # after the window is up: a bad path shows an error box over a running program
        QTimer.singleShot(0, lambda: window.open_startup_path(args.path))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
