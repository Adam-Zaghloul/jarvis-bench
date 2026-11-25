"""Known-good reference tables, known-good samples, range checks and doc conflicts.

Files (DATA_DIR defaults to jarvis/):
    reference/<board_type>[_<rev>].csv            ranges YOU typed: test_point,mode,min,max,source,note
    reference/<board_type>[_<rev>].draft.csv      candidate rows from the docs, min/max blank (never used for checks)
    reference/<board_type>[_<rev>].samples.jsonl  readings captured by "Mark board known-good" (separate, never merged)
Values in min/max use base units (V, ohm, A, F, Hz). Suffixes k/M/m/u/n/p are accepted.
"""
import csv
import json
import re
from pathlib import Path

import parse
import store

REF_DIR = store.DATA_DIR / "reference"
COLUMNS = ["test_point", "mode", "min", "max", "source", "note"]
_SAFE = re.compile(r"[^A-Za-z0-9_-]")
_SUFFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6}


def _key(board_type, rev=None):
    bt = _SAFE.sub("", board_type or "DEMO") or "DEMO"
    rv = _SAFE.sub("", rev or "")
    return bt + ("_" + rv if rv else "")


def num(s):
    """'4.7k' -> 4700.0, '600m' -> 0.6, '' -> None."""
    s = (s or "").strip().replace(",", ".")
    if not s:
        return None
    m = re.match(r"^([-+]?\d+(?:\.\d+)?)\s*([pnuµmkKM]?)\s*(?:V|A|ohm|Ω|F|Hz)?$", s)
    if not m:
        return None
    return float(m.group(1)) * _SUFFIX.get(m.group(2), 1)


def files_for(board_type, rev=None):
    """Most specific first: DEMO_A.csv, then DEMO.csv."""
    keys = [_key(board_type, rev)] + ([_key(board_type)] if rev else [])
    return [REF_DIR / (k + ".csv") for k in keys]


def load_ranges(board_type, rev=None):
    rows = []
    for p in files_for(board_type, rev):
        if not p.exists():
            continue
        with open(p, newline="", encoding="utf-8-sig") as f:
            for i, r in enumerate(csv.DictReader(f), 2):
                tp = (r.get("test_point") or "").strip()
                if not tp or tp.startswith("#"):
                    continue
                lo, hi = num(r.get("min")), num(r.get("max"))
                if lo is None and hi is None:
                    continue  # no range typed yet
                rows.append({"test_point": parse._norm_tp(tp), "mode": (r.get("mode") or "").strip().lower(),
                             "min": lo, "max": hi, "source": (r.get("source") or "").strip(),
                             "note": (r.get("note") or "").strip(), "file": p.name, "line": i})
    return rows


def samples_path(board_type, rev=None):
    return REF_DIR / (_key(board_type, rev) + ".samples.jsonl")


def load_samples(board_type, rev=None):
    p = samples_path(board_type, rev)
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def sample_ranges(board_type, rev=None):
    """(test_point, mode) -> {min, max, n, serials} built only from known-good samples."""
    agg = {}
    for s in load_samples(board_type, rev):
        k = (s["test_point"], s["mode"])
        a = agg.setdefault(k, {"test_point": s["test_point"], "mode": s["mode"], "unit": s["unit"],
                               "min": s["value"], "max": s["value"], "n": 0, "serials": []})
        a["min"], a["max"] = min(a["min"], s["value"]), max(a["max"], s["value"])
        a["n"] += 1
        if s["serial"] not in a["serials"]:
            a["serials"].append(s["serial"])
    return agg


def check(reading, board_type, rev=None):
    """Range-check one parsed reading. Returns {status: in|out|none, range..., sample...}."""
    if not reading:
        return None
    res = {"status": "none"}
    for r in load_ranges(board_type, rev):
        if r["test_point"] == reading["test_point"] and (not r["mode"] or r["mode"] == reading["mode"]):
            lo, hi, v = r["min"], r["max"], reading["value"]
            ok = (lo is None or v >= lo) and (hi is None or v <= hi)
            res = {"status": "in" if ok else "out", "min": lo, "max": hi, "unit": reading["unit"],
                   "source": r["source"] or "%s line %d" % (r["file"], r["line"]), "note": r["note"],
                   "ref": "%s#L%d" % (r["file"], r["line"])}
            break
    s = sample_ranges(board_type, rev).get((reading["test_point"], reading["mode"]))
    if s:
        v = reading["value"]
        res["sample"] = {"min": s["min"], "max": s["max"], "n": s["n"], "boards": len(s["serials"]),
                         "inside": s["min"] <= v <= s["max"]}
    return res


def mark_known_good(serial, board_type, rev=None):
    """Save every parsed reading of this board (all days) as known-good samples. Returns count added."""
    REF_DIR.mkdir(parents=True, exist_ok=True)
    existing = {(s["serial"], s["ts"], s["test_point"]) for s in load_samples(board_type, rev)}
    added = []
    for d in store.log_dates():
        for e in store.read_log(d):
            r = e.get("reading")
            if e.get("serial") != serial or not r:
                continue
            k = (serial, e["ts"], r["test_point"])
            if k in existing:
                continue
            added.append({"serial": serial, "ts": e["ts"], "board_type": board_type, "rev": rev or "",
                          "test_point": r["test_point"], "mode": r["mode"], "value": r["value"], "unit": r["unit"],
                          "raw": e["text"]})
    if added:
        with open(samples_path(board_type, rev), "a", encoding="utf-8") as f:
            for a in added:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
    return len(added)


# ---------------------------------------------------------------- doc conflicts

_DOC_NUM = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(mV|V|kΩ|MΩ|Ω|k|M|mA|µA|A|MHz|kHz|Hz|nF|µF|pF)(?![\w])")
_DOC_UNIT = {"mV": ("V", 1e-3), "V": ("V", 1), "kΩ": ("ohm", 1e3), "MΩ": ("ohm", 1e6), "Ω": ("ohm", 1),
             "k": ("ohm", 1e3), "M": ("ohm", 1e6), "mA": ("A", 1e-3), "µA": ("A", 1e-6), "A": ("A", 1),
             "MHz": ("Hz", 1e6), "kHz": ("Hz", 1e3), "Hz": ("Hz", 1), "nF": ("F", 1e-9), "µF": ("F", 1e-6),
             "pF": ("F", 1e-12)}
_MODE_UNIT = {"dcv": "V", "acv": "V", "diode": "V", "resistance": "ohm", "current": "A",
              "frequency": "Hz", "capacitance": "F"}


def _doc_line(source):
    """'test-points.md#L14' -> (path, line text). None if the source isn't a repo doc line."""
    m = re.match(r"^([\w./-]+\.md)#L(\d+)", source or "")
    if not m:
        return None
    try:
        p = store.resolve_repo_path(m.group(1))
        lines = p.read_text(encoding="utf-8").splitlines()
        n = int(m.group(2))
        return m.group(1), n, lines[n - 1] if 0 < n <= len(lines) else ""
    except (ValueError, FileNotFoundError, OSError):
        return None


def conflicts(board_type, rev=None):
    """Reference rows whose cited doc line states a value outside the typed range."""
    out = []
    for r in load_ranges(board_type, rev):
        d = _doc_line(r["source"])
        if not d:
            continue
        path, n, text = d
        want = _MODE_UNIT.get(r["mode"])
        vals = []
        for v, u in _DOC_NUM.findall(text):
            base, mult = _DOC_UNIT[u]
            if want and base != want:
                continue
            vals.append(float(v) * mult)
        outside = [v for v in vals if (r["min"] is not None and v < r["min"]) or (r["max"] is not None and v > r["max"])]
        if vals and len(outside) == len(vals):
            out.append({"test_point": r["test_point"], "mode": r["mode"], "min": r["min"], "max": r["max"],
                        "ref": "%s#L%d" % (r["file"], r["line"]), "doc": "%s#L%d" % (path, n),
                        "doc_text": text.strip()[:300], "doc_values": vals})
    return out


def overview(board_type, rev=None):
    ranges = load_ranges(board_type, rev)
    samples = sample_ranges(board_type, rev)
    draft = REF_DIR / (_key(board_type, rev) + ".draft.csv")
    return {"files": [p.name for p in files_for(board_type, rev) if p.exists()],
            "expected_file": files_for(board_type, rev)[0].name,
            "ranges": ranges,
            "samples": sorted(samples.values(), key=lambda s: (s["test_point"], s["mode"])),
            "conflicts": conflicts(board_type, rev),
            "draft": draft.name if draft.exists() else None}
