"""PyInstaller entry point (the package's own __main__ uses absolute imports)."""
import sys

from video_trimmer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
