"""Loopback-only development API; run with python3 -m lawindex.server."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .search import ROOT, Snapshot, Unavailable
from .retrieval import SearchFilters
from .coverage import build_coverage


def make_server(root: Path = ROOT, port: int = 8000, vector_backend=None):
    root = Path(root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Query traces are returned on demand, not written to logs.

        def respond(self, status, payload, content_type="application/json; charset=utf-8"):
            if not isinstance(payload, bytes):
                payload = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if urlsplit("http://" + self.headers.get("Host", "")).hostname not in ("localhost", "127.0.0.1"):
                self.respond(403, {"error": {"code": "local_only", "message": "Use localhost or 127.0.0.1."}})
                return
            parsed = urlsplit(self.path)
            path = unquote(parsed.path)
            try:
                if path.startswith("/api/"):
                    if path == "/api/health":
                        self.respond(200, {"status": "ok", "scope": "local development"})
                        return
                    snapshot = Snapshot(root)
                    if path == "/api/inventory":
                        try:
                            report = build_coverage(root, snapshot)
                        except (OSError, ValueError, KeyError, TypeError) as error:
                            raise Unavailable("Phase 3 inventory is unavailable or invalid.") from error
                        self.respond(200, report)
                        return
                    if path == "/api/corpus":
                        self.respond(200, snapshot.corpus())
                        return
                    if path == "/api/search":
                        params = parse_qs(parsed.query, keep_blank_values=True)
                        if set(params) - {"q", "limit", "act", "year", "ministry", "document_type", "mode"} or any(len(v) != 1 for v in params.values()):
                            raise ValueError("Use each search parameter at most once: q, limit, act, year, ministry, document_type, mode.")
                        filters = SearchFilters(**{k: params[k][0] for k in ("act", "year", "ministry", "document_type") if k in params})
                        result = snapshot.search(params.get("q", [""])[0], int(params.get("limit", ["10"])[0]), filters=filters,
                                                 mode=params.get("mode", [None])[0], vector_backend=vector_backend)
                        self.respond(200, result)
                        return
                    if path.startswith("/api/provisions/"):
                        key = path.removeprefix("/api/provisions/")
                        if key in snapshot.records:
                            self.respond(200, {"provision": snapshot.records[key], "navigation": snapshot.navigation(key),
                                               "corpus": snapshot.corpus()})
                            return
                    if path.startswith("/api/sources/") and path.endswith(".pdf"):
                        key = path.removeprefix("/api/sources/").removesuffix(".pdf")
                        if key in snapshot.pdfs:
                            self.respond(200, snapshot.pdfs[key], "application/pdf")
                            return
                else:
                    web = (root / "web").resolve()
                    target = (web / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
                    if (target.is_relative_to(web) and target.is_file()
                            and target.suffix in {".html", ".css", ".js", ".svg", ".ico"}):
                        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                        self.respond(200, target.read_bytes(), content_type)
                        return
                self.respond(404, {"error": {"code": "not_found", "message": "No currently admitted provision or resource at this address."}})
            except ValueError as error:
                self.respond(400, {"error": {"code": "invalid_query", "message": str(error)}})
            except Unavailable as error:
                self.respond(503, {"error": {"code": "data_unavailable", "message": str(error)}})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--vectors", action="store_true",
                        help="load the local embedding model and vector index so mode=vector and mode=hybrid work "
                             "(run with .venv/bin/python)")
    args = parser.parse_args()
    backend = None
    if args.vectors:
        from .embedding import VectorBackend
        backend = VectorBackend.load(ROOT)
    server = make_server(port=args.port, vector_backend=backend)
    print(f"Local LawIndex API: http://127.0.0.1:{server.server_port}/api/corpus", flush=True)
    print("UI files will be served from web/ when implemented. Ctrl+C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
