"""
Allow `python scripts/<name>.py` to import packages from the project root.

Import this module first in every script under scripts/.
"""

from __future__ import annotations

import sys
from pathlib import Path


def setup(caller_file: str | Path) -> Path:
    """Insert the project root into sys.path if needed."""
    root = Path(caller_file).resolve().parent.parent
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
