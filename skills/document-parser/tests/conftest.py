import sys
from pathlib import Path


_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
  sys.path.insert(0, str(_SKILL_ROOT))
