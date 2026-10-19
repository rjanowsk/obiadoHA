"""Load the portable client without importing Home Assistant on Windows.

The Linux CI additionally runs the real Home Assistant integration tests.
"""

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if importlib.util.find_spec("homeassistant") is None:
    package = types.ModuleType("custom_components.obiado")
    package.__path__ = [str(ROOT / "custom_components" / "obiado")]
    sys.modules["custom_components.obiado"] = package
