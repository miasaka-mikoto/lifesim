"""Pytest bootstrap for the source checkout.

The packaged application may install ``lifesim`` normally.  Keeping this
small path bootstrap lets the same tests run directly from a fresh checkout
without requiring an editable install first.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

