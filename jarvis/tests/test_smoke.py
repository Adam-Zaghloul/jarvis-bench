"""JARVIS mock-mode smoke tests. No Claude usage, no writes to the real jarvis/logs.

    python -m unittest discover -s jarvis/tests -v
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="jarvis-test-")
os.environ["JARVIS_MOCK"] = "1"
os.environ["JARVIS_DATA_DIR"] = TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import brain  # noqa: E402
import server  # noqa: E402
import store  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

PORT = None


def setUpModule():
    global PORT, SRV
    SRV = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    PORT = SRV.server_address[1]
    threading.Thread(target=SRV.serve_forever, daemon=True).start()


def tearDownModule():
    SRV.shutdown()


def call(path, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json"}
    if body is not None:
        h["X-Jarvis"] = "1"
    if path.startswith("/api/log") and path != "/api/log/undo" and body is not None:
        import capture
        h["Authorization"] = "Bearer " + capture.api_token()
    h.update(headers or {})
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=None if body is None else json.dumps(body).encode(), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            return r.status, (data if raw else json.loads(data))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


class T1Safety(unittest.TestCase):
    def test_argv_read_only(self):
        argv = brain.build_argv("claude", "ask", "/tmp/r.txt")
        joined = " ".join(argv)
        self.assertIn("--tools Read,Grep,Glob", joined)
        for t in ("Bash", "Edit", "Write", "WebFetch", "WebSearch"):
            self.assertIn(t, argv[argv.index("--disallowedTools") + 1])
        self.assertIn("--strict-mcp-config", argv)
        self.assertNotIn("Question", joined)  # question never in argv

    def test_bad_session_rejected(self):
        with self.assertRaises(brain.BrainError):
            brain.build_argv("claude", "ask", "/tmp/r.txt", session_id="x; rm -rf /")

    def test_cmd_shim_metachar_guard(self):
        with self.assertRaises(brain.BrainError):
            brain._check_argv(["claude.cmd", "-p", "a & calc"])
        brain._check_argv(["claude.cmd"] + brain.build_argv("claude", "seen", "C:/t/r.txt", structured=True)[1:])

    def test_post_needs_header(self):
        req = urllib.request.Request("http://127.0.0.1:%d/api/board" % PORT, data=b"{}",
                                     headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 403)

    def test_bad_host_rejected(self):
        code, _ = call("/api/status", headers={"Host": "evil.example"})
        self.assertEqual(code, 403)

    def test_path_traversal(self):
        for p in ("../../../etc/passwd", ".git/config", "..%2F..%2Fetc%2Fpasswd"):
            code, _ = call("/api/file?path=" + p)
            self.assertIn(code, (400, 404), p)

    def test_binds_localhost_only(self):
        self.assertEqual(server.HOST, "127.0.0.1")


class T2Log(unittest.TestCase):
    def test_log_flow(self):
        code, d = call("/api/log", {"text": "no board yet"})
        if store.get_active() is None:
            self.assertEqual(code, 400)
        code, d = call("/api/board", {"board_type": "DEMO", "serial": "10000000000001"})
        self.assertEqual(code, 200)
        code, d = call("/api/log", {"text": "VIN to GND 0.42 ohm", "kind": "measurement"})
        self.assertEqual(d["entry"]["serial"], "10000000000001")
        call("/api/log", {"text": "oops", "kind": "observation"})
        code, d = call("/api/log/undo", {})
        self.assertEqual(d["removed"]["text"], "oops")
        code, d = call("/api/log?date=" + store._today())
        texts = [e["text"] for e in d["entries"]]
        self.assertIn("VIN to GND 0.42 ohm", texts)
        self.assertNotIn("oops", texts)
        line = (Path(TMP) / "logs" / ("%s.jsonl" % store._today())).read_text().splitlines()[0]
        self.assertEqual(set(json.loads(line)), {"ts", "board_type", "serial", "kind", "text", "status"})

    def test_bad_kind_status(self):
        call("/api/board", {"board_type": "DEMO", "serial": "10000000000001"})
        self.assertEqual(call("/api/log", {"text": "x", "kind": "nope"})[0], 400)
        self.assertEqual(call("/api/log", {"text": "x", "status": "nope"})[0], 400)


class T3Ask(unittest.TestCase):
    def test_stream_and_followup(self):
        code, raw = call("/api/ask", {"question": "status LED never blinks"}, raw=True)
        evs = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
        types = [e["type"] for e in evs]
        self.assertEqual(types[0], "session")
        self.assertIn("delta", types)
        self.assertEqual(types[-1], "done")
        self.assertIn("[[", evs[-1]["text"])
        sid = evs[-1]["session_id"]
        code, raw = call("/api/ask", {"question": "offset 0.3", "session_id": sid}, raw=True)
        last = json.loads(raw.decode().strip().splitlines()[-1])
        self.assertEqual(last["session_id"], sid)
        self.assertIn("follow-up", last["text"])

    def test_error_path(self):
        code, raw = call("/api/ask", {"question": "MOCK_ERROR"}, raw=True)
        last = json.loads(raw.decode().strip().splitlines()[-1])
        self.assertEqual(last["type"], "error")
        self.assertTrue(last["hint"])

    def test_board_context(self):
        call("/api/board", {"board_type": "DEMO", "serial": "10000000000001"})
        ctx = server.board_context_text()
        self.assertIn("10000000000001", ctx)

    def test_cited_file_opens(self):
        code, d = call("/api/file?path=01-decision-tree.md")
        self.assertEqual(code, 200)
        self.assertIn("BRANCH 2", d["text"])
        code, d = call("/api/raw?path=schematics/DEMO_Schematic.pdf", raw=True)
        self.assertEqual(code, 200)
        self.assertTrue(d.startswith(b"%PDF"))


class T4Seen(unittest.TestCase):
    def test_fast_and_brain(self):
        code, d = call("/api/seen/fast", {"q": "status LED never blinks"})
        self.assertGreater(len(d["hits"]), 3)
        self.assertTrue(all(Path(store.REPO / h["path"]).exists() for h in d["hits"] if not h["path"].startswith("jarvis/")))
        code, d = call("/api/seen/brain", {"q": "status LED never blinks"})
        self.assertEqual(code, 200)
        self.assertEqual(len(d["dropped"]), 1)  # the mock's invented case is dropped
        self.assertTrue(d["resolved"])
        self.assertTrue(d["unresolved"])
        self.assertTrue(all(not c["resolved"] for c in d["unresolved"]))

    def test_jsonl_logs_searched(self):
        call("/api/board", {"board_type": "DEMO", "serial": "10000000000002"})
        call("/api/log", {"text": "zebracrystal oscillation dead", "kind": "observation"})
        call("/api/board", {"board_type": "DEMO", "serial": "10000000000003"})
        code, d = call("/api/seen/fast", {"q": "zebracrystal"})
        self.assertTrue(any(h["class"] == "bench-log" for h in d["hits"]))


class T5Debrief(unittest.TestCase):
    def test_debrief(self):
        call("/api/board", {"board_type": "DEMO", "serial": "10000000000009"})
        call("/api/log", {"text": "Status LED never blinks", "kind": "observation"})
        call("/api/log", {"text": "R14 open", "kind": "measurement"})
        call("/api/log", {"text": "Replaced R14", "kind": "action", "status": "fixed"})
        code, d = call("/api/debrief", {"date": store._today(), "lang": "en"})
        self.assertEqual(code, 200)
        self.assertTrue(d["slack"])
        self.assertTrue(any(j["serial"] == "10000000000009" for j in d["jira"]))
        j = [j for j in d["jira"] if j["serial"] == "10000000000009"][0]["text"]
        self.assertNotIn("??:??:??", j.split("Next step")[0].replace("(none logged)", ""))
        self.assertTrue(any(not u["traced"] for u in d["gaps"]["unplaced"]))  # mock's invented ts flagged
        self.assertTrue(Path(d["saved"]).exists())
        self.assertTrue(str(d["saved"]).startswith(TMP))

    def test_empty_day(self):
        code, d = call("/api/debrief", {"date": "2000-01-01"})
        self.assertTrue(d["empty"])


class T6Static(unittest.TestCase):
    def test_index_and_assets(self):
        code, d = call("/", raw=True)
        self.assertIn(b"JARVIS", d)
        self.assertNotIn(b"http://", d.replace(b"http://www.w3.org", b""))
        self.assertNotIn(b"https://", d)
        for a in ("app.js", "app.css", "md.js", "fonts/orbitron-latin-700-normal.woff2"):
            self.assertEqual(call("/static/" + a, raw=True)[0], 200, a)

    def test_no_external_urls_in_assets(self):
        static = Path(server.STATIC)
        for f in ("app.js", "app.css", "md.js", "index.html"):
            t = (static / f).read_text()
            for bad in ("https://", "cdn.", "googleapis"):
                self.assertNotIn(bad, t, f)

    def test_status_counts(self):
        code, s = call("/api/status")
        self.assertGreaterEqual(s["docs"], 12)
        self.assertGreaterEqual(s["cases"], 4)
        self.assertTrue(s["mock"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
