"""JARVIS V2 API routes. server.py checks these first; each returns (http_code, payload).

GET handlers get (query: dict, handler). POST handlers get (body: dict, handler).
"""
import json

import brain
import closeout
import parse
import reference
import store


def _active_or_400():
    a = store.get_active()
    if not a:
        raise ValueError("No active board. Set the board first.")
    return a


def _board_log(serial):
    """Every entry for one board, across all days, in order."""
    out = []
    for d in store.log_dates():
        out += [e for e in store.read_log(d) if e.get("serial") == serial]
    return out


def _annotate(entries):
    """Add range checks to entries that carry a parsed reading (computed, never stored)."""
    for e in entries:
        r = e.get("reading")
        if r:
            e["check"] = reference.check(r, e.get("board_type"), e.get("rev"))
            e["reading_display"] = parse.fmt(r["value"], r["unit"])
    return entries


def _brain_data(mode, question, ctx):
    result = None
    for ev in brain.ask(mode, question, ctx):
        if ev["type"] == "error":
            return None, ev
        if ev["type"] == "done":
            result = ev
    data = (result or {}).get("data")
    store.cite(mode, json.dumps(data, ensure_ascii=False) if data else "")
    return data, None


def _jsonl(entries):
    keep = ("ts", "board_type", "rev", "serial", "kind", "text", "status", "reading")
    return "\n".join(json.dumps({k: e.get(k) for k in keep if e.get(k) is not None}, ensure_ascii=False)
                     for e in entries)


# ---------------------------------------------------------------- Phase 1: board, log, parse, reference

def post_board(body, h):
    a = store.set_active(body.get("board_type"), body.get("serial"), body.get("rev"), body.get("ticket"))
    store.usage("scan" if body.get("via") == "scan" else "board")
    return 200, {"active": a}


def post_parse(body, h):
    """Preview chip: what the quick-log line would be stored as. Nothing is saved."""
    text = (body.get("text") or "").strip()
    r = parse.parse_reading(text)
    a = store.get_active()
    chk = reference.check(r, a["board_type"], a.get("rev")) if (r and a) else None
    return 200, {"reading": r, "display": parse.fmt(r["value"], r["unit"]) if r else None, "check": chk}


def _clean_photos(ps):
    out = []
    for p in ps or []:
        if not isinstance(p, str) or not __import__("re").match(r"^jarvis/logs/photos/\d{4}-\d{2}-\d{2}/[\w.-]+\.(jpg|png)$", p):
            raise ValueError("Bad photo path.")
        store.resolve_any(p)  # must exist
        out.append(p)
    return out


def post_log(body, h):
    body = dict(body, photos=_clean_photos(body.get("photos")))
    e = store.add_entry(body.get("text"), body.get("kind"), body.get("status"),
                        parse_reading=body.get("parse", True) is not False,
                        photos=body.get("photos"), serial=body.get("serial"), source=body.get("source"))
    _annotate([e])
    return 200, {"entry": e, "closeout_needed": e.get("status") in store.CLOSED}


def get_log(q, h):
    date = q.get("date") or store._today()
    return 200, {"date": date, "entries": _annotate(store.read_log(date)), "dates": store.log_dates()}


def get_reference(q, h):
    a = store.get_active() or {"board_type": q.get("board_type") or "DEMO", "rev": q.get("rev") or ""}
    o = reference.overview(a["board_type"], a.get("rev"))
    o["board_type"], o["rev"] = a["board_type"], a.get("rev", "")
    return 200, o


def post_known_good(body, h):
    a = _active_or_400()
    if body.get("serial") != a["serial"]:
        raise ValueError("Confirm the serial of the board you are marking known-good.")
    n = reference.mark_known_good(a["serial"], a["board_type"], a.get("rev"))
    store.usage("known_good")
    return 200, {"added": n, "file": reference.samples_path(a["board_type"], a.get("rev")).name}


def get_timeline(q, h):
    serial = q.get("serial") or (store.get_active() or {}).get("serial")
    if not serial:
        raise ValueError("No board.")
    return 200, {"serial": serial, "entries": _annotate(_board_log(serial)), "closeouts": closeout.for_serial(serial)}


# ---------------------------------------------------------------- Phase 1: close-out + patterns

def post_closeout_draft(body, h):
    """Brain pre-fill. Returns a DRAFT only; nothing is written."""
    a = _active_or_400()
    serial = body.get("serial") or a["serial"]
    entries = _board_log(serial)
    if not entries:
        raise ValueError("No log entries for %s." % serial)
    data, err = _brain_data("closeout", "Draft the close-out card for this board.",
                            "Board %s %s rev %s\nBench log (JSONL):\n%s" % (
                                entries[-1].get("board_type"), serial, entries[-1].get("rev", "?"), _jsonl(entries)))
    store.usage("closeout_draft")
    if err:
        return 200, {"error": err}
    closed = next((e["status"] for e in reversed(entries) if e.get("status") in store.CLOSED), None)
    draft = dict(data or {}, ticket=entries[-1].get("ticket", "") or a.get("ticket", ""))
    draft["root_cause_status"] = "suspected"  # default stays suspected until YOU mark it confirmed
    if data and data.get("root_cause_status") == "confirmed":
        draft["brain_suggests_confirmed"] = True
    hyp = [x for x in _hypotheses() if x.get("serial") == serial]
    return 200, {"draft": draft, "serial": serial, "closed_status": closed, "board_type": entries[-1].get("board_type"),
                 "rev": entries[-1].get("rev", ""), "hypotheses": hyp, "saved": False}


def post_closeout_confirm(body, h):
    a = store.get_active() or {}
    serial = body.get("serial")
    entries = _board_log(serial) if serial else []
    if not entries:
        raise ValueError("Unknown board.")
    closed = body.get("closed_status") or next((e["status"] for e in reversed(entries)
                                                if e.get("status") in store.CLOSED), None)
    c = closeout.save(body.get("card") or {}, serial, entries[-1].get("board_type"), entries[-1].get("rev", ""),
                      closed, body.get("hypothesis"))
    store.usage("closeout_confirm")
    return 200, {"closeout": c, "saved": True}


def get_closeouts(q, h):
    s = q.get("serial")
    return 200, {"closeouts": closeout.for_serial(s) if s else closeout.load()}


def get_patterns(q, h):
    return 200, {"patterns": closeout.patterns()}


def post_pattern(body, h):
    st = closeout.set_pattern(body.get("id"), body.get("status"))
    store.usage("pattern")
    return 200, {"state": st}


# ---------------------------------------------------------------- hypotheses (Phase 2, used by close-out)

def _hyp_path():
    return store.LOG_DIR / "hypotheses.jsonl"


def _hypotheses():
    p = _hyp_path()
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def post_hypothesis(body, h):
    hyp = (body.get("hypothesis") or "").strip()
    if not hyp:
        raise ValueError("Empty hypothesis.")
    rec = {"ts": store._now(), "serial": body.get("serial") or "", "question": (body.get("question") or "")[:2000],
           "hypothesis": hyp[:500]}
    store.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_hyp_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    store.usage("hypothesis")
    return 200, {"saved": True}


CITE_RE = __import__("re").compile(r"\[\[([^\]\n]{1,300})\]\]")


def post_feedback(body, h):
    rating = body.get("rating")
    if rating not in ("up", "down"):
        raise ValueError("rating must be up or down")
    store.usage("feedback_" + rating)
    if rating == "up":
        return 200, {"saved": True}
    answer = body.get("answer") or ""
    rec = {"ts": store._now(), "question": (body.get("question") or "")[:4000], "answer": answer[:20000],
           "citations": CITE_RE.findall(answer), "reason": (body.get("reason") or "")[:1000],
           "session_id": body.get("session_id") or "", "status": "candidate"}
    d = store.DATA_DIR / "evals"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "candidates.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return 200, {"saved": True, "saved_to": "jarvis/evals/candidates.jsonl"}


# ---------------------------------------------------------------- Phase 4: daily work

import daily  # noqa: E402

DRAFTS_DIR = store.DATA_DIR / "drafts"


def _plain(text):
    """Text that leaves JARVIS: turn [[path#x]] into '(see path)'."""
    return CITE_RE.sub(lambda m: " (see %s)" % m.group(1).split("#")[0], text or "")
DRAFT_BANNER = "DRAFT — not reviewed. Do not use until reviewed."


def get_tob(q, h):
    serial = q.get("serial") or (store.get_active() or {}).get("serial")
    if not serial:
        return 200, {"seconds": None}
    s = daily.time_on_board(daily.board_entries(serial))
    return 200, {"serial": serial, "seconds": s, "display": daily.fmt_dur(s)}


def post_handoff(body, h):
    serial = body.get("serial")
    entries = daily.board_entries(serial) if serial else []
    if not entries:
        raise ValueError("Unknown board.")
    cos = [c for c in closeout.for_serial(serial) if c.get("closed_status") == "escalated"]
    last_status = next((e["status"] for e in reversed(entries) if e.get("status")), None)
    if not cos and last_status != "escalated":
        raise ValueError("Handoff notes are for boards closed as escalated.")
    ctx = "Board %s %s rev %s (escalated)\nBench log (JSONL):\n%s\n\nClose-out card:\n%s" % (
        entries[-1].get("board_type"), serial, entries[-1].get("rev", "?"), _jsonl(entries),
        json.dumps(cos[-1] if cos else {"note": "no confirmed close-out yet"}, ensure_ascii=False))
    data, err = _brain_data("handoff", "Write the escalation handoff note.", ctx)
    if err:
        return 200, {"error": err}
    text = _plain((data or {}).get("text", ""))
    store.usage("handoff")
    return 200, {"serial": serial, "text": text, "copy_only": True}


def get_weekly(q, h):
    y, w = daily.parse_week(q.get("week"))
    p = store.DEBRIEF_DIR / ("week-%s.md" % daily.week_label(y, w))
    today = __import__("datetime").date.today()
    ty, tw, wd = today.isocalendar()
    this_week = store.DEBRIEF_DIR / ("week-%s.md" % daily.week_label(ty, tw))
    return 200, {"week": daily.week_label(y, w), "saved": p.read_text(encoding="utf-8") if p.exists() else None,
                 "nudge": wd == 5 and not this_week.exists(), "this_week": daily.week_label(ty, tw)}


def post_weekly(body, h):
    y, w = daily.parse_week(body.get("week"))
    st = daily.week_stats(y, w)
    ctx, n = daily.week_brain_context(y, w)
    competency, dropped, err = [], [], None
    if n:
        data, err = _brain_data("competency", "List the techniques and skills used this week.", ctx)
        competency, dropped = daily.competency_filter((data or {}).get("items"))
    md = daily.week_markdown(st, competency, dropped)
    store.DEBRIEF_DIR.mkdir(parents=True, exist_ok=True)
    out = store.DEBRIEF_DIR / ("week-%s.md" % st["week"])
    out.write_text(md, encoding="utf-8")
    store.usage("weekly")
    return 200, {"week": st["week"], "stats": st, "competency": competency, "dropped": dropped, "markdown": md,
                 "saved": str(out), "brain_error": err}


def post_workinstruction(body, h):
    pid = body.get("pattern_id") or ""
    pat = next((p for p in closeout.patterns() if p["id"] == pid), None)
    if not pat:
        raise ValueError("Unknown pattern.")
    if pat["status"] != "verified":
        raise ValueError("Only a verified pattern can produce a work-instruction draft.")
    data, err = _brain_data("workinstruction", "Draft the work instruction for this verified pattern.",
                            json.dumps(pat, ensure_ascii=False, indent=1))
    if err:
        return 200, {"error": err}
    text = _plain((data or {}).get("text", "")).strip()
    if not text.startswith(DRAFT_BANNER):
        text = DRAFT_BANNER + "\n\n" + text
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    out = DRAFTS_DIR / ("%s-%s.md" % (pid, store._today()))
    out.write_text(text + "\n\n---\nGenerated by JARVIS from pattern %s (%d close-outs). Not part of the repo docs.\n" % (
        pid, len(pat["cases"])), encoding="utf-8")
    store.usage("workinstruction")
    return 200, {"text": text, "saved": str(out)}


# ---------------------------------------------------------------- Phase 5: capture

import capture  # noqa: E402


def post_photo(body, h):
    path, n = capture.save_photo(body.get("data"))
    store.usage("photo")
    return 200, {"path": path, "bytes": n}


# ---------------------------------------------------------------- Phase 6: health

import backup  # noqa: E402
import health  # noqa: E402


def get_audit(q, h):
    return 200, health.audit()


def get_usage(q, h):
    return 200, health.usage_week(q.get("week"))


def get_backup(q, h):
    return 200, backup.status()


def get_token(q, h):
    # Same-origin page only (Host check + no CORS headers); other sites can't read this response.
    return 200, {"token": capture.api_token()}


GET = {
    "/api/log": get_log,
    "/api/reference": get_reference,
    "/api/timeline": get_timeline,
    "/api/closeouts": get_closeouts,
    "/api/patterns": get_patterns,
    "/api/tob": get_tob,
    "/api/weekly": get_weekly,
    "/api/token": get_token,
    "/api/audit": get_audit,
    "/api/usage": get_usage,
    "/api/backup": get_backup,
}
POST = {
    "/api/board": post_board,
    "/api/parse": post_parse,
    "/api/log": post_log,
    "/api/reference/known-good": post_known_good,
    "/api/closeout/draft": post_closeout_draft,
    "/api/closeout/confirm": post_closeout_confirm,
    "/api/patterns": post_pattern,
    "/api/hypothesis": post_hypothesis,
    "/api/feedback": post_feedback,
    "/api/handoff": post_handoff,
    "/api/weekly": post_weekly,
    "/api/workinstruction": post_workinstruction,
    "/api/photo": post_photo,
}
