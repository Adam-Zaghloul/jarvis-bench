"""JARVIS local server. Binds to 127.0.0.1 only. Python 3.9+ stdlib, no dependencies.

    python jarvis/server.py [--open] [--port 8765]
"""
import argparse
import json
import mimetypes
import os
import re
import socket
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain  # noqa: E402
import capture  # noqa: E402
import closeout  # noqa: E402
import backup  # noqa: E402
import routes  # noqa: E402
import store  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
HOST = "127.0.0.1"
BOOT_ID = uuid.uuid4().hex[:12]
_health = {"ok": None, "detail": "Checking Claude Code…"}
_health_lock = threading.Lock()

TEXT_VIEW_EXT = {".md", ".txt", ".csv", ".c", ".h", ".jsonl"}
RAW_TYPES = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg"}


def run_health():
    global _health
    h = brain.health_check()
    with _health_lock:
        _health = h


# ---------------------------------------------------------------- helpers for modes

def board_context_text():
    a = store.get_active()
    if not a:
        return ""
    entries = [e for e in store.read_log(store._today()) if e.get("serial") == a["serial"]]
    lines = ["Board context (active board, today's log only — do not mix with other boards):",
             "Board: %s serial %s" % (a["board_type"], a["serial"])]
    if not entries:
        lines.append("(no log entries yet today)")
    for e in entries:
        lines.append("- %s [%s] %s%s" % (e["ts"][11:], e.get("kind") or "note", e["text"],
                                        " (status: %s)" % e["status"] if e.get("status") else ""))
    return "\n".join(lines)


def latest_observation():
    a = store.get_active()
    if not a:
        return ""
    entries = [e for e in store.read_log(store._today()) if e.get("serial") == a["serial"]]
    for e in reversed(entries):
        if e.get("kind") == "observation":
            return e["text"]
    return entries[-1]["text"] if entries else ""


def seen_brain(query, lang):
    a = store.get_active()
    fast = store.fast_search(query, limit=30, exclude_serial=a["serial"] if a else None)
    pats = closeout.patterns_for_query(query)  # verified patterns, shown first
    if not fast["hits"]:
        return {"fast": fast, "patterns": pats, "summary": None, "resolved": [], "unresolved": [], "dropped": [],
                "note": "No keyword matches, so the brain was not called."}
    lines = ["Symptom: " + query, "", "Keyword-search hits (path:line | heading | meta | snippet):"]
    for h in fast["hits"]:
        m = h.get("meta") or {}
        lines.append("- %s:%s | %s | serial=%s date=%s status=%s | %s" % (
            h["path"], h["line"], h.get("heading", ""), m.get("serial", ""), m.get("date", ""),
            m.get("status", ""), h["snippet"]))
    ctx = "\n".join(lines)
    result = None
    for ev in brain.ask("seen", "Group these into past cases similar to the symptom and summarise the pattern.",
                        ctx, lang=lang):
        if ev["type"] == "error":
            return {"fast": fast, "error": ev}
        if ev["type"] == "done":
            result = ev
    data = (result or {}).get("data") or {}
    keep, dropped = [], []
    for c in data.get("cases") or []:
        if store.entry_exists(c.get("source_path"), c.get("source_line")):
            keep.append(c)
        else:
            dropped.append(c)
    store.cite("seen", paths=[c.get("source_path") for c in keep])
    return {"fast": fast, "patterns": pats, "summary": data.get("summary"),
            "resolved": [c for c in keep if c.get("resolved")],
            "unresolved": [c for c in keep if not c.get("resolved")],
            "dropped": dropped, "duration_s": (result or {}).get("duration_s")}


L10N = {
    "en": {"symptom": "Symptom", "meas": "Measurements", "act": "Actions", "result": "Result",
           "next": "Next step", "board": "Board", "slack": "Slack update", "jira": "Jira notes",
           "open": "Open items for tomorrow", "gaps": "Gap check", "noclose": "No closing status",
           "unplaced": "Entries not placed", "untraced": "Lines with no matching log timestamp",
           "none": "(none)"},
    "fr": {"symptom": "Symptôme", "meas": "Mesures", "act": "Actions", "result": "Résultat",
           "next": "Prochaine étape", "board": "Carte", "slack": "Mise à jour Slack", "jira": "Notes Jira",
           "open": "Points ouverts pour demain", "gaps": "Vérification des trous",
           "noclose": "Sans statut de fermeture", "unplaced": "Entrées non placées",
           "untraced": "Lignes sans horodatage correspondant", "none": "(aucun)"},
}


def _trace(ts, stamps):
    """Match a brain-supplied ts against real log timestamps. Returns the real ts or None."""
    ts = (ts or "").strip()
    if not ts:
        return None
    for s in stamps:
        if ts == s or ts == s[11:] or (len(ts) == 5 and s[11:16] == ts):
            return s
    return None


_CITE = re.compile(r"\s*\[\[([^\]\n]{1,300})\]\]")


def _plain_cites(obj):
    """Debrief text is pasted into Slack/Jira: turn any [[path#x]] markup into '(see path)'."""
    if isinstance(obj, str):
        return _CITE.sub(lambda m: " (see %s)" % m.group(1).split("#")[0], obj)
    if isinstance(obj, list):
        return [_plain_cites(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _plain_cites(v) for k, v in obj.items()}
    return obj


def debrief(date, lang):
    lang = lang if lang in L10N else "en"
    t = L10N[lang]
    entries = store.read_log(date)
    if not entries:
        return {"date": date, "empty": True, "note": "No log entries for %s." % date}
    stamps = [e["ts"] for e in entries]
    jsonl = "\n".join(json.dumps({k: e.get(k) for k in ("ts", "board_type", "serial", "kind", "text", "status")},
                                 ensure_ascii=False) for e in entries)
    ctx = "Date: %s\nLanguage: %s\nBench log (JSONL, one entry per line):\n%s" % (date, lang, jsonl)
    result = None
    for ev in brain.ask("debrief", "Write the end-of-shift debrief for this log.", ctx, lang=lang):
        if ev["type"] == "error":
            return {"date": date, "error": ev}
        if ev["type"] == "done":
            result = ev
    data = _plain_cites((result or {}).get("data") or {})

    untraced = []

    def line(item):
        item = item or {}
        text = (item.get("text") or "").strip()
        real = _trace(item.get("ts"), stamps)
        if not text or text == "(none logged)":
            return text or "(none logged)"
        if not real:
            untraced.append(item)
            return "[??:??:?? ⚠ not in log] %s" % text
        return "[%s] %s" % (real[11:], text)

    jira = []
    for b in data.get("boards") or []:
        out = ["*%s %s (%s)* — %s" % (t["board"], b.get("serial", ""), b.get("board_type", ""), b.get("status", ""))]
        out.append("%s: %s" % (t["symptom"], line(b.get("symptom"))))
        out.append(t["meas"] + ":")
        out += ["- " + line(m) for m in b.get("measurements") or []] or ["- " + t["none"]]
        out.append(t["act"] + ":")
        out += ["- " + line(m) for m in b.get("actions") or []] or ["- " + t["none"]]
        out.append("%s: %s" % (t["result"], line(b.get("result"))))
        out.append("%s: %s" % (t["next"], b.get("next_step", "")))
        jira.append({"serial": b.get("serial", ""), "text": "\n".join(out)})

    st = store.board_states(entries)
    no_close = [b for b in st.values() if b["status"] not in store.CLOSED]
    unplaced = list(data.get("unplaced") or [])
    for u in unplaced:
        u["traced"] = bool(_trace(u.get("ts"), stamps))
    slack = "\n".join(data.get("slack") or [])
    open_items = data.get("open_items") or []

    md = ["# Debrief — %s" % date, "", "## " + t["slack"], "", slack, "", "## " + t["jira"], ""]
    for j in jira:
        md += [j["text"], ""]
    md += ["## " + t["open"], ""] + ["- " + o for o in open_items] + [""]
    md += ["## " + t["gaps"], "", "### " + t["noclose"], ""]
    md += ["- %s %s (%s)" % (b["board_type"], b["serial"], b["status"] or "—") for b in no_close] or ["- " + t["none"]]
    md += ["", "### " + t["unplaced"], ""]
    md += ["- [%s] %s — %s" % (u.get("ts"), u.get("text"), u.get("reason")) for u in unplaced] or ["- " + t["none"]]
    md += ["", "### " + t["untraced"], ""]
    md += ["- [%s] %s" % (u.get("ts", ""), u.get("text", "")) for u in untraced] or ["- " + t["none"]]
    photos = {}
    for e in entries:
        for ph in e.get("photos") or []:
            photos.setdefault(e["serial"], []).append({"ts": e["ts"], "path": ph, "text": e.get("text", "")})
    if photos:
        md += ["", "## Photos", ""]
        for serial, ps in photos.items():
            md.append("- %s: " % serial + ", ".join("[%s] %s" % (p["ts"][11:], p["path"]) for p in ps))
    md.append("")
    store.DEBRIEF_DIR.mkdir(parents=True, exist_ok=True)
    out_path = store.DEBRIEF_DIR / ("%s.md" % date)
    out_path.write_text("\n".join(md), encoding="utf-8")
    return {"date": date, "lang": lang, "slack": slack, "jira": jira, "open_items": open_items,
            "gaps": {"no_close": no_close, "unplaced": unplaced, "untraced": untraced},
            "photos": photos,
            "saved": str(out_path),
            "duration_s": (result or {}).get("duration_s"), "entries": len(entries)}


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "JARVIS/1"
    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("JARVIS_HTTP_LOG"):
            sys.stderr.write("%s\n" % (fmt % args))

    # -- guards
    def _host_ok(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; "
                         "frame-src 'self'; object-src 'self'; connect-src 'self'")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code, msg, hint=""):
        self._send(code, {"error": msg, "hint": hint})

    # Photos arrive as base64 data URLs: 8 MB of image ≈ 10.7 MB of base64. Everything else stays small.
    BODY_MAX = {"/api/photo": 11_500_000}

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        limit = self.BODY_MAX.get(urlparse(self.path).path, 200000)
        if n > limit:
            self.close_connection = True   # don't read (or keep alive) an oversized upload
            raise ValueError("Image too large (8 MB max)." if limit > 200000 else "Request too large.")
        raw = self.rfile.read(n) if n else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    # -- GET
    def do_GET(self):
        if not self._host_ok():
            return self._err(403, "Bad host.")
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path in routes.GET:
                code, payload = routes.GET[u.path](q, self)
                return self._send(code, payload)
            if u.path == "/":
                return self._static("index.html")
            if u.path.startswith("/static/"):
                return self._static(u.path[len("/static/"):])
            if u.path == "/api/status":
                s = store.status()
                with _health_lock:
                    s["health"] = dict(_health)
                s["boot_id"] = BOOT_ID
                s["mock"] = brain.is_mock()
                s["backup"] = backup.status()
                return self._send(200, s)
            if u.path == "/api/board":
                return self._send(200, {"active": store.get_active()})
            if u.path == "/api/log":
                date = q.get("date") or store._today()
                return self._send(200, {"date": date, "entries": store.read_log(date), "dates": store.log_dates()})
            if u.path == "/api/docs":
                return self._send(200, {"docs": store.doc_index()})
            if u.path == "/api/file":
                p = store.resolve_any(q.get("path"))
                ext = p.suffix.lower()
                if ext in TEXT_VIEW_EXT:
                    return self._send(200, {"path": q.get("path"), "ext": ext,
                                            "text": p.read_text(encoding="utf-8", errors="replace")})
                if ext in RAW_TYPES:
                    return self._send(200, {"path": q.get("path"), "ext": ext, "text": None})
                return self._err(415, "Can't show this file type.")
            if u.path == "/api/raw":
                p = store.resolve_any(q.get("path"))
                ext = p.suffix.lower()
                if ext not in RAW_TYPES:
                    return self._err(415, "Not a raw-viewable file.")
                return self._send(200, p.read_bytes(), RAW_TYPES[ext])
            if u.path == "/api/seen/prefill":
                return self._send(200, {"text": latest_observation()})
            if u.path == "/api/debrief":
                date = q.get("date") or store._today()
                p = store.DEBRIEF_DIR / ("%s.md" % date)
                if not store.DATE_RE.match(date):
                    return self._err(400, "Bad date.")
                return self._send(200, {"date": date, "saved": p.read_text(encoding="utf-8") if p.exists() else None})
            return self._err(404, "Not found.")
        except FileNotFoundError:
            return self._err(404, "File not found.")
        except ValueError as e:
            return self._err(400, str(e))

    def _static(self, rel):
        p = (STATIC / rel).resolve()
        try:
            p.relative_to(STATIC.resolve())
        except ValueError:
            return self._err(403, "No.")
        if not p.is_file():
            return self._err(404, "Not found.")
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if p.suffix == ".woff2":
            ctype = "font/woff2"
        if p.suffix == ".m4a":
            ctype = "audio/mp4"                       # tour narration; Chrome expects this type
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        return self._send(200, p.read_bytes(), ctype)

    # -- POST
    def do_POST(self):
        if not self._host_ok():
            return self._err(403, "Bad host.")
        u = urlparse(self.path)
        # POST /api/log needs the token (from jarvis/settings.json) — the page, Shortcuts and curl all send it.
        if u.path == "/api/log":
            if not capture.token_ok(self.headers.get("Authorization") or self.headers.get("X-Jarvis-Token")):
                return self._err(401, "Missing or wrong token.", "Use the token from jarvis/settings.json (README: Quick-log from any app).")
            if self.headers.get("X-Jarvis") != "1":
                return self._token_log()
        # Custom header = browsers on other sites can't post here without a CORS preflight we never answer.
        elif self.headers.get("X-Jarvis") != "1":
            return self._err(403, "Missing X-Jarvis header.")
        try:
            body = self._body()
            if u.path in routes.POST:
                code, payload = routes.POST[u.path](body, self)
                return self._send(code, payload)
            if u.path == "/api/log/undo":
                return self._send(200, {"removed": store.undo_last()})
            if u.path == "/api/ask":
                return self._stream_ask(body)
            if u.path == "/api/seen/fast":
                a = store.get_active()
                r = store.fast_search(body.get("q", ""), exclude_serial=a["serial"] if a else None)
                r["patterns"] = closeout.patterns_for_query(body.get("q", ""))
                store.usage("seen_fast")
                return self._send(200, r)
            if u.path == "/api/seen/brain":
                store.usage("seen_brain")
                return self._send(200, seen_brain(body.get("q", ""), body.get("lang")))
            if u.path == "/api/debrief":
                date = body.get("date") or store._today()
                if not store.DATE_RE.match(date):
                    return self._err(400, "Bad date.")
                store.usage("debrief")
                return self._send(200, debrief(date, body.get("lang")))
            if u.path == "/api/health":
                run_health()
                with _health_lock:
                    return self._send(200, dict(_health))
            return self._err(404, "Not found.")
        except ValueError as e:
            return self._err(400, str(e))

    def _token_log(self):
        """Quick-log from another app (Shortcuts/curl): JSON {"text": "...", "kind"?, "status"?} or plain text."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(min(n, 20000)).decode("utf-8", "replace") if n else ""
            if (self.headers.get("Content-Type") or "").startswith("application/json"):
                body = json.loads(raw or "{}")
            else:
                body = {"text": raw}
            e = store.add_entry(body.get("text"), body.get("kind"), body.get("status"), source="api")
            store.usage("log_api")
            return self._send(200, {"ok": True, "serial": e["serial"], "ts": e["ts"],
                                    "reading": e.get("reading"), "text": e["text"]})
        except ValueError as ex:
            return self._err(400, str(ex))

    def _stream_ask(self, body):
        question = (body.get("question") or "").strip()
        if not question:
            return self._err(400, "Empty question.")
        ctx = board_context_text() if body.get("board_context") else ""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        store.usage("ask", followup=bool(body.get("session_id")))
        try:
            for ev in brain.ask("ask", question, ctx, session_id=body.get("session_id") or None,
                                lang=body.get("lang")):
                if ev.get("type") == "done":
                    store.cite("ask", ev.get("text"))
                self.wfile.write((json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # user closed the tab or pressed stop; brain.ask's finally kills the child


CHROME_MAC = ("/Applications/Google Chrome.app", str(Path.home() / "Applications/Google Chrome.app"))
CHROME_WIN = (r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
              r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
              r"%LocalAppData%\Google\Chrome\Application\chrome.exe")


def open_browser(url):
    """Open the app in Google Chrome only (other browsers are blocked on the bench machines).
    If Chrome isn't found, print the address instead of opening some other browser."""
    import subprocess
    if sys.platform == "darwin":
        if any(Path(p).exists() for p in CHROME_MAC):
            if subprocess.run(["open", "-a", "Google Chrome", url]).returncode == 0:
                return
    elif os.name == "nt":
        for p in CHROME_WIN:
            exe = os.path.expandvars(p)
            if Path(exe).exists():
                subprocess.Popen([exe, url])
                return
    else:
        for name in ("google-chrome", "google-chrome-stable", "chrome"):
            try:
                webbrowser.get(name).open(url)
                return
            except webbrowser.Error:
                pass
    print("Google Chrome not found. Open this address in Chrome: %s" % url)


def port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, port)) == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("JARVIS_PORT", "8765")))
    ap.add_argument("--open", action="store_true", help="open the browser after start")
    ap.add_argument("--no-health", action="store_true", help="skip the Claude Code startup check")
    a = ap.parse_args()
    url = "http://%s:%d/" % (HOST, a.port)
    if port_in_use(a.port):
        print("JARVIS is already running at %s" % url)
        if a.open:
            open_browser(url)
        return
    srv = ThreadingHTTPServer((HOST, a.port), Handler)
    srv.daemon_threads = True
    if not a.no_health:
        threading.Thread(target=run_health, daemon=True).start()
    else:
        _health.update({"ok": True, "detail": "Startup check skipped."})
    print("JARVIS online at %s%s  (Ctrl+C to stop)" % (url, "  [MOCK MODE]" if brain.is_mock() else ""))
    if a.open:
        threading.Timer(0.6, lambda: open_browser(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nJARVIS offline.")


if __name__ == "__main__":
    main()
