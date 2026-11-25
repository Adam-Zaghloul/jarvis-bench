"""Canned brain answers for JARVIS_MOCK=1. No Claude usage. Shapes match brain.ask() exactly."""
import json
import time
import uuid

MOCK_ASK = """## From your docs

**Mock answer.** The status-LED branch starts by confirming all three rails before probing the clock and the LED path [[01-decision-tree.md#BRANCH 2 — Status LED never blinks]].

Step 1 — zero the meter leads and record the offset. Why: a lead offset can make a copper short look like a part failure [[CLAUDE.md#Hard-won rules worth enforcing on me]].

⚡ POWER ON is **not** needed for this step.

Send me the offset reading.

## From past cases

Board 10000000000011 had the same symptom; R14 was open [[10000000000011-led-not-blinking-R14.md#Root cause]].

## General knowledge (not in your docs)

Typical leads read 0.1–0.4 Ω shorted.
"""


def _chunks(text, n=24):
    for i in range(0, len(text), n):
        yield text[i:i + n]


def mock_events(mode, question, context, session_id):
    sid = session_id or str(uuid.uuid4())
    if "MOCK_ERROR" in (question or ""):
        yield {"type": "error", "message": "Mock error (question contained MOCK_ERROR).",
               "hint": "This is the error path. Remove MOCK_ERROR and retry."}
        return
    if mode == "ask":
        yield {"type": "session", "id": sid}
        yield {"type": "tool", "name": "Read", "detail": "01-decision-tree.md"}
        text = MOCK_ASK
        if session_id:
            text = "## From your docs\n\n**Mock follow-up** (same session `%s`). Offset noted. Next step: measure R14 in diode mode [[10000000000011-led-not-blinking-R14.md#Root cause]].\n" % sid[:8]
        for c in _chunks(text):
            time.sleep(0.01)
            yield {"type": "delta", "text": c}
        yield {"type": "done", "text": text, "session_id": sid, "duration_s": 0.3}
    elif mode == "seen":
        data = {
            "summary": {"similar_count": 3,
                        "pattern": "Mock: led-not-blinking boards traced to the clock path or the LED_STATUS sensor.",
                        "worked": ["R14 replaced (status LED series resistor)", "C4 replaced (crystal load capacitor)"],
                        "did_not_work": ["Reflashing alone on a board with an open passive"]},
            "cases": [
                {"source_path": "10000000000011-led-not-blinking-R14.md", "source_line": 1, "date": "2026-08-14",
                 "board_type": "DEMO", "serial": "10000000000011", "symptom": "Rails present, status LED never blinks",
                 "fix": "R14 replaced", "outcome": "Locks at bench", "resolved": True},
                {"source_path": "10000000000012-led-not-blinking-C4.md", "source_line": 1, "date": "2026-08-17",
                 "board_type": "DEMO", "serial": "10000000000012", "symptom": "Status LED never blinks",
                 "fix": "C4 replaced", "outcome": "Locks", "resolved": True},
                {"source_path": "10000000000013-led-not-blinking-WIP.md", "source_line": 1, "date": "2026-09-24",
                 "board_type": "DEMO", "serial": "10000000000013", "symptom": "Status LED never blinks",
                 "fix": "", "outcome": "Open", "resolved": False},
                {"source_path": "does-not-exist.md", "source_line": 1, "date": "2026-01-01", "board_type": "DEMO",
                 "serial": "00000000000000", "symptom": "Invented case (must be dropped by the server)",
                 "fix": "", "outcome": "", "resolved": True},
            ],
        }
        yield {"type": "done", "data": data, "session_id": sid, "duration_s": 0.2}
    elif mode == "debrief":
        entries = []
        for line in (context or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    pass
        boards = {}
        for e in entries:
            b = boards.setdefault(e.get("serial", "?"), {"serial": e.get("serial", "?"),
                                                          "board_type": e.get("board_type", "DEMO"),
                                                          "status": "open", "symptom": None,
                                                          "measurements": [], "actions": [], "result": None,
                                                          "next_step": "Mock: continue per decision tree."})
            item = {"ts": e.get("ts", ""), "text": e.get("text", "")}
            k = e.get("kind")
            if k == "measurement":
                b["measurements"].append(item)
            elif k == "action":
                b["actions"].append(item)
            elif k == "result":
                b["result"] = item
            elif b["symptom"] is None:
                b["symptom"] = item
            if e.get("status"):
                b["status"] = e["status"]
        for b in boards.values():
            b["symptom"] = b["symptom"] or {"ts": "", "text": "(none logged)"}
            b["result"] = b["result"] or {"ts": "", "text": "(none logged)"}
        data = {
            "slack": ["Mock debrief: %d boards worked." % len(boards),
                      "Fixed %d, open %d." % (sum(1 for b in boards.values() if b["status"] == "fixed"),
                                             sum(1 for b in boards.values() if b["status"] in ("open", ""))),
                      "No blockers (mock)."],
            "boards": list(boards.values()),
            "open_items": ["Mock: finish open boards."],
            "unplaced": [{"ts": "99:99:99", "text": "invented entry", "reason": "mock: must be flagged"}],
        }
        yield {"type": "done", "data": data, "session_id": sid, "duration_s": 0.2}
    elif mode == "closeout":
        texts = [json.loads(l).get("text", "") for l in (context or "").splitlines() if l.strip().startswith("{")]
        data = {"symptom": texts[0] if texts else "Mock symptom", "root_cause": "Mock: R14 open",
                "fix": "Replaced R14", "parts": "R14", "outcome": texts[-1] if texts else "Mock outcome",
                "root_cause_status": "confirmed"}
        yield {"type": "done", "data": data, "session_id": sid, "duration_s": 0.1}
    elif mode == "handoff":
        yield {"type": "done", "data": {"text": "Mock handoff note.\nMeasured: see log.\nSuggested next check: mock."},
               "session_id": sid, "duration_s": 0.1}
    elif mode == "competency":
        yield {"type": "done", "data": {"items": [
            "Isolated a fault by comparing readings against a known-good board",
            "Mock leak check: replaced R14 on serial 10000000000011",  # must be filtered by the server
        ]}, "session_id": sid, "duration_s": 0.1}
    elif mode == "workinstruction":
        yield {"type": "done", "data": {"text": "DRAFT — not reviewed. Do not use until reviewed.\n\n# Mock work instruction\n\n1. Mock step."},
               "session_id": sid, "duration_s": 0.1}
