"""Allow ``python -m lifesim`` to launch the CLI."""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())

