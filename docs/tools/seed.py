"""Seed a scratch JARVIS data folder with one realistic demo week, through the real API.

    python3 seed.py <port> <data_dir> <photo.png>

Entries are posted through the API (so the stored shape is exactly what the app writes), then their
timestamps are moved onto a believable shift schedule. Only the scratch data folder is touched.
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

PORT, DATA, PHOTO = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
TOKEN = json.loads((DATA / "settings.json").read_text())["api_token"]


def call(path, body=None):
    h = {"Content-Type": "application/json"}
    if body is not None:
        h["X-Jarvis"] = "1"
        if path == "/api/log":
            h["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path),
                                 data=None if body is None else json.dumps(body).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def board(serial, ticket=""):
    call("/api/board", {"board_type": "DEMO", "serial": serial, "rev": "A", "ticket": ticket})


def log(serial, text, kind="", status="", photos=None):
    body = {"text": text, "serial": serial}
    if kind: body["kind"] = kind
    if status: body["status"] = status
    if photos: body["photos"] = photos
    return call("/api/log", body)


# (day, serial, [(time, text, kind, status)], close-out card or None)
R14 = {"symptom": "Status LED never blinks", "root_cause": "R14 open (LED series resistor)", "fix": "Replaced R14, 330 Ω",
       "parts": "R14", "outcome": "LED blinks at 1 Hz", "root_cause_status": "confirmed"}
HISTORY = [
    ("2026-11-23", "10000000000021", [("08:40", "Status LED never blinks, rails OK", "observation", ""),
                                       ("08:52", "U3 pin 15 toggles 0-3.3 V at 1 Hz", "measurement", ""),
                                       ("08:58", "R14 reads open in circuit", "measurement", ""),
                                       ("09:10", "Replaced R14", "action", ""),
                                       ("09:14", "LED blinks at 1 Hz", "result", "fixed")], R14),
    ("2026-11-23", "10000000000022", [("10:05", "Status LED dark, rails present", "observation", ""),
                                       ("10:19", "R14 open", "measurement", ""),
                                       ("10:31", "Replaced R14", "action", ""),
                                       ("10:34", "Blinks OK", "result", "fixed")], R14),
    ("2026-11-24", "10000000000023", [("13:02", "Status LED never blinks at power-up", "observation", ""),
                                       ("13:20", "R14 cracked, reads open", "measurement", ""),
                                       ("13:33", "Replaced R14", "action", ""),
                                       ("13:36", "LED blinks", "result", "fixed")], R14),
    ("2026-11-24", "10000000000024", [("14:10", "No power, bench supply hits current limit", "observation", ""),
                                       ("14:16", "VIN to GND 0.3 ohm", "measurement", ""),
                                       ("14:40", "Thermal camera at 1 A: C12 hot", "observation", ""),
                                       ("14:48", "Replaced C12", "action", ""),
                                       ("14:55", "VIN 12.0 V, rails OK", "result", "fixed")],
     {"symptom": "No power, supply in current limit", "root_cause": "C12 MLCC cracked, VIN shorted", "fix": "Replaced C12",
      "parts": "C12", "outcome": "Rails OK", "root_cause_status": "confirmed"}),
]
photo = call("/api/photo", {"data": "data:image/png;base64," + base64.b64encode(PHOTO.read_bytes()).decode()})["path"]
TODAY = [
    ("2026-11-25", "10000000000013", [("08:05", "Status LED never blinks", "observation", ""),
                                       ("08:09", "Meter leads shorted 0.2 ohm", "measurement", ""),
                                       ("08:12", "C20 5.01 V", "measurement", ""),
                                       ("08:14", "C30 3.30 V", "measurement", ""),
                                       ("08:22", "No 8 MHz at U3 pin 10", "measurement", ""),
                                       ("08:31", "C4 reads open, expected 22 pF", "measurement", ""),
                                       ("08:33", "Bench photo: C4 removed, pads clean", "observation", "PHOTO"),
                                       ("08:47", "Replaced C4", "action", ""),
                                       ("08:52", "8 MHz at pin 10, LED blinks", "result", "fixed")],
     {"symptom": "Status LED never blinks", "root_cause": "C4 open (Y1 load capacitor), no clock", "fix": "Replaced C4, 22 pF",
      "parts": "C4", "outcome": "8 MHz at U3 pin 10, LED blinks", "root_cause_status": "confirmed"}),
    ("2026-11-25", "10000000000014", [("09:20", "Status LED dark, U1 warm to the touch", "observation", ""),
                                       ("09:24", "C10 11.98 V", "measurement", ""),
                                       ("09:26", "C20 4.62 V", "measurement", ""),
                                       ("09:28", "C30 3.05 V", "measurement", "")], None),
]

days = {}
for day, serial, entries, card in HISTORY + TODAY:
    board(serial, "DEMO-%s" % serial[-3:])
    for t, text, kind, status in entries:
        if status == "PHOTO":
            log(serial, text, kind, photos=[photo])
        else:
            log(serial, text, kind, status)
        days.setdefault(serial, []).append(day + "T" + t + ":00")
    if card:
        call("/api/closeout/confirm", {"serial": serial, "card": card})

# Move timestamps onto the schedule above (and history onto its own days).
logdir = DATA / "logs"
today_file = max(logdir.glob("20??-??-??.jsonl"))
rows = [json.loads(l) for l in today_file.read_text().splitlines() if l.strip()]
seen = {}
by_day = {}
for r in rows:
    i = seen.get(r["serial"], 0); seen[r["serial"]] = i + 1
    r["ts"] = days[r["serial"]][i]
    by_day.setdefault(r["ts"][:10], []).append(r)
today_file.unlink()
for day, rs in by_day.items():
    (logdir / (day + ".jsonl")).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sorted(rs, key=lambda r: r["ts"])))
co = logdir / "closeouts.jsonl"
cards = [json.loads(l) for l in co.read_text().splitlines() if l.strip()]
for c in cards:
    c["ts"] = days[c["serial"]][-1]
co.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cards))

# Verify the R14 pattern, and leave the escalation candidate active.
pats = call("/api/patterns")["patterns"]
for p in pats:
    if "R14" in p["parts"]:
        call("/api/patterns", {"id": p["id"], "status": "verified"})
board("10000000000014", "DEMO-014")
print("seeded:", {d: len(r) for d, r in by_day.items()}, "closeouts:", len(cards), "patterns:", [(p["title"], p["status"]) for p in call("/api/patterns")["patterns"]])
