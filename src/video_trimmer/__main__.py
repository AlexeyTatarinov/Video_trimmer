"""Entry point: ``python -m video_trimmer``."""
from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from video_trimmer.ui.main_window import MainWindow

    from video_trimmer import icon

    app = QApplication(sys.argv)
    icon.install(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
