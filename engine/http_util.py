"""계산 서비스를 HTTP로 여는 공통 처리 (Vercel 파이썬 함수와 로컬 개발 서버가 같이 씀)."""
from __future__ import annotations

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler

import service

# 엔진은 작물표·가정 값을 모듈 전역에 두고, '답이 뒤집히는 조건' 계산은 작물 값을 잠깐 바꿨다 되돌린다.
# 한 프로세스에서 요청이 동시에 돌면 서로의 값을 읽을 수 있으므로 계산은 한 번에 하나씩만 한다.
LOCK = threading.Lock()


def run(name: str, body: bytes) -> tuple[int, dict]:
    fn = service.ROUTES.get(name)
    if fn is None:
        return 404, dict(error="없는 주소예요")
    try:
        d = json.loads(body.decode("utf-8")) if body else {}
        if not isinstance(d, dict):
            raise service.InputError("입력 형식이 맞지 않아요")
        with LOCK:
            return 200, fn(d)
    except service.InputError as e:
        return 400, dict(error=str(e))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, dict(error="입력 형식이 맞지 않아요 (UTF-8 JSON으로 보내 주세요)")
    except Exception:  # noqa: BLE001 — 화면에는 짧게, 서버 기록에는 자세히
        traceback.print_exc()
        return 500, dict(error="계산 중 문제가 생겼어요. 조건을 바꿔 다시 해 보세요")


def make_handler(name: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, data: dict):
            out = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self._send(*run(name, self.rfile.read(n) if n else b""))

        def do_GET(self):
            self._send(*run(name, b""))

    return Handler
