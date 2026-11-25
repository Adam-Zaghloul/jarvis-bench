"""JARVIS V2 Phase 6 — health: doc audit (report only, never edits), weekly usage counts.

Nothing here writes to the docs. The audit reads the repo; usage reads jarvis/logs/usage.jsonl,
citations.jsonl and the bench logs.
"""
import collections
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import unquote

import daily
import store

# Build specs describe JARVIS itself (and future paths); they aren't bench docs.
AUDIT_SKIP = re.compile(r"^JARVIS_.*\.md$")
_MD_LINK = re.compile(r"(?<!!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_TICK = re.compile(r"`([^`\n]{2,200})`")
_PLACEHOLDER = re.compile(r"[<>{}*]|YYYY|MM-DD|XXXX|\.\.\.|…")
# JARVIS's own runtime data: created on first use, so "doesn't exist yet" isn't a broken reference.
_RUNTIME = re.compile(r"^jarvis/(logs|debriefs|drafts|evals/results|settings\.json)")


def _md_docs():
    for rel, p in store.iter_docs():
        if rel.startswith("jarvis/") or not rel.lower().endswith(".md") or AUDIT_SKIP.match(rel.split("/")[-1]):
            continue
        yield rel, p


def _exists(rel_from, target):
    """target relative to the citing file's folder, or to the repo root (both styles are used)."""
    repo = store.REPO.resolve()
    base = (repo / rel_from).parent
    for root in (base, repo):
        q = (root / target).resolve()
        try:
            q.relative_to(repo)
        except ValueError:
            continue
        if q.exists():
            return True
    return False


def _first_dir_exists(rel_from, target):
    seg = target.split("/")[0]
    return (store.REPO / seg).is_dir() or ((store.REPO / rel_from).parent / seg).is_dir()


def audit(now=None):
    now = now or dt.datetime.now()
    broken, missing = [], []
    for rel, p in _md_docs():
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        in_code = False
        for i, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                continue
            for t in _MD_LINK.findall(line):
                if re.match(r"^(https?:|mailto:|#)", t):
                    continue
                path = unquote(t.split("#")[0])
                if path and not _exists(rel, path):
                    broken.append({"path": rel, "line": i, "target": t})
            for t in _TICK.findall(line):
                t = t.strip()
                if "/" not in t or " " in t or _PLACEHOLDER.search(t) or _RUNTIME.match(t) or re.match(r"^(~|/|\.\./|https?:|[A-Za-z]:)", t):
                    continue
                if not re.match(r"^[\w.-]+/", t):          # must start like a folder name: reference/…, cases/x.md
                    continue
                t = t.rstrip(".,;:")
                if not _first_dir_exists(rel, t):
                    missing.append({"path": rel, "line": i, "ref": t, "why": "folder %s/ doesn't exist" % t.split("/")[0]})
                elif re.search(r"\.\w{1,5}$", t) and not _exists(rel, t):
                    missing.append({"path": rel, "line": i, "ref": t, "why": "file doesn't exist"})

    # Not cited in 30 days (brain citations recorded by store.cite).
    cutoff = (now - dt.timedelta(days=30)).isoformat(timespec="seconds")
    cited, first = set(), None
    for r in _jsonl(store.LOG_DIR / "citations.jsonl"):
        first = first or r.get("ts")
        if r.get("ts", "") >= cutoff:
            cited.update(r.get("paths") or [])
    docs = store.doc_index()
    uncited = [d for d in docs if d["path"] not in cited and not AUDIT_SKIP.match(d["path"].split("/")[-1])
               and d["class"] != "jarvis" and not d["path"].startswith("jarvis/")]
    by_class = collections.defaultdict(list)
    for d in uncited:
        by_class[d["class"]].append(d["path"])
    tracking_days = None
    if first:
        tracking_days = (now - dt.datetime.fromisoformat(first)).days

    # Oldest files by last modification (on this machine).
    ages = []
    for rel, p in _md_docs():
        try:
            m = dt.datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            continue
        ages.append({"path": rel, "modified": m.date().isoformat(), "days": (now - m).days})
    ages.sort(key=lambda a: a["modified"])
    return {"broken_links": broken, "missing_paths": missing,
            "uncited": dict(sorted(by_class.items())), "uncited_count": len(uncited), "docs": len(docs),
            "citations_since": first[:10] if first else None, "tracking_days": tracking_days,
            "oldest": ages[:10], "md_files": len(ages)}


def _jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


# Every feature that records a usage event, in the order the panel shows them.
FEATURES = [
    ("ask", "Ask"), ("seen_fast", "Seen before (keyword)"), ("seen_brain", "Seen before (brain)"),
    ("debrief", "Debrief"), ("log_api", "Quick-log from another app"), ("scan", "Scanner board switch"),
    ("photo", "Photos"), ("closeout_draft", "Close-out draft"), ("closeout_confirm", "Close-out saved"),
    ("known_good", "Mark known-good"), ("pattern", "Pattern verify/dismiss"), ("hypothesis", "Predict first"),
    ("feedback_up", "👍"), ("feedback_down", "👎"), ("handoff", "Escalation handoff"),
    ("weekly", "Weekly review"), ("workinstruction", "Work-instruction draft"),
]


def usage_week(week=None):
    y, w = daily.parse_week(week)
    ev = collections.Counter()
    for r in _jsonl(store.LOG_DIR / "usage.jsonl"):
        if r.get("ts") and daily._in_week(r["ts"], y, w):
            ev[r.get("event")] += 1
    entries = [e for e in daily.all_entries() if e.get("ts") and daily._in_week(e["ts"], y, w)]
    up, down = ev["feedback_up"], ev["feedback_down"]
    rows = [{"event": k, "label": lbl, "count": ev[k]} for k, lbl in FEATURES]
    unused = [r["label"] for r in rows if not r["count"] and r["event"] not in ("feedback_up", "feedback_down")]
    if not up and not down:
        unused.append("👍/👎 feedback")
    return {"week": "%d-%02d" % (y, w),
            "entries": len(entries), "boards": len({e.get("serial") for e in entries}),
            "questions": ev["ask"], "seen": ev["seen_fast"] + ev["seen_brain"], "debriefs": ev["debrief"],
            "thumbs_up": up, "thumbs_down": down,
            "thumbs_ratio": round(up / (up + down), 2) if (up + down) else None,
            "features": rows, "unused": unused}
