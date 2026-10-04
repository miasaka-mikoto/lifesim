"""PyInstaller-friendly executable entry point for LifeSim.

``lifesim/__main__.py`` intentionally uses a package-relative import for
``python -m lifesim``.  PyInstaller executes a script as ``__main__`` instead
of importing it as a package, so this tiny absolute-import shim keeps the
Windows build working while reusing the same CLI.
"""

from lifesim.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

