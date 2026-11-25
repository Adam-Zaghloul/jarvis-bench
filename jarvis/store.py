"""JARVIS data layer: bench logs, active board, doc index, fast keyword search.

Writes happen only under DATA_DIR/logs and DATA_DIR/debriefs (DATA_DIR defaults to jarvis/).
"""
import datetime as dt
import json
import os
import re
import threading
import unicodedata
from pathlib import Path

JARVIS_DIR = Path(__file__).resolve().parent
REPO = JARVIS_DIR.parent
DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR") or JARVIS_DIR)
LOG_DIR = DATA_DIR / "logs"
DEBRIEF_DIR = DATA_DIR / "debriefs"

KINDS = ("measurement", "action", "observation", "result")
STATUSES = ("fixed", "escalated", "scrap", "open")
CLOSED = ("fixed", "escalated", "scrap")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SERIAL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
DOC_EXT = {".md", ".pdf", ".txt", ".csv", ".c", ".h", ".png", ".jsonl"}
TEXT_EXT = {".md", ".txt", ".csv", ".c", ".h", ".jsonl"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", "docs"}   # docs/ = README images and the tools that make them

_lock = threading.Lock()


def _today():
    return dt.date.today().isoformat()


def _now():
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- active board

def get_active():
    try:
        d = json.loads((LOG_DIR / "active.json").read_text(encoding="utf-8"))
        if d.get("serial"):
            return d
    except (OSError, ValueError):
        pass
    return None


REV_RE = re.compile(r"^[A-Za-z0-9._-]{0,10}$")
TICKET_RE = re.compile(r"^[A-Za-z0-9._-]{0,40}$")


def set_active(board_type, serial, rev=None, ticket=None):
    board_type = (board_type or "DEMO").strip()[:20] or "DEMO"
    serial = (serial or "").strip()
    rev = (rev or "").strip()
    ticket = (ticket or "").strip()
    if not SERIAL_RE.match(serial):
        raise ValueError("Serial must be 1-40 letters/digits (dash and underscore allowed).")
    if not REV_RE.match(rev):
        raise ValueError("Revision: up to 10 letters/digits.")
    if not TICKET_RE.match(ticket):
        raise ValueError("Ticket ID: letters, digits and dashes only (e.g. DEMO-27826).")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    d = {"board_type": board_type, "serial": serial, "rev": rev, "ticket": ticket, "since": _now()}
    (LOG_DIR / "active.json").write_text(json.dumps(d), encoding="utf-8")
    return d


# ---------------------------------------------------------------- usage (local only, Phase 6 panel)

def usage(event, **kw):
    """Count one local event (no question text, no content). Never fails the caller."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": _now(), "event": event}
        rec.update({k: v for k, v in kw.items() if isinstance(v, (int, float, bool)) or (isinstance(v, str) and len(v) < 40)})
        with open(LOG_DIR / "usage.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


_CITE_PATH = re.compile(r"\[\[([^\]\n#]{1,300})(?:#[^\]\n]*)?\]\]")


def cite(mode, text=None, paths=None):
    """Record which repo files the brain cited (paths only, never the answer text). Feeds the doc audit's
    'not cited in 30 days'. Never fails the caller."""
    try:
        ps = list(paths or []) + _CITE_PATH.findall(text or "")
        ps = sorted({p.strip().replace("\\", "/") for p in ps if p and isinstance(p, str) and len(p) < 300})
        if not ps:
            return
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / "citations.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _now(), "mode": mode, "paths": ps}, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- bench log

def log_path(date):
    if not DATE_RE.match(date or ""):
        raise ValueError("Bad date.")
    return LOG_DIR / ("%s.jsonl" % date)


def read_log(date):
    p = log_path(date)
    out = []
    if not p.exists():
        return out
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        e["_line"] = i
        out.append(e)
    return out


def add_entry(text, kind=None, status=None, parse_reading=True, photos=None, serial=None, source=None):
    """Append one entry. `text` is stored exactly as given (stripped of surrounding whitespace only).
    Parsed reading, revision, ticket and photos sit beside it as separate fields."""
    import parse as _parse
    text = (text or "").strip()
    if not text and not photos:
        raise ValueError("Empty entry.")
    if len(text) > 2000:
        raise ValueError("Entry too long (2000 chars max).")
    kind = kind or None
    status = status or None
    if kind is not None and kind not in KINDS:
        raise ValueError("Bad kind.")
    if status is not None and status not in STATUSES:
        raise ValueError("Bad status.")
    active = get_active()
    if not active:
        raise ValueError("No active board. Set the board first.")
    if serial and serial != active["serial"]:
        # The page showed a preview for one board, but the active board changed since. Refuse: never mix boards.
        raise ValueError("Active board changed to %s. Entry not saved; check the board bar." % active["serial"])
    e = {"ts": _now(), "board_type": active["board_type"], "serial": active["serial"],
         "kind": kind, "text": text, "status": status}
    if active.get("rev"):
        e["rev"] = active["rev"]
    if active.get("ticket"):
        e["ticket"] = active["ticket"]
    reading = _parse.parse_reading(text) if parse_reading else None
    if reading:
        e["reading"] = reading
        if e["kind"] is None:
            e["kind"] = "measurement"
    if photos:
        e["photos"] = list(photos)
    if source:
        e["source"] = source
    with _lock:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(log_path(_today()), "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def undo_last():
    """Remove the last entry of today's log. Only the last one; returns it."""
    with _lock:
        p = log_path(_today())
        if not p.exists():
            return None
        lines = p.read_text(encoding="utf-8").splitlines()
        while lines and not lines[-1].strip():
            lines.pop()
        if not lines:
            return None
        last = lines.pop()
        p.write_text("".join(l + "\n" for l in lines), encoding="utf-8")
    try:
        return json.loads(last)
    except ValueError:
        return {"text": last}


def log_dates():
    if not LOG_DIR.exists():
        return []
    return sorted(p.stem for p in LOG_DIR.glob("*.jsonl") if DATE_RE.match(p.stem))


def board_states(entries):
    """serial -> last status seen (None if never closed)."""
    st = {}
    for e in entries:
        key = e.get("serial")
        st.setdefault(key, {"board_type": e.get("board_type"), "serial": key, "status": None, "count": 0})
        st[key]["count"] += 1
        if e.get("status"):
            st[key]["status"] = e["status"]
    return st


def open_boards_before(date):
    """Boards left without a closing status on the most recent log day before `date`."""
    prev = [d for d in log_dates() if d < date]
    if not prev:
        return None, []
    day = prev[-1]
    st = board_states(read_log(day))
    return day, [b for b in st.values() if b["status"] not in CLOSED]


# ---------------------------------------------------------------- docs

def classify(rel):
    name = rel.split("/")[-1]
    low = name.lower()
    if rel.startswith("jarvis/"):
        return "jarvis"
    if rel.startswith("datasheets/"):
        return "datasheet"
    if rel.startswith("schematics/"):
        return "schematic"
    if rel.startswith("diag/"):
        return "diag"
    if low.endswith("-wip.md"):
        return "board-log"
    if re.match(r"^(\d{3}|\d{10,})-.*\.md$", low):
        return "case"
    if low in ("board-log.md", "case-writeup.md"):
        return "template"
    if low in ("00-methodology.md", "01-decision-tree.md", "02-short-circuit-workflow.md"):
        return "process"
    if low in ("readme.md", "claude.md", "jarvis_build_spec.md") or rel.startswith(".claude/"):
        return "meta"
    if low.endswith((".md", ".csv", ".txt")):
        return "reference"
    return "other"


def iter_docs():
    for root, dirs, files in os.walk(REPO):
        rp = Path(root)
        rel_root = rp.relative_to(REPO).as_posix()
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS
                         and not (rel_root == "jarvis" and d in ("static", "tests")))
        for f in sorted(files):
            p = rp / f
            if p.suffix.lower() not in DOC_EXT:
                continue
            rel = p.relative_to(REPO).as_posix()
            if rel.startswith("jarvis/") and not rel.startswith("jarvis/logs/"):
                continue
            yield rel, p


def doc_index():
    out = []
    for rel, p in iter_docs():
        c = classify(rel)
        if c == "jarvis":
            continue
        out.append({"path": rel, "class": c, "ext": p.suffix.lower()})
    return out


def resolve_repo_path(rel):
    """Map a repo-relative path to a file, refusing anything outside the repo or inside .git."""
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or "\x00" in rel:
        raise ValueError("Bad path.")
    p = (REPO / rel).resolve()
    try:
        r = p.relative_to(REPO)
    except ValueError:
        # Logs may live in an overridden DATA_DIR.
        try:
            p.relative_to(LOG_DIR.resolve())
        except ValueError:
            raise ValueError("Path outside the repo.")
        r = None
    if r is not None and r.parts and r.parts[0] in SKIP_DIRS:
        raise ValueError("Path not allowed.")
    if not p.is_file():
        raise FileNotFoundError(rel)
    return p


def data_rel(p):
    """Display path for a file in LOG_DIR (repo-relative when DATA_DIR is the default)."""
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return "jarvis/logs/" + p.name


def resolve_any(rel):
    rel = (rel or "").replace("\\", "/")
    if rel.startswith("jarvis/logs/") and DATA_DIR != JARVIS_DIR:
        p = (LOG_DIR / rel.split("/", 2)[2]).resolve()
        base = LOG_DIR.resolve()
        if base not in p.parents or not p.is_file():   # logs/ itself or a subfolder (photos/YYYY-MM-DD/)
            raise FileNotFoundError(rel)
        return p
    return resolve_repo_path(rel)


# ---------------------------------------------------------------- case metadata

_SERIAL_IN_TEXT = re.compile(r"\b(\d{14})\b")      # 14-digit serials; change to match your boards
_DATE_IN_TEXT = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def case_meta(rel, text):
    lines = text.splitlines()
    head = "\n".join(lines[:15])
    m = _SERIAL_IN_TEXT.search(rel) or _SERIAL_IN_TEXT.search(head)
    serial = m.group(1) if m else ""
    d = _DATE_IN_TEXT.search(head)
    status = ""
    sm = re.search(r"\*\*Status:?\s*(?:\*\*)?:?\s*([A-Z][A-Z-]+(?: [A-Z-]+)*)", head)
    if sm:
        status = sm.group(1).strip().split(" — ")[0].strip()
    elif rel.lower().endswith("-wip.md"):
        status = "OPEN (WIP)"
    title = lines[0].lstrip("# ").strip() if lines else rel
    resolved = status.startswith("RESOLVED") or status.startswith("CLOSED")
    return {"serial": serial, "date": d.group(1) if d else "", "status": status, "title": title,
            "board_type": "DEMO", "resolved": resolved}


def count_cases():
    return sum(1 for d in doc_index() if d["class"] in ("case", "board-log"))


# ---------------------------------------------------------------- fast search

STOP = set("""a an and are as at be but by for from has have i in is it its of on or that the this to was were
with my not no do does did can cant can't board demo when what which why how after before into than then
le la les un une des de du et est en au aux pour par pas sur avec dans que qui ne se sa son ses""".split())


def fold(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def tokens(q):
    toks = []
    for t in re.findall(r"[a-z0-9_+.\-]+", fold(q or "")):
        t = t.strip(".-")
        if len(t) >= 2 and t not in STOP:
            toks.append(t)
    return list(dict.fromkeys(toks))


def _md_sections(text):
    """Yield (start_line, end_line, heading, body) per markdown section."""
    lines = text.splitlines()
    start, heading = 1, ""
    buf = []
    for i, line in enumerate(lines, 1):
        if re.match(r"^#{1,4}\s", line):
            if buf:
                yield start, i - 1, heading, "\n".join(buf)
            start, heading, buf = i, line.lstrip("#").strip(), [line]
        else:
            buf.append(line)
    if buf:
        yield start, len(lines), heading, "\n".join(buf)


def _score(hay, toks):
    h = fold(hay)
    hits = [t for t in toks if t in h]
    if not hits:
        return 0, []
    score = sum(min(h.count(t), 5) for t in hits)
    score += 4 * len(hits)  # breadth beats repetition
    return score, hits


def _snippet(body, hits, width=220):
    # Strip markdown syntax so the snippet reads as text.
    body = re.sub(r"(?m)^\s*#{1,6}\s*", "", body)
    body = re.sub(r"\*\*|__|`|^\s*>\s?|\[\[|\]\]", "", body, flags=re.M)
    body = re.sub(r"\s*\|\s*", " · ", body)
    body = re.sub(r"(?m)^[\s·:-]+$", "", body)
    flat = re.sub(r"\s+", " ", body).strip(" ·")
    f = fold(flat)
    pos = min([f.find(t) for t in hits if f.find(t) >= 0] or [0])
    a = max(0, pos - 60)
    s = flat[a:a + width]
    return ("…" if a else "") + s + ("…" if a + width < len(flat) else "")


def search_sources():
    """Case write-ups, board logs, field data and every text log (md/txt/csv/jsonl)."""
    def bench_file(p):
        # Only day logs and confirmed close-outs; not usage/hypothesis/sample bookkeeping files.
        return DATE_RE.match(p.stem) or p.name == "closeouts.jsonl"
    for rel, p in iter_docs():
        c = classify(rel)
        if rel.startswith("jarvis/logs/"):
            if p.suffix.lower() == ".jsonl" and bench_file(p):
                yield rel, p, "closeout" if p.name == "closeouts.jsonl" else "bench-log"
            continue
        if c in ("case", "board-log") or rel.lower().endswith((".txt", ".csv", ".jsonl")) \
                or rel == "field-failure-data.md":
            yield rel, p, c
    if DATA_DIR != JARVIS_DIR and LOG_DIR.exists():
        for p in sorted(LOG_DIR.glob("*.jsonl")):
            if bench_file(p):
                yield data_rel(p), p, "closeout" if p.name == "closeouts.jsonl" else "bench-log"


def fast_search(query, limit=40, exclude_serial=None):
    toks = tokens(query)
    if not toks:
        return {"tokens": [], "hits": []}
    hits = []
    for rel, p, cls in search_sources():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ext = p.suffix.lower()
        if ext == ".jsonl":
            for i, line in enumerate(text.splitlines(), 1):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if exclude_serial and e.get("serial") == exclude_serial and p.stem == _today():
                    continue  # don't match the board you're asking about against itself
                if cls == "closeout":
                    body = " ".join(str(e.get(k) or "") for k in ("symptom", "root_cause", "fix", "parts", "outcome", "serial"))
                    snip = "%s → %s (%s; root cause %s)" % (e.get("symptom", ""), e.get("root_cause", ""),
                                                           e.get("fix", ""), e.get("root_cause_status", ""))
                    e = dict(e, status=e.get("closed_status"))
                else:
                    body = "%s %s %s %s" % (e.get("text", ""), e.get("kind") or "", e.get("status") or "", e.get("serial", ""))
                    snip = e.get("text", "")
                s, h = _score(body, toks)
                if s:
                    hits.append({"path": rel, "line": i, "heading": "", "class": cls, "score": s,
                                 "matched": h, "snippet": snip,
                                 "meta": {"serial": e.get("serial", ""), "date": (e.get("ts") or "")[:10],
                                          "board_type": e.get("board_type", ""),
                                          "status": e.get("status") or "", "kind": e.get("kind") or "",
                                          "resolved": e.get("status") in CLOSED}})
        elif ext == ".csv" or ext == ".txt":
            for i, line in enumerate(text.splitlines(), 1):
                s, h = _score(line, toks)
                if s:
                    hits.append({"path": rel, "line": i, "heading": "", "class": cls, "score": s,
                                 "matched": h, "snippet": _snippet(line, h), "meta": {}})
        else:
            meta = case_meta(rel, text) if cls in ("case", "board-log") else {}
            title_bonus = _score(meta.get("title", ""), toks)[0] if meta else 0
            for a, b, heading, body in _md_sections(text):
                s, h = _score(body, toks)
                if s:
                    if heading and re.match(r"(root cause|symptom|cause|summary)", fold(heading)):
                        s += 3
                    hits.append({"path": rel, "line": a, "line_end": b, "heading": heading, "class": cls,
                                 "score": s + title_bonus, "matched": h, "snippet": _snippet(body, h),
                                 "meta": meta})
    hits.sort(key=lambda x: (-x["score"], x["path"], x["line"]))
    # Keep at most 3 sections per file so one long case doesn't drown the rest.
    per, out = {}, []
    for hit in hits:
        per[hit["path"]] = per.get(hit["path"], 0) + 1
        if per[hit["path"]] <= 3:
            out.append(hit)
        if len(out) >= limit:
            break
    return {"tokens": toks, "hits": out}


def entry_exists(rel, line):
    """True if rel:line points at a real file/line (used to drop invented cases)."""
    try:
        p = resolve_any(rel)
    except (ValueError, FileNotFoundError):
        return False
    if p.suffix.lower() == ".pdf":
        return True
    try:
        n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return False
    return 1 <= int(line or 1) <= max(n, 1)


# ---------------------------------------------------------------- status

def status():
    today = _today()
    docs = doc_index()
    entries = read_log(today)
    day, open_prev = open_boards_before(today)
    past = 0
    for d in log_dates():
        if d != today:
            past += len(read_log(d))
    return {
        "today": today,
        "docs": len(docs),
        "docs_by_class": {c: sum(1 for d in docs if d["class"] == c)
                          for c in sorted({d["class"] for d in docs})},
        "cases": count_cases(),
        "past_log_entries": past,
        "today_entries": len(entries),
        "today_boards": len(board_states(entries)),
        "prev_day": day,
        "open_prev": open_prev,
        "active": get_active(),
    }
