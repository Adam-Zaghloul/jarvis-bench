"""Phase 4: time-on-board, weekly review, competency filter, work-instruction drafts, escalation handoff."""
import collections
import datetime as dt
import json
import re
import statistics

import closeout
import store

GAP_LIMIT_S = 30 * 60
WEEK_RE = re.compile(r"^(\d{4})-W?(\d{1,2})$")


def _ts(s):
    return dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


def time_on_board(entries):
    """Seconds from first to last entry, excluding any gap over 30 min between consecutive entries."""
    ts = sorted(_ts(e["ts"]) for e in entries if e.get("ts"))
    total = 0
    for a, b in zip(ts, ts[1:]):
        gap = (b - a).total_seconds()
        if gap <= GAP_LIMIT_S:
            total += gap
    return int(total)


def fmt_dur(sec):
    if sec is None:
        return "—"
    m = int(round(sec / 60.0))
    return "%d min" % m if m < 60 else "%d h %02d min" % (m // 60, m % 60)


def all_entries():
    out = []
    for d in store.log_dates():
        out += store.read_log(d)
    return out


def board_entries(serial):
    return [e for e in all_entries() if e.get("serial") == serial]


# ---------------------------------------------------------------- weeks

def parse_week(s=None):
    if not s:
        y, w, _ = dt.date.today().isocalendar()
        return y, w
    m = WEEK_RE.match(s)
    if not m:
        raise ValueError("Week must look like 2026-48.")
    y, w = int(m.group(1)), int(m.group(2))
    if not 1 <= w <= 53:
        raise ValueError("Bad week number.")
    return y, w


def week_bounds(y, w):
    start = dt.date.fromisocalendar(y, w, 1)
    return start, start + dt.timedelta(days=6)


def week_label(y, w):
    return "%04d-%02d" % (y, w)


def _in_week(ts, y, w):
    d = dt.date.fromisoformat(ts[:10])
    iy, iw, _ = d.isocalendar()
    return (iy, iw) == (y, w)


# ---------------------------------------------------------------- competency filter

# Identifiers that must never appear in the competency log (career record, written generally).
_BANNED = [
    (re.compile(r"\b[A-Z]{1,3}\d{1,4}\b"), "reference designator"),
    (re.compile(r"\b\d{5,}\b"), "serial / long number"),
    (re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b"), "ticket or part ID"),
    (re.compile(r"\b\d+(?:\.\d+)?\s?(?:k|M|m|µ|u|n|p)?(?:Ω|ohm|V|A|F|Hz)\b", re.I), "part value"),
    # Add your company, product, tool and ticket-project names here.
    (re.compile(r"\b(DEMO|ACME|ATmega\w*|STM32\w*|PIC\d+\w*|LM\d+\w*|LT\d+|TPS\d+\w*|DRV\w*)\b", re.I),
     "product / internal name"),
]


def competency_filter(items):
    keep, dropped = [], []
    for it in items or []:
        it = (it or "").strip()
        if not it:
            continue
        hit = next((why for rx, why in _BANNED if rx.search(it)), None)
        (dropped if hit else keep).append({"text": it, "reason": hit} if hit else it)
    return keep, dropped


# ---------------------------------------------------------------- weekly review

def week_stats(y, w):
    es = [e for e in all_entries() if e.get("ts") and _in_week(e["ts"], y, w)]
    by_board = collections.OrderedDict()
    for e in es:
        by_board.setdefault(e["serial"], []).append(e)
    boards = []
    for serial, ent in by_board.items():
        last = next((x["status"] for x in reversed(ent) if x.get("status")), None)
        boards.append({"serial": serial, "board_type": ent[0].get("board_type"), "rev": ent[-1].get("rev", ""),
                       "entries": len(ent), "status": last, "seconds": time_on_board(ent)})
    counts = collections.Counter(b["status"] or "open" for b in boards)
    cos = [c for c in closeout.load() if _in_week(c["ts"], y, w)]
    sym = collections.Counter(c["symptom"].strip().rstrip(".") for c in cos if c.get("symptom"))
    cause = collections.Counter(c["root_cause"].strip().rstrip(".") for c in cos if c.get("root_cause"))
    parts = collections.Counter(p.strip() for c in cos for p in re.split(r"[,;]", c.get("parts") or "") if p.strip())
    rated = [c for c in cos if c.get("hypothesis_match") in (True, False)]
    hits = sum(1 for c in rated if c["hypothesis_match"])
    week_ids = {c["id"] for c in cos}
    pats = [p for p in closeout.patterns() if p["status"] != "dismissed" and any(x["id"] in week_ids for x in p["cases"])]
    secs = [b["seconds"] for b in boards if b["seconds"] > 0]
    open_now = [b for b in boards if b["status"] not in store.CLOSED]
    return {
        "week": week_label(y, w), "from": week_bounds(y, w)[0].isoformat(), "to": week_bounds(y, w)[1].isoformat(),
        "boards": boards, "entries": len(es),
        "counts": {k: counts.get(k, 0) for k in ("fixed", "escalated", "scrap", "open")},
        "top_symptoms": sym.most_common(5), "top_causes": cause.most_common(5), "top_parts": parts.most_common(5),
        "closeouts": len(cos), "patterns": [{"title": p["title"], "status": p["status"], "cases": len(p["cases"])} for p in pats],
        "open_boards": [{"serial": b["serial"], "board_type": b["board_type"], "status": b["status"] or "no status"} for b in open_now],
        "median_seconds": int(statistics.median(secs)) if secs else None,
        "hit_rate": {"rated": len(rated), "matched": hits, "pct": round(100.0 * hits / len(rated)) if rated else None},
    }


def week_markdown(st, competency, dropped):
    L = ["# Weekly review — %s (%s to %s)" % (st["week"], st["from"], st["to"]), ""]
    c = st["counts"]
    L += ["## Boards", "", "%d boards worked, %d entries. Fixed %d · escalated %d · scrap %d · open %d." % (
        len(st["boards"]), st["entries"], c["fixed"], c["escalated"], c["scrap"], c["open"]), ""]
    L += ["| Board | Status | Time on board | Entries |", "|---|---|---|---|"]
    L += ["| %s %s | %s | %s | %d |" % (b["board_type"], b["serial"], b["status"] or "open", fmt_dur(b["seconds"]), b["entries"])
          for b in st["boards"]] or ["| (none) | | | |"]
    L += ["", "Median time on board: %s (first to last entry, gaps over 30 min excluded)." % fmt_dur(st["median_seconds"]), ""]
    L += ["## Top symptoms (confirmed close-outs)", ""] + (["- %s (%d)" % kv for kv in st["top_symptoms"]] or ["- (none)"])
    L += ["", "## Top causes", ""] + (["- %s (%d)" % kv for kv in st["top_causes"]] or ["- (none)"])
    if st["top_parts"]:
        L += ["", "Parts replaced: " + ", ".join("%s ×%d" % kv for kv in st["top_parts"])]
    L += ["", "## Patterns", ""] + (["- %s — %s, %d cases" % (p["title"], p["status"], p["cases"]) for p in st["patterns"]] or ["- (none)"])
    L += ["", "## Open boards", ""] + (["- %s %s (%s)" % (b["board_type"], b["serial"], b["status"]) for b in st["open_boards"]] or ["- (none)"])
    hr = st["hit_rate"]
    L += ["", "## Predict-first hit rate", "",
          ("%d of %d hypotheses matched the root cause (%d%%)." % (hr["matched"], hr["rated"], hr["pct"])) if hr["rated"]
          else "No rated hypotheses this week."]
    L += ["", "## Competency log", "", "_Written generally for career records: no part numbers, serials, internal or product names, ticket IDs._", ""]
    L += ["- " + x for x in competency] or ["- (none)"]
    if dropped:
        L += ["", "_%d item(s) removed because they contained identifiers (%s)._" % (
            len(dropped), ", ".join(sorted({d["reason"] for d in dropped})))]
    L.append("")
    return "\n".join(L)


def week_brain_context(y, w):
    es = [e for e in all_entries() if e.get("ts") and _in_week(e["ts"], y, w)]
    cos = [c for c in closeout.load() if _in_week(c["ts"], y, w)]
    keep = ("kind", "text", "status")
    lines = ["Bench log entries this week (identifiers will be stripped from your output, write generally):"]
    lines += [json.dumps({k: e.get(k) for k in keep if e.get(k)}, ensure_ascii=False) for e in es]
    lines += ["", "Confirmed close-outs this week:"]
    lines += [json.dumps({k: c.get(k) for k in ("symptom", "root_cause", "fix", "outcome", "closed_status")}, ensure_ascii=False)
              for c in cos]
    return "\n".join(lines), len(es) + len(cos)
