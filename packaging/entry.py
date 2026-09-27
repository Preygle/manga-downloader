"""PyInstaller entry point for mangabinder.exe."""
import sys

from mangabinder.cli import main

if __name__ == "__main__":
    sys.exit(main())
