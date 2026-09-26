#!/usr/bin/env python3
"""Capture a small, explicit set of public source URLs for Phase 0 discovery.

Uses curl because urllib requests behaved differently against the source during
discovery. No recursive crawling; one request at a time, no automatic retries.
"""
import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "discovery"


def capture(name, url):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError("name must be a lowercase filesystem-safe identifier")
    host = urlparse(url).hostname or ""
    if urlparse(url).scheme != "https" or not (
        host in {"indiacode.gov.in", "indiacode.nic.in"}
        or host.endswith(".indiacode.gov.in")
        or host.endswith(".indiacode.nic.in")
    ):
        raise ValueError("only explicit HTTPS India Code source URLs are supported")
    DEST.mkdir(parents=True, exist_ok=True)
    body = DEST / (name + ".body")
    meta = DEST / (name + ".json")
    if body.exists() or meta.exists():
        raise FileExistsError(f"capture {name} already exists; use a new name")
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run([
        "curl", "--silent", "--show-error", "--location", "--max-redirs", "4",
        "--proto", "=https", "--proto-redir", "=https", "--max-time", "40",
        "--connect-timeout", "15", "--max-filesize", "52428800",
        "--user-agent", "LawIndex-Discovery/0.1 (bounded public-source inspection)",
        "--output", str(body), "--write-out", "%{json}", url,
    ], capture_output=True, text=True)
    info = json.loads(result.stdout) if result.stdout.strip() else {}
    raw = body.read_bytes() if body.exists() else b""
    record = {
        "requested_url": url, "effective_url": info.get("url_effective"),
        "fetched_at_utc": started, "http_status": info.get("http_code"),
        "content_type": info.get("content_type"), "curl_exit_code": result.returncode,
        "error": result.stderr.strip() or None,
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "body_path": str(body.relative_to(ROOT)) if body.exists() else None,
        "elapsed_seconds": info.get("time_total"),
        "note": "HTTP success alone does not establish valid source content; inspect body.",
    }
    meta.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"name": name, "status": record["http_status"], "bytes": len(raw),
                      "type": record["content_type"], "error": record["error"]}), flush=True)
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pairs", nargs="+", help="name=URL (quote URLs in the shell)")
    args = parser.parse_args()
    for index, pair in enumerate(args.pairs):
        if index:
            time.sleep(2)
        capture(*pair.split("=", 1))
