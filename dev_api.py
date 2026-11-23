"""로컬 개발용 계산 서버: python dev_api.py → http://127.0.0.1:8000/api/<이름>

배포(Vercel)에서는 api/*.py 가 같은 일을 한다. `pnpm dev`(또는 npm run dev)의 화면은
next.config.ts 의 rewrites 로 /api/* 요청을 이 서버로 넘긴다.
"""
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "engine"))
from http_util import make_handler  # noqa: E402
from service import ROUTES  # noqa: E402

HANDLERS = {name: make_handler(name) for name in ROUTES}


class Router(BaseHTTPRequestHandler):
    def _dispatch(self, method):
        name = self.path.split("?")[0].rstrip("/").removeprefix("/api/")
        cls = HANDLERS.get(name)
        if cls is None:
            self.send_error(404)
            return
        h = cls.__new__(cls)
        h.__dict__.update(self.__dict__)
        getattr(h, method)()

    def do_POST(self):
        self._dispatch("do_POST")

    def do_GET(self):
        self._dispatch("do_GET")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"계산 서버: http://127.0.0.1:{port}/api/calc")
    ThreadingHTTPServer(("127.0.0.1", port), Router).serve_forever()
