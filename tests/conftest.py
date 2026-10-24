import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="inkloom-test-"))
os.environ["INKLOOM_DATA"] = str(_root)
os.environ["INKLOOM_DB"] = str(_root / "test.db")
