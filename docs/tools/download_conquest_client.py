#!/usr/bin/env python3
"""Download the Conquest Reborn client from a public Google Drive link (stdlib only)."""
import argparse
import hashlib
import http.cookiejar
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request

CHUNK = 8 * 1024 * 1024


def file_id(url):
    m = re.search(r"/d/([A-Za-z0-9_-]{20,})", url) or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url)
    if not m:
        raise SystemExit("Could not find the Google Drive file id in the URL.")
    return m.group(1)


def open_url(opener, url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    return opener.open(req, timeout=120)


def prepare(opener, fid):
    base = "https://drive.google.com/uc?export=download&id=" + fid
    resp = open_url(opener, base)
    ctype = resp.headers.get("Content-Type", "")
    if "text/html" in ctype:
        html = resp.read().decode("utf-8", "replace")
        confirm = re.search(r'name="confirm"\s+value="([^"]+)"', html)
        uuid = re.search(r'name="uuid"\s+value="([^"]+)"', html)
        action = re.search(r'action="([^"]+)"', html)
        if confirm and action:
            action = action.group(1).replace("&amp;", "&")
            params = {"id": fid, "export": "download", "confirm": confirm.group(1)}
            if uuid:
                params["uuid"] = uuid.group(1)
            return action + ("&" if "?" in action else "?") + urllib.parse.urlencode(params)
        raise SystemExit("Drive returned HTML without a confirm form; make sure the file is shared with Anyone with the link.")
    return base


def download(opener, url, out):
    part = out + ".part"
    have = os.path.getsize(part) if os.path.exists(part) else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    try:
        resp = open_url(opener, url, headers)
    except urllib.error.HTTPError as e:
        if e.code == 416:
            os.replace(part, out)
            print("Part file already complete.")
            return
        raise
    status = resp.status
    if status not in (200, 206):
        raise SystemExit(f"Download failed: HTTP {status}")
    ctype = resp.headers.get("Content-Type", "")
    if "text/html" in ctype:
        html = resp.read(8192).decode("utf-8", "replace")
        title = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        raise SystemExit("Drive returned an HTML error page instead of the file: " + (title.group(1).strip() if title else html[:300]))
    length = int(resp.headers.get("Content-Length", "0") or 0)
    total = have + length
    mode = "ab" if have and status == 206 else "wb"
    if mode == "wb":
        have = 0
    seen = have
    started = time.time()
    with open(part, mode) as f:
        while True:
            chunk = resp.read(CHUNK)
            if not chunk:
                break
            f.write(chunk)
            seen += len(chunk)
            elapsed = max(1e-6, time.time() - started)
            speed = (seen - have) / elapsed / (1024 * 1024)
            pct = f"{seen * 100 / total:.2f}%" if total else "?"
            print(f"\r{seen:,} / {total:,} bytes ({pct}) {speed:.1f} MB/s", end="", flush=True)
    print()
    os.replace(part, out)


def verify(path, expected):
    if not expected:
        return
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(block)
    digest = h.hexdigest()
    if digest.lower() != expected.lower():
        raise SystemExit(f"SHA-256 mismatch!\n  expected {expected}\n  actual   {digest}")
    print("SHA-256 OK:", digest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", default="ConquestReborn-Client.7z")
    ap.add_argument("--sha256", default="")
    ap.add_argument("--extract-to", default="")
    ap.add_argument("--sevenzip", default="7zr.exe")
    a = ap.parse_args()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    fid = file_id(a.url)
    print("Resolving Drive link", fid)
    url = prepare(opener, fid)
    print("Direct download:", url)
    download(opener, url, a.out)
    verify(a.out, a.sha256)
    if a.extract_to:
        os.makedirs(a.extract_to, exist_ok=True)
        subprocess.run([a.sevenzip, "x", "-y", f"-o{a.extract_to}", a.out], check=True)


if __name__ == "__main__":
    main()
