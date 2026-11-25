"""JARVIS V2 mock-mode tests. No Claude usage; data in a temp folder.

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

os.environ["JARVIS_MOCK"] = "1"
TMP = os.environ.setdefault("JARVIS_DATA_DIR", tempfile.mkdtemp(prefix="jarvis-v2-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import closeout  # noqa: E402
import parse  # noqa: E402
import reference  # noqa: E402
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
            d = r.read()
            return r.status, (d if raw else json.loads(d))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def board(serial, rev="A", ticket=""):
    return call("/api/board", {"board_type": "DEMO", "serial": serial, "rev": rev, "ticket": ticket})


# ------------------------------------------------------------------ Phase 1

class P1Parse(unittest.TestCase):
    CASES = {
        "TP4 4.98V": ("TP4", 4.98, "V", "dcv"),
        "R47 4.7k": ("R47", 4700, "ohm", "resistance"),
        "D3 diode 0.52": ("D3", 0.52, "V", "diode"),
        "VIN short 0.4 ohm": ("VIN", 0.4, "ohm", "resistance"),
        "U6 pin 32 4.9 V": ("U6.32", 4.9, "V", "dcv"),
        "C58 0.1 uF": ("C58", 1e-7, "F", "capacitance"),
        "Y1 10 MHz": ("Y1", 1e7, "Hz", "frequency"),
        "U6.35 600mV": ("U6.35", 0.6, "V", "dcv"),
    }
    UNSURE = ["Replaced R14", "R14 open", "TP4 4.98", "tp4 4.98", "R9 330", "C64 five volts",
              "LED_STATUS at U6 pin 32 stays high", "Meter leads shorted: 0.31 ohm offset",
              "the 5V rail 5.02 V", "R47 4.7 k ohm", "D3 diode", "TP4 4.98 Q"]

    def test_parses(self):
        for text, (tp, v, u, m) in self.CASES.items():
            r = parse.parse_reading(text)
            self.assertIsNotNone(r, text)
            self.assertEqual((r["test_point"], r["unit"], r["mode"]), (tp, u, m), text)
            self.assertAlmostEqual(r["value"], v, places=9, msg=text)

    def test_unsure_stays_raw(self):
        for text in self.UNSURE:
            self.assertIsNone(parse.parse_reading(text), text)

    def test_raw_text_never_altered(self):
        board("10011110000001")
        code, d = call("/api/log", {"text": "R47 4.7k", "serial": "10011110000001"})
        self.assertEqual(d["entry"]["text"], "R47 4.7k")
        self.assertEqual(d["entry"]["reading"]["value"], 4700)
        code, d = call("/api/log", {"text": "R47 4.7k", "parse": False, "serial": "10011110000001"})
        self.assertNotIn("reading", d["entry"])  # "Wrong? text only" from the preview chip

    def test_preview_saves_nothing(self):
        board("10011110000001")
        n = len(store.read_log(store._today()))
        code, d = call("/api/parse", {"text": "TP4 4.98V"})
        self.assertEqual(d["reading"]["test_point"], "TP4")
        self.assertEqual(len(store.read_log(store._today())), n)

    def test_board_changed_since_preview(self):
        board("10011110000002")
        code, d = call("/api/log", {"text": "x", "serial": "10011110000001"})
        self.assertEqual(code, 400)
        self.assertIn("changed", d["error"])


class P1Board(unittest.TestCase):
    def test_rev_ticket(self):
        code, d = board("10011110000003", rev="A", ticket="DEMO-12345")
        self.assertEqual((d["active"]["rev"], d["active"]["ticket"]), ("A", "DEMO-12345"))
        code, d = call("/api/log", {"text": "obs", "kind": "observation", "serial": "10011110000003"})
        self.assertEqual((d["entry"]["rev"], d["entry"]["ticket"]), ("A", "DEMO-12345"))
        self.assertEqual(board("10011110000003", ticket="bad ticket; rm")[0], 400)


class P1Reference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reference.REF_DIR.mkdir(parents=True, exist_ok=True)
        (reference.REF_DIR / "DEMO_A.csv").write_text(
            "test_point,mode,min,max,source,note\n"
            "C64,dcv,4.95,5.10,test-points.md#L8,typed by me\n"
            "U6.32,dcv,0.5,0.7,test-points.md#L34,\n"
            "R14,resistance,10,20,board-reference.md#L18,deliberately wrong to trigger a conflict\n", encoding="utf-8")

    def test_range_flags(self):
        board("10011110000004")
        code, d = call("/api/log", {"text": "C64 5.03 V", "serial": "10011110000004"})
        self.assertEqual(d["entry"]["check"]["status"], "in")
        self.assertIn("test-points.md", d["entry"]["check"]["source"])
        code, d = call("/api/log", {"text": "U6 pin 32 4.9 V", "serial": "10011110000004"})
        self.assertEqual(d["entry"]["check"]["status"], "out")
        code, d = call("/api/log", {"text": "TP99 1.0 V", "serial": "10011110000004"})
        self.assertEqual(d["entry"]["check"]["status"], "none")
        # stored entry has no check field (computed on read only)
        last = store.read_log(store._today())[-1]
        self.assertNotIn("check", last)

    def test_known_good_separate(self):
        board("10011110000005")
        call("/api/log", {"text": "C64 5.06 V", "serial": "10011110000005"})
        call("/api/log", {"text": "R34 332k", "serial": "10011110000005"})
        self.assertEqual(call("/api/reference/known-good", {"serial": "wrong"})[0], 400)
        code, d = call("/api/reference/known-good", {"serial": "10011110000005"})
        self.assertEqual(d["added"], 2)
        code, d = call("/api/reference/known-good", {"serial": "10011110000005"})
        self.assertEqual(d["added"], 0)  # idempotent
        chk = reference.check(parse.parse_reading("C64 5.00 V"), "DEMO", "A")
        self.assertEqual((chk["min"], chk["max"]), (4.95, 5.10))  # typed range untouched
        self.assertEqual(chk["sample"]["n"], 1)
        self.assertFalse(chk["sample"]["inside"])

    def test_conflict(self):
        code, o = call("/api/reference")
        tps = [c["test_point"] for c in o["conflicts"]]
        self.assertIn("R14", tps)        # doc says 330 Ω, range is 10-20 Ω
        self.assertNotIn("C64", tps)     # doc 5.02 V inside 4.95-5.10


class P1Closeout(unittest.TestCase):
    def test_draft_then_confirm(self):
        s = "10011110000006"
        board(s)
        call("/api/log", {"text": "Rails present, status LED never blinks", "kind": "observation", "serial": s})
        call("/api/log", {"text": "Replaced R14", "kind": "action", "status": "fixed", "serial": s})
        before = len(closeout.load())
        code, d = call("/api/closeout/draft", {"serial": s})
        self.assertFalse(d["saved"])
        self.assertEqual(d["draft"]["root_cause_status"], "suspected")  # default even though brain says confirmed
        self.assertTrue(d["draft"]["brain_suggests_confirmed"])
        self.assertEqual(len(closeout.load()), before)                 # drafting saves nothing
        self.assertEqual(call("/api/closeout/confirm", {"serial": s, "card": {"symptom": ""}})[0], 400)
        card = dict(d["draft"]); card.pop("brain_suggests_confirmed")
        code, c = call("/api/closeout/confirm", {"serial": s, "card": card})
        self.assertTrue(c["saved"])
        self.assertEqual(c["closeout"]["root_cause_status"], "suspected")
        self.assertEqual(c["closeout"]["closed_status"], "fixed")
        self.assertEqual(len(closeout.load()), before + 1)

    def test_status_triggers_card(self):
        board("10011110000007")
        code, d = call("/api/log", {"text": "Sent to engineering", "status": "escalated", "serial": "10011110000007"})
        self.assertTrue(d["closeout_needed"])
        code, d = call("/api/log", {"text": "still open", "status": "open", "serial": "10011110000007"})
        self.assertFalse(d["closeout_needed"])


class P1Patterns(unittest.TestCase):
    def test_pattern_from_three(self):
        for i, (sym, rc) in enumerate([
            ("Status LED dark, rails present", "R14 open, status LED series resistor unlit"),
            ("Rails OK but status LED dark", "R14 open circuit, status LED dark"),
            ("Rails present, status LED never blinks at bench", "R14 cracked, LED_STATUS LED off"),
            ("No RS485 reply to host controller", "U3 transceiver damaged"),
        ]):
            s = "1001111001000%d" % i
            board(s)
            call("/api/log", {"text": sym, "kind": "observation", "status": "fixed", "serial": s})
            call("/api/closeout/confirm", {"serial": s, "card": {"symptom": sym, "root_cause": rc, "fix": "Replaced",
                                                                  "root_cause_status": "confirmed"}})
        code, d = call("/api/patterns")
        pats = [p for p in d["patterns"] if "R14" in p["parts"]]
        self.assertEqual(len(pats), 1)
        self.assertGreaterEqual(len(pats[0]["cases"]), 3)
        self.assertFalse(any("RS485" in c["symptom"] for c in pats[0]["cases"]))
        self.assertEqual(pats[0]["status"], "new")
        code, d = call("/api/seen/fast", {"q": "status LED dark"})
        self.assertEqual(d["patterns"], [])              # not verified yet → not shown first
        call("/api/patterns", {"id": pats[0]["id"], "status": "verified"})
        code, d = call("/api/seen/fast", {"q": "status LED dark"})
        self.assertEqual(d["patterns"][0]["id"], pats[0]["id"])
        self.assertEqual(call("/api/patterns", {"id": "zzz", "status": "verified"})[0], 400)


# ------------------------------------------------------------------ Phase 2

import eval as jeval  # noqa: E402


class P2Trust(unittest.TestCase):
    def test_feedback(self):
        cand = Path(TMP) / "evals" / "candidates.jsonl"
        n = len(cand.read_text().splitlines()) if cand.exists() else 0
        call("/api/feedback", {"rating": "up", "question": "q", "answer": "a"})
        self.assertEqual(len(cand.read_text().splitlines()) if cand.exists() else 0, n)
        code, d = call("/api/feedback", {"rating": "down", "reason": "wrong pin", "question": "Which pin?",
                                          "answer": "Pin 8 [[test-points.md#L36]] and [[CLAUDE.md]]"})
        rec = json.loads(cand.read_text().splitlines()[-1])
        self.assertEqual((rec["question"], rec["reason"]), ("Which pin?", "wrong pin"))
        self.assertEqual(rec["citations"], ["test-points.md#L36", "CLAUDE.md"])
        self.assertEqual(call("/api/feedback", {"rating": "meh"})[0], 400)

    def test_hypothesis_reaches_closeout(self):
        s = "10011110000020"
        board(s)
        call("/api/hypothesis", {"question": "status LED dark", "hypothesis": "R14 open", "serial": s})
        call("/api/log", {"text": "Replaced R14", "kind": "action", "status": "fixed", "serial": s})
        code, d = call("/api/closeout/draft", {"serial": s})
        self.assertEqual(d["hypotheses"][-1]["hypothesis"], "R14 open")
        card = {"symptom": "unlit", "root_cause": "R14 open", "root_cause_status": "confirmed"}
        code, c = call("/api/closeout/confirm", {"serial": s, "card": card,
                                                  "hypothesis": {"text": "R14 open", "match": True}})
        self.assertTrue(c["closeout"]["hypothesis_match"])

    def test_golden_set_shape(self):
        # No fixed count: questions get added by hand. Every line must be a well-formed question instead.
        # expect keys per type: (required, optional) besides "type".
        EXPECT = {"must_cite": ({"target"}, set()), "not_in_docs": (set(), set()), "one_step": (set(), set()),
                  "expected_verdict": ({"verdict"}, {"target"})}
        ANY = {"must_contain"}                                   # optional on every type
        lines = [l for l in jeval.GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertTrue(lines, "golden set is empty")
        ids = []
        for n, line in enumerate(lines, 1):
            with self.subTest(line=n):
                i = json.loads(line)
                self.assertEqual(set(i), {"id", "status", "question", "expect", "why"})
                self.assertRegex(i["id"], r"^g\d{2,}$")
                ids.append(i["id"])
                self.assertIn(i["status"], ("draft", "confirmed"))   # confirmed only by you, by hand
                for k in ("question", "why"):
                    self.assertIsInstance(i[k], str)
                    self.assertTrue(i[k].strip(), k)
                e = i["expect"]
                self.assertIn(e.get("type"), EXPECT)
                req, opt = EXPECT[e["type"]]
                self.assertTrue(req <= set(e) - {"type"} <= req | opt | ANY, "expect keys %s" % sorted(e))
                if "must_contain" in e:
                    mc = e["must_contain"]
                    self.assertTrue(isinstance(mc, list) and mc, "must_contain must be a non-empty list")
                    self.assertTrue(all(isinstance(t, str) and t.strip() == t and t for t in mc), mc)
                    self.assertEqual(len(mc), len({t.lower() for t in mc}), "duplicate terms")
                if "verdict" in e:
                    self.assertIn(e["verdict"], ("yes", "no"))
                if "target" in e:
                    for t in e["target"].split("|"):
                        self.assertTrue(t and (store.REPO / t).is_file(), "target %r" % t)
                # The eval must know this type (an unknown type would silently fail every run).
                self.assertNotEqual(jeval.check(i, "## From your docs\n\nx")[1], "unknown expect type")
        self.assertEqual(len(ids), len(set(ids)), "duplicate ids")

    def test_eval_checks(self):
        good = "## From your docs\n\nC64 reads 5.04 V [[test-points.md#L14]].\n"
        self.assertTrue(jeval.check({"expect": {"type": "must_cite", "target": "test-points.md"}}, good)[0])
        self.assertFalse(jeval.check({"expect": {"type": "must_cite", "target": "board-reference.md"}}, good)[0])
        nd = "## From your docs\n\nThe docs don't cover a torque spec.\n"
        self.assertTrue(jeval.check({"expect": {"type": "not_in_docs"}}, nd)[0])
        self.assertFalse(jeval.check({"expect": {"type": "not_in_docs"}}, good)[0])
        one = "## From your docs\n\nMeasure C64 (⚡ POWER ON). Why: … Send me the reading.\n"
        two = "## From your docs\n\n1. Measure C64.\n2. Measure U6 pin 32.\nSend both.\n"
        self.assertTrue(jeval.check({"expect": {"type": "one_step"}}, one)[0])
        self.assertFalse(jeval.check({"expect": {"type": "one_step"}}, two)[0])
        v = {"expect": {"type": "expected_verdict", "verdict": "no", "target": "test-points.md"}}
        no = "## From your docs\n\n**No. Don't probe pin 9 (XIN).** Probe pin 10 [[test-points.md#L13]].\n"
        self.assertTrue(jeval.check(v, no)[0])
        self.assertEqual(jeval.first_sentence(no), "No.")
        self.assertFalse(jeval.check(v, no.replace("test-points.md", "board-reference.md"))[0])  # right verdict, wrong source
        self.assertFalse(jeval.check(v, "## From your docs\n\nYes, pin 9 is fine [[test-points.md#L13]].\n")[0])
        self.assertFalse(jeval.check(v, "## From your docs\n\nProbe pin 10. No, not pin 9 [[test-points.md#L13]].\n")[0])  # verdict not first
        self.assertFalse(jeval.check(v, "## From your docs\n\nNot pin 9 [[test-points.md#L13]].\n")[0])  # "Not" isn't "No"
        self.assertTrue(jeval.check({"expect": {"type": "expected_verdict", "verdict": "yes"}}, "## From your docs\n\n- Yes — pin 10 is safe.\n")[0])
        self.assertFalse(jeval.check({"expect": {"type": "expected_verdict", "verdict": "maybe"}}, "## From your docs\n\nMaybe.\n")[0])
        mc = {"expect": {"type": "must_cite", "target": "test-points.md", "must_contain": ["5.04", "c64"]}}
        self.assertTrue(jeval.check(mc, good)[0])                                   # case-insensitive
        self.assertFalse(jeval.check(mc, good.replace("5.04", "15.04"))[0])         # whole word only
        self.assertTrue(jeval.check(mc, good.replace("5.04", "5.040"))[0])          # numbers match by value
        self.assertFalse(jeval.check(mc, good.replace("5.04", "5.04.1"))[0])
        self.assertTrue(jeval.check(mc, good.replace("5.04", "5.04V"))[0])          # unit glued on
        self.assertEqual(jeval.missing_terms(["5.04", "4.7", "330", "16", "470", "10", "35"],
                         "5.04V, 4.7k or 4.7kΩ, 330Ω, 16MHz, 470pF, 10mA, 35%."), [])
        self.assertEqual(jeval.missing_terms(["4.7"], "4.7K"), [])
        self.assertEqual(jeval.missing_terms(["12"], "12 ohms"), [])
        self.assertEqual(jeval.missing_terms(["8"], "p/n 8AB-01-100"), ["8"])     # not a unit
        self.assertEqual(jeval.missing_terms(["2"], "the 2nd pass"), ["2"])
        self.assertEqual(jeval.missing_terms(["5"], "5V0 and 5.5V"), ["5"])
        num = lambda terms, ans: jeval.missing_terms(terms, ans)
        self.assertEqual(num(["2.5", "10", "0.215"], "2.50 V, 10.0 kΩ, 0.2150 Ω."), [])
        self.assertEqual(num(["2.5"], "VIN 12.5 V or 2.55 V"), ["2.5"])
        self.assertEqual(num(["5"], "2.5 V and 0.5"), ["5"])                        # not part of a decimal
        self.assertEqual(num(["5", "29"], "5 V, rows 29-35."), [])
        self.assertEqual(num(["7", "8"], "pin 7, not pin 8."), [])
        self.assertEqual(num(["6"], "U6 and R6"), ["6"])                            # digits inside a part name don't count
        self.assertEqual(num(["LED_STATUS", "PB6"], "the led_status net; PB6 leaks; LED_STATUS2"), [])
        self.assertEqual(num(["VIN"], "VIN_SENSE only"), ["VIN"])
        self.assertFalse(jeval.check(mc, good.replace("C64 ", "C640 "))[0])
        self.assertFalse(jeval.check(mc, good.replace("test-points.md", "board-reference.md"))[0])  # type check still applies
        self.assertIn("missing: 5.04", jeval.check(mc, good.replace("5.04", "5.1"))[1])
        cit = {"expect": {"type": "not_in_docs", "must_contain": ["14"]}}
        self.assertFalse(jeval.check(cit, "## From your docs\n\nThe docs don't cover it [[test-points.md#L14]].\n")[0])  # not from a citation
        self.assertTrue(jeval.check({"expect": {"type": "expected_verdict", "verdict": "no", "must_contain": ["U3", "10"]}},
                                    "## From your docs\n\nNo. Probe U3 pin 10.\n")[0])
        self.assertTrue(jeval.labels_ok(good)[0])
        self.assertFalse(jeval.labels_ok("Preamble.\n\n## From your docs\n\nx")[0])
        self.assertFalse(jeval.labels_ok("## Answer\n\nx")[0])

    def test_eval_refuses_mock(self):
        self.assertEqual(jeval.main.__code__.co_name, "main")
        old = sys.argv
        sys.argv = ["eval.py"]
        try:
            self.assertEqual(jeval.main(), 2)  # JARVIS_MOCK=1 → refuses, never fakes results
        finally:
            sys.argv = old

    def test_golden_never_written(self):
        before = jeval.GOLDEN.stat().st_mtime
        jeval.check({"expect": {"type": "not_in_docs"}}, "x")
        self.assertEqual(jeval.GOLDEN.stat().st_mtime, before)


# ------------------------------------------------------------------ Phase 4

import daily  # noqa: E402


class P4Daily(unittest.TestCase):
    def test_time_on_board_excludes_long_gaps(self):
        es = [{"ts": "2026-11-24T09:00:00"}, {"ts": "2026-11-24T09:20:00"},   # 20 min counts
              {"ts": "2026-11-24T10:30:00"},                                     # 70 min gap: excluded
              {"ts": "2026-11-24T10:40:00"}]                                     # 10 min counts
        self.assertEqual(daily.time_on_board(es), 30 * 60)
        self.assertEqual(daily.time_on_board([{"ts": "2026-11-24T09:00:00"}]), 0)
        self.assertEqual(daily.fmt_dur(30 * 60), "30 min")
        self.assertEqual(daily.fmt_dur(95 * 60), "1 h 35 min")

    def test_competency_filter(self):
        keep, drop = daily.competency_filter([
            "Isolated a power-rail short by comparing in-circuit resistance against a known-good board",
            "Replaced R14 on the LED_STATUS path", "Fixed serial 10000000000011", "Closed DEMO-27826",
            "Measured 5.03 V on the rail", "Repaired a DEMO board", "Used an ATmega328P ISP header"])
        self.assertEqual(len(keep), 1)
        self.assertEqual(len(drop), 6)

    def test_weekly(self):
        s = "10011110000030"
        board(s)
        call("/api/hypothesis", {"question": "q", "hypothesis": "C4 open", "serial": s})
        call("/api/log", {"text": "Status LED never blinks", "kind": "observation", "serial": s})
        call("/api/log", {"text": "Replaced C4", "kind": "action", "status": "fixed", "serial": s})
        call("/api/closeout/confirm", {"serial": s, "card": {"symptom": "Status LED never blinks", "root_cause": "C4 open",
                                                             "parts": "C4", "root_cause_status": "confirmed"},
                                       "hypothesis": {"text": "C4 open", "match": True}})
        code, d = call("/api/weekly", {})
        self.assertEqual(code, 200)
        self.assertTrue(Path(d["saved"]).name.startswith("week-"))
        self.assertTrue(Path(d["saved"]).exists())
        self.assertIn("## Competency log", d["markdown"])
        self.assertEqual(len(d["competency"]), 1)        # mock's leaking item was dropped
        self.assertEqual(len(d["dropped"]), 1)
        self.assertNotIn("10000000000011", d["markdown"].split("## Competency log")[1])
        self.assertGreaterEqual(d["stats"]["hit_rate"]["rated"], 1)
        self.assertIn("Median time on board", d["markdown"])
        code, g = call("/api/weekly?week=" + d["week"])
        self.assertTrue(g["saved"])
        self.assertEqual(call("/api/weekly", {"week": "nope"})[0], 400)

    def test_handoff_only_escalated(self):
        s = "10011110000031"
        board(s)
        call("/api/log", {"text": "No RS485 reply", "kind": "observation", "serial": s})
        self.assertEqual(call("/api/handoff", {"serial": s})[0], 400)
        call("/api/log", {"text": "Sent to engineering", "status": "escalated", "serial": s})
        code, d = call("/api/handoff", {"serial": s})
        self.assertEqual(code, 200)
        self.assertTrue(d["copy_only"])
        self.assertTrue(d["text"])

    def test_workinstruction_needs_verified(self):
        pats = closeout.patterns()
        new = [p for p in pats if p["status"] != "verified"]
        if new:
            self.assertEqual(call("/api/workinstruction", {"pattern_id": new[0]["id"]})[0], 400)
        ver = [p for p in pats if p["status"] == "verified"]
        if not ver:
            self.skipTest("no verified pattern in this run")
        code, d = call("/api/workinstruction", {"pattern_id": ver[0]["id"]})
        self.assertTrue(d["text"].startswith("DRAFT"))
        p = Path(d["saved"])
        self.assertEqual(p.parent.name, "drafts")
        self.assertTrue(str(p).startswith(TMP))           # never inside the repo docs
        self.assertIn("DRAFT", p.read_text())


# ------------------------------------------------------------------ Phase 5

import base64  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402
import zlib  # noqa: E402

import capture  # noqa: E402


def _jpeg_with_gps():
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    exif_body = b"Exif\x00\x00" + b"MM\x00\x2a GPSLatitude 45.53 N GPSLongitude 73.51 W"
    app1 = b"\xff\xe1" + struct.pack(">H", len(exif_body) + 2) + exif_body
    com = b"\xff\xfe" + struct.pack(">H", 9) + b"secret!"
    dqt = b"\xff\xdb" + struct.pack(">H", 67) + b"\x00" + bytes(range(64))
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\x01\x01\x00\x00\x3f\x00" + b"\x12\x34\x56" + b"\xff\xd9"
    return b"\xff\xd8" + app0 + app1 + com + dqt + sos


def _png_with_text():
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"tEXt", b"GPS\x0045.53,-73.51") +
            chunk(b"eXIf", b"MM\x00\x2a") + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


class P5Capture(unittest.TestCase):
    def test_scan_detector_node(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not installed")
        r = subprocess.run([node, str(Path(__file__).parent / "scan_test.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)

    def test_photo_metadata_stripped(self):
        board("10011110000040")
        for raw, mime in ((_jpeg_with_gps(), "jpeg"), (_png_with_text(), "png")):
            self.assertTrue(capture.has_metadata(raw))
            code, d = call("/api/photo", {"data": "data:image/%s;base64,%s" % (mime, base64.b64encode(raw).decode())})
            self.assertEqual(code, 200, d)
            self.assertTrue(d["path"].startswith("jarvis/logs/photos/" + store._today() + "/"))
            saved = (store.LOG_DIR / d["path"].split("jarvis/logs/", 1)[1]).read_bytes()
            self.assertFalse(capture.has_metadata(saved), mime)
            self.assertNotIn(b"GPS", saved)
        # A realistic phone-size photo (~1.5 MB) must fit; the 200 KB limit for other POSTs doesn't apply.
        big = _jpeg_with_gps()[:-2] + b"\x00" * 1_500_000 + b"\xff\xd9"
        code, d = call("/api/photo", {"data": "data:image/jpeg;base64," + base64.b64encode(big).decode()})
        self.assertEqual(code, 200, d)
        self.assertEqual(call("/api/photo", {"data": "data:image/gif;base64,R0lGOD"})[0], 400)
        self.assertEqual(call("/api/photo", {"data": "data:image/jpeg;base64," + base64.b64encode(b"notajpeg").decode()})[0], 400)

    def test_photo_on_entry_and_debrief(self):
        s = "10011110000041"
        board(s)
        code, d = call("/api/photo", {"data": "data:image/jpeg;base64," + base64.b64encode(_jpeg_with_gps()).decode()})
        code, e = call("/api/log", {"text": "", "photos": [d["path"]], "serial": s})
        self.assertEqual(code, 200, e)                                  # photo-only entry allowed
        self.assertEqual(e["entry"]["photos"], [d["path"]])
        self.assertEqual(call("/api/log", {"text": "x", "photos": ["../../etc/passwd"], "serial": s})[0], 400)
        code, r = call("/api/raw?path=" + d["path"], raw=True)
        self.assertEqual(code, 200)
        code, deb = call("/api/debrief", {"date": store._today()})
        self.assertIn(s, deb["photos"])
        self.assertIn("## Photos", Path(deb["saved"]).read_text())

    def test_token_quicklog(self):
        board("10011110000042")
        url = "http://127.0.0.1:%d/api/log" % PORT

        def post(data, headers):
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        self.assertEqual(post(b'{"text":"x"}', {"Content-Type": "application/json", "X-Jarvis": "1"})[0], 401)
        self.assertEqual(post(b'{"text":"x"}', {"Content-Type": "application/json", "Authorization": "Bearer nope"})[0], 401)
        tok = capture.api_token()
        code, d = post(b'{"text":"TP4 4.98V"}', {"Content-Type": "application/json", "Authorization": "Bearer " + tok})
        self.assertEqual((code, d["serial"], d["reading"]["test_point"]), (200, "10011110000042", "TP4"))
        code, d = post("Plain line from Shortcuts".encode(), {"Content-Type": "text/plain", "X-Jarvis-Token": tok})
        self.assertEqual((code, d["text"]), (200, "Plain line from Shortcuts"))
        self.assertEqual(store.read_log(store._today())[-1].get("source"), "api")
        self.assertEqual(json.loads(capture.SETTINGS.read_text())["api_token"], tok)  # stored in settings.json


# ------------------------------------------------------------------ Phase 6

import datetime as _dt  # noqa: E402

import backup  # noqa: E402
import health  # noqa: E402


class P6Health(unittest.TestCase):
    def test_audit_on_fake_repo(self):
        fake = Path(tempfile.mkdtemp(prefix="jarvis-audit-"))
        (fake / "schematics").mkdir()
        (fake / "a.md").write_text("See [b](b.md) and [gone](missing.md) and [web](https://x.y) and [top](#top).\n"
                                   "Old path `reference/test-points.md`, real path `schematics/`, missing file `schematics/nope.pdf`.\n"
                                   "Placeholder `jarvis/logs/YYYY-MM-DD.jsonl`, data `jarvis/logs/closeouts.jsonl` and external `~/dev/other-project/` are skipped.\n"
                                   "```\n[in code](nowhere.md)\n```\n")
        (fake / "b.md").write_text("# b\n")
        (fake / "JARVIS_X_SPEC.md").write_text("[future](future/x.md)\n")
        old = store.REPO
        store.REPO = fake
        try:
            store.cite("ask", "answer cites [[b.md#L1]] only")
            a = health.audit()
        finally:
            store.REPO = old
        self.assertEqual([(b["path"], b["line"], b["target"]) for b in a["broken_links"]], [("a.md", 1, "missing.md")])
        self.assertEqual(sorted((m["ref"], m["why"].split()[0]) for m in a["missing_paths"]),
                         [("reference/test-points.md", "folder"), ("schematics/nope.pdf", "file")])
        uncited = sum(a["uncited"].values(), [])
        self.assertIn("a.md", uncited)
        self.assertNotIn("b.md", uncited)                       # cited today
        self.assertNotIn("JARVIS_X_SPEC.md", uncited)
        self.assertTrue(a["citations_since"])
        self.assertEqual({o["path"] for o in a["oldest"]}, {"a.md", "b.md"})

    def test_usage_week(self):
        board("10011110000060")
        call("/api/log", {"text": "usage check"})
        call("/api/seen/fast", {"q": "status"})
        call("/api/ask", {"question": "status LED dark"}, raw=True)
        call("/api/board", {"board_type": "DEMO", "serial": "10011110000061", "via": "scan"})
        call("/api/feedback", {"rating": "up", "question": "q", "answer": "a [[01-decision-tree.md#L1]]"})
        code, u = call("/api/usage")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(u["entries"], 1)
        self.assertGreaterEqual(u["questions"], 1)
        self.assertGreaterEqual(u["seen"], 1)
        self.assertGreaterEqual(u["thumbs_up"], 1)
        f = {r["event"]: r["count"] for r in u["features"]}
        self.assertGreaterEqual(f["scan"], 1)
        self.assertIn("Escalation handoff", u["unused"]) if not f["handoff"] else None
        self.assertNotIn("Ask", u["unused"])
        self.assertEqual(call("/api/usage?week=nope")[0], 400)
        # Ask's citations were recorded (paths only).
        recs = [json.loads(l) for l in (store.LOG_DIR / "citations.jsonl").read_text().splitlines()]
        self.assertTrue(any(r["mode"] == "ask" and r["paths"] for r in recs))
        self.assertFalse(any("LED dark" in json.dumps(r) for r in recs))

    def test_backup_copy_prune_and_status(self):
        dest = Path(tempfile.mkdtemp(prefix="jarvis-bk-"))
        (dest / "my-own-folder").mkdir()
        (dest / "jarvis-backup-notes").mkdir()               # not our exact name pattern: never deleted
        board("10011110000062")
        call("/api/log", {"text": "backup me"})
        capture.api_token()
        t0 = _dt.datetime(2026, 1, 1, 9, 0, 0)
        for i in range(12):
            r = backup.run(str(dest), now=t0 + _dt.timedelta(days=i))
        ours = sorted(p.name for p in dest.iterdir() if backup.NAME_RE.match(p.name))
        self.assertEqual(len(ours), 10)
        self.assertEqual(ours[0], "jarvis-backup-2026-01-03_090000")
        self.assertTrue((dest / "my-own-folder").is_dir() and (dest / "jarvis-backup-notes").is_dir())
        last = Path(r["path"])
        self.assertTrue((last / "settings.json").is_file())
        self.assertTrue(any((last / "logs").glob("*.jsonl")))
        m = json.loads((last / "manifest.json").read_text())
        self.assertEqual(m["files"], r["files"])
        st = backup.status(now=t0 + _dt.timedelta(days=11 + 8))
        self.assertTrue(st["stale"])
        self.assertEqual(st["dest"], str(dest.resolve()))
        self.assertFalse(backup.status(now=t0 + _dt.timedelta(days=12))["stale"])
        for bad in (str(store.REPO / "x"), str(store.DATA_DIR / "logs"), ""):
            with self.assertRaises(ValueError):
                backup.run(bad) if bad else backup.run("  ")
        code, s = call("/api/status")
        self.assertIn("backup", s)
        self.assertEqual(call("/api/backup")[1]["dest"], str(dest.resolve()))

    def test_audit_endpoint_real_repo(self):
        code, a = call("/api/audit")
        self.assertEqual(code, 200)
        for k in ("broken_links", "missing_paths", "uncited", "oldest"):
            self.assertIn(k, a)


class P7Tour(unittest.TestCase):
    """The narrated tour: scene list is well formed, every scene has its voiceover clip, and the app links to it."""
    TOUR = Path(__file__).resolve().parent.parent / "static" / "tour"
    PANES = {"", "ask", "seen", "log", "debrief", "board", "patterns", "review", "health"}

    def test_scenes_and_audio(self):
        scenes = json.loads((self.TOUR / "scenes.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(scenes), 5)
        ids = [s["id"] for s in scenes]
        self.assertEqual(len(ids), len(set(ids)), "scene ids must be unique")
        for s in scenes:
            with self.subTest(scene=s.get("id")):
                self.assertEqual(set(s), {"id", "title", "pane", "caption", "say"}, "unexpected keys")
                self.assertTrue(s["title"].strip() and s["say"].strip())
                self.assertIn(s["pane"], self.PANES)
                self.assertTrue(isinstance(s["caption"], list) and s["caption"], "caption must be a non-empty list")
                self.assertTrue(all(isinstance(c, str) and c.strip() for c in s["caption"]))
                clip = self.TOUR / (s["id"] + ".m4a")
                self.assertTrue(clip.is_file(), "run: python3 jarvis/tour_audio.py")
                self.assertGreater(clip.stat().st_size, 1000)

    def test_tour_is_served_and_linked(self):
        app = (self.TOUR.parent / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="/static/tour.html"', app)
        page = (self.TOUR.parent / "tour.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>", page)                # CSP: script-src 'self' only
        self.assertNotIn("style=", page)                  # CSP: style-src 'self' only
        self.assertIn('src="/static/tour.js"', page)


if __name__ == "__main__":
    unittest.main(verbosity=2)
