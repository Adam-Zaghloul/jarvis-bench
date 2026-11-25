"""Close-out cards (confirmed by the technician) and recurring-pattern detection.

closeouts.jsonl  one confirmed close-out per line (never written from a draft without confirm)
patterns.json    {pattern_id: {"status": "new|verified|dismissed", "ts": ...}} — only your decisions are stored;
                 the clusters themselves are recomputed from close-outs each time.

Similarity (documented in Build notes): two close-outs are "similar" when
    same board_type
    AND Jaccard(symptom tokens) >= 0.4
    AND (Jaccard(root-cause tokens) >= 0.4 OR they share a part designator in root cause/fix, e.g. R14).
Tokens: lowercased, accent-folded words of 3+ chars minus stopwords. Clusters = connected components
(single link). A cluster of 3+ close-outs is a pattern.
"""
import hashlib
import json
import re

import store

CLOSEOUTS = store.LOG_DIR / "closeouts.jsonl"
PATTERNS = store.LOG_DIR / "patterns.json"
FIELDS = ("symptom", "root_cause", "fix", "parts", "outcome", "ticket")
RC_STATUS = ("suspected", "confirmed")
MIN_CASES = 3
J_SYM, J_RC = 0.4, 0.4
_DESIG = re.compile(r"\b([A-Z]{1,3}\d{1,4})\b")


def validate(card):
    out = {}
    for f in FIELDS:
        v = card.get(f, "")
        if not isinstance(v, str):
            v = str(v)
        if len(v) > 2000:
            raise ValueError("%s too long" % f)
        out[f] = v.strip()
    if not out["symptom"] or not out["root_cause"]:
        raise ValueError("Symptom and root cause are required to confirm.")
    rcs = card.get("root_cause_status") or "suspected"
    if rcs not in RC_STATUS:
        raise ValueError("root_cause_status must be suspected or confirmed")
    out["root_cause_status"] = rcs
    return out


def save(card, serial, board_type, rev, closed_status, hypothesis=None):
    """Called only from the confirm action. Appends one close-out."""
    if closed_status not in store.CLOSED:
        raise ValueError("Close-out needs status fixed, escalated or scrap.")
    c = validate(card)
    c.update({"id": "%s-%s" % (serial, store._now().replace(":", "").replace("-", "")),
              "ts": store._now(), "serial": serial, "board_type": board_type, "rev": rev or "",
              "closed_status": closed_status, "confirmed_by_user": True})
    if hypothesis:
        c["hypothesis"] = hypothesis.get("text", "")
        c["hypothesis_match"] = hypothesis.get("match")  # True/False/None, set by you on the card
    store.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CLOSEOUTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return c


def load():
    out = []
    if CLOSEOUTS.exists():
        for i, line in enumerate(CLOSEOUTS.read_text(encoding="utf-8").splitlines(), 1):
            try:
                c = json.loads(line)
                c["_line"] = i
                out.append(c)
            except ValueError:
                pass
    return out


def for_serial(serial):
    return [c for c in load() if c.get("serial") == serial]


# ---------------------------------------------------------------- patterns

def _tok(s):
    return set(t for t in store.tokens(s or "") if len(t) >= 3)


def _jac(a, b):
    return len(a & b) / float(len(a | b)) if (a or b) else 0.0


def similar(a, b):
    if (a.get("board_type") or "").upper() != (b.get("board_type") or "").upper():
        return False
    if _jac(_tok(a["symptom"]), _tok(b["symptom"])) < J_SYM:
        return False
    if _jac(_tok(a["root_cause"]), _tok(b["root_cause"])) >= J_RC:
        return True
    da = set(_DESIG.findall(a["root_cause"] + " " + a.get("fix", "")))
    db = set(_DESIG.findall(b["root_cause"] + " " + b.get("fix", "")))
    return bool(da & db)


def _state():
    try:
        return json.loads(PATTERNS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def patterns():
    cos = load()
    n = len(cos)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(n):
        for j in range(i + 1, n):
            if similar(cos[i], cos[j]):
                parent[find(i)] = find(j)
    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(cos[i])
    st = _state()
    out = []
    for g in groups.values():
        if len(g) < MIN_CASES:
            continue
        ids = sorted(c["id"] for c in g)
        pid = hashlib.sha1("|".join(ids).encode()).hexdigest()[:12]
        common_sym = set.intersection(*[_tok(c["symptom"]) for c in g])
        common_rc = set.intersection(*[_tok(c["root_cause"]) for c in g])
        parts = sorted(set.intersection(*[set(_DESIG.findall(c["root_cause"] + " " + c.get("fix", ""))) for c in g]))
        s = st.get(pid, {})
        out.append({
            "id": pid, "status": s.get("status", "new"), "board_type": g[0]["board_type"],
            # Readable title: the shortest real symptom and root cause in the group (not a bag of words).
            "title": "%s: %s → %s" % (g[0]["board_type"],
                                      min((c["symptom"] for c in g), key=len).rstrip(".")[:80],
                                      ", ".join(parts) or min((c["root_cause"] for c in g), key=len).rstrip(".")[:60]),
            "symptom_tokens": sorted(common_sym), "root_cause_tokens": sorted(common_rc), "parts": parts,
            "confirmed_root_causes": sum(1 for c in g if c.get("root_cause_status") == "confirmed"),
            "cases": [{"id": c["id"], "serial": c["serial"], "ts": c["ts"], "symptom": c["symptom"],
                       "root_cause": c["root_cause"], "root_cause_status": c.get("root_cause_status"),
                       "fix": c.get("fix", ""), "outcome": c.get("outcome", ""),
                       "ref": "jarvis/logs/closeouts.jsonl#L%d" % c["_line"]} for c in g],
        })
    order = {"verified": 0, "new": 1, "dismissed": 2}
    out.sort(key=lambda p: (order.get(p["status"], 1), -len(p["cases"])))
    return out


def set_pattern(pid, status):
    if status not in ("verified", "dismissed", "new"):
        raise ValueError("Bad pattern status.")
    if not re.match(r"^[0-9a-f]{12}$", pid or ""):
        raise ValueError("Bad pattern id.")
    if pid not in {p["id"] for p in patterns()}:
        raise ValueError("Unknown pattern.")
    st = _state()
    st[pid] = {"status": status, "ts": store._now()}
    store.LOG_DIR.mkdir(parents=True, exist_ok=True)
    PATTERNS.write_text(json.dumps(st, indent=1), encoding="utf-8")
    return st[pid]


def patterns_for_query(q):
    """Verified patterns whose symptom/root-cause tokens overlap the query; shown first in Seen before."""
    qt = _tok(q)
    out = []
    for p in patterns():
        if p["status"] != "verified":
            continue
        overlap = qt & (set(p["symptom_tokens"]) | set(p["root_cause_tokens"]) | {x.lower() for x in p["parts"]})
        if overlap:
            out.append(dict(p, matched=sorted(overlap)))
    return out
