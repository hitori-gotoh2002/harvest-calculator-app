"""POST /api/farm — engine/service.py 의 farm() (Vercel 파이썬 함수)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
from http_util import make_handler  # noqa: E402

handler = make_handler("farm")
