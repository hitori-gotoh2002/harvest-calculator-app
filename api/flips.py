"""POST /api/flips — engine/service.py 의 flips() (Vercel 파이썬 함수)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
from http_util import make_handler  # noqa: E402

_Base = make_handler("flips")


class handler(_Base):  # Vercel 은 파일 맨 위에 정의된 handler 클래스를 찾는다
    pass
