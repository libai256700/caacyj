from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[7] / "code" / "develop" / "yunjikeji" / "dist" / "build" / "h5"


class H5Handler(SimpleHTTPRequestHandler):
    def translate_path(self, request_path: str) -> str:
        path = unquote(urlparse(request_path).path)
        if path == "/yunjikeji" or path == "/yunjikeji/":
            return str(ROOT / "index.html")
        if path.startswith("/yunjikeji/"):
            path = path[len("/yunjikeji/") :]
        target = (ROOT / path).resolve()
        if ROOT not in target.parents and target != ROOT:
            return str(ROOT / "index.html")
        return str(target if target.exists() else ROOT / "index.html")


ThreadingHTTPServer(("127.0.0.1", 5173), H5Handler).serve_forever()
