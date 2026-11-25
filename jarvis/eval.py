"""Run the golden set against the real brain:  sh jarvis.sh eval  [--only g01,g05] [--workers 4]

Reads jarvis/evals/golden.jsonl (never writes it), prints a pass/fail table,
saves results to jarvis/evals/results/YYYY-MM-DD_HHMM.json.

Checks (heuristics, documented in JARVIS_V2_SPEC.md Build notes):
  must_cite    at least one [[citation]] whose path equals one of the target paths ('a.md|b.md')
  not_in_docs  the answer says plainly the docs don't cover it (phrase match)
  one_step     at most one numbered step, and it asks for a reading / waits
  expected_verdict  the answer's first sentence starts with the expected Yes / No ("verdict": "yes"|"no");
               with an optional "target", it must also cite one of those paths (as must_cite)
  must_contain (optional list, on any type) every term must appear in the answer: whole word, case-insensitive,
               [[citations]] ignored (so "14" can't match "#L14"). A number term matches by value
               ("2.5" matches 2.50, "10" matches 10.0), also with a unit glued on (5.04V, 4.7kΩ, 16MHz),
               but never part of a longer number ("5" isn't in 2.5) or a part name ("6" isn't in U6).
               All of them, or the question fails.
  labels       (all) the answer starts with a labelled section and every section is labelled
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain  # noqa: E402

EVAL_DIR = Path(os.environ.get("JARVIS_DATA_DIR") or Path(__file__).resolve().parent) / "evals"
GOLDEN = Path(__file__).resolve().parent / "evals" / "golden.jsonl"

CITE = re.compile(r"\[\[([^\]\n]+)\]\]")
NOT_IN_DOCS = re.compile(
    r"(not (?:in|covered (?:by|in)|stated in|mentioned in|found in) (?:your|the|these) (?:docs|repo|files|documentation))"
    r"|((?:your |the )?docs (?:do not|don't|does not|doesn't) (?:cover|say|mention|contain|have|give|list|state|include|specify))"
    r"|(no (?:mention|information|data|value|spec\w*|record)\b[^.\n]{0,60}\b(?:in|from) (?:your|the) (?:docs|repo|files))"
    r"|(isn't|is not|aren't|are not) (?:in|covered by) (?:your|the) (?:docs|repo)"
    r"|(nothing in (?:your|the) (?:docs|repo|files))|(not documented)", re.I)
ASKS = re.compile(r"(send|report|reply with|tell me|give me|let me know|what (?:is|was|do you get|does it read)|reading\b.*\?|then I'?ll|wait)", re.I)
NUMBERED = re.compile(r"(?m)^\s*\d+[.)]\s+\S")
VERDICT = re.compile(r"^(yes|no)\b", re.I)
LABELS = ("from your docs", "from past cases", "general knowledge")


def cite_paths(text):
    out = []
    for c in CITE.findall(text):
        p = re.split(r"#| p\.| page ", c, maxsplit=1)[0].strip()
        out.append(p)
    return out


def labels_ok(text):
    t = text.strip()
    heads = re.findall(r"(?m)^##\s+(.+)$", t)
    if not heads:
        return False, "no section headings"
    if not re.match(r"^##\s", t):
        return False, "text before the first labelled section"
    bad = [h for h in heads if not any(h.lower().startswith(l) for l in LABELS)]
    return (not bad), ("unlabelled: " + "; ".join(bad)) if bad else ""


def first_sentence(text):
    """First sentence of the answer body: skip headings and blank lines, drop markdown emphasis."""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"[*_`>]+", "", line).lstrip("-• ").strip()
        m = re.match(r"(.+?[.!?])(\s|$)", line)
        return (m.group(1) if m else line).strip()
    return ""


NUM_TERM = re.compile(r"^\d+(?:\.\d+)?$")
# Units that may be glued to a number: 5.04V, 4.7k, 4.7kΩ, 330Ω, 16MHz, 470pF, 10mA, 35%.
UNIT = r"(?:[pnuµμmkM]?(?:Ω|Ω|ohms?|Hz|V|A|F|W|s)|[kKM]|%)"
# A number in the answer: not glued to a letter/digit before it (U6, C640), not part of a longer decimal
# ("5" isn't in 2.5), and followed by nothing word-like except one of the units above (8AB, 2nd don't count).
NUM_TOKEN = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?:" + UNIT + r")?(?!\w|\.\d)")


def missing_terms(terms, text):
    body = CITE.sub(" ", text)
    values = {Decimal(n) for n in NUM_TOKEN.findall(body)}
    miss = []
    for t in terms:
        if NUM_TERM.match(t):
            found = Decimal(t) in values                   # by value: 2.5 = 2.50, 10 = 10.0
        else:
            found = re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", body, re.I)
        if not found:
            miss.append(t)
    return miss


def check(item, text):
    ok, detail, lok, ldetail = _check_type(item, text)
    terms = item["expect"].get("must_contain") or []
    if terms:
        miss = missing_terms(terms, text)
        ok = ok and not miss
        detail += "; " + ("missing: " + ", ".join(miss) if miss else "has all %d terms" % len(terms))
    return ok, detail, lok, ldetail


def _check_type(item, text):
    exp = item["expect"]
    t = exp["type"]
    if t == "must_cite":
        targets = exp["target"].split("|")
        got = cite_paths(text)
        ok = any(g in targets for g in got)
        detail = "cited: " + (", ".join(sorted(set(got))) or "nothing")
    elif t == "not_in_docs":
        m = NOT_IN_DOCS.search(text)
        ok = bool(m)
        detail = ("said: \"%s\"" % m.group(0)) if m else "no 'not in docs' statement"
    elif t == "expected_verdict":
        want = (exp.get("verdict") or "").lower()
        fs = first_sentence(text)
        m = VERDICT.match(fs)
        got = m.group(1).lower() if m else None
        ok = want in ("yes", "no") and got == want
        detail = "first sentence: \"%s\" (%s, want %s)" % (fs[:60], got or "no verdict", want or "?")
        if exp.get("target"):
            cited = cite_paths(text)
            hit = any(g in exp["target"].split("|") for g in cited)
            ok = ok and hit
            detail += "; " + ("cited " + exp["target"] if hit else "did not cite " + exp["target"])
    elif t == "one_step":
        n = len(NUMBERED.findall(text.split("## General knowledge")[0]))
        asks = bool(ASKS.search(text))
        ok = n <= 1 and asks
        detail = "%d numbered steps, %s" % (n, "asks for the reading" if asks else "does not ask for a reading")
    else:
        ok, detail = False, "unknown expect type"
    lok, ldetail = labels_ok(text)
    return ok, detail, lok, ldetail


def run_one(item):
    t0 = time.time()
    text, err = "", None
    for ev in brain.ask("ask", item["question"]):
        if ev["type"] == "done":
            text = ev.get("text") or ""
        elif ev["type"] == "error":
            err = ev["message"]
    if err:
        return dict(id=item["id"], ok=False, labels=False, detail="ERROR: " + err, label_detail="", seconds=round(time.time() - t0, 1), answer="")
    ok, detail, lok, ldetail = check(item, text)
    return dict(id=item["id"], type=item["expect"]["type"], ok=ok, detail=detail, labels=lok, label_detail=ldetail,
                seconds=round(time.time() - t0, 1), question=item["question"], answer=text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if brain.is_mock():
        print("JARVIS_MOCK=1 is set: the golden set must run against the real brain. Unset it.")
        return 2
    items = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.only:
        want = set(a.only.split(","))
        items = [i for i in items if i["id"] in want]
    h = brain.health_check()
    if not h.get("ok"):
        print("Brain offline: %s %s" % (h.get("detail"), h.get("hint", "")))
        return 2
    print("Running %d golden questions against %s (%d at a time)…" % (len(items), h.get("version"), a.workers))
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        results = list(ex.map(run_one, items))
    total = time.time() - t0
    print()
    print("%-4s %-16s %-5s %-6s %6s  %s" % ("id", "type", "pass", "labels", "secs", "detail"))
    print("-" * 100)
    for r in results:
        print("%-4s %-16s %-5s %-6s %6.1f  %s%s" % (r["id"], r.get("type", ""), "PASS" if r["ok"] else "FAIL",
                                                    "ok" if r["labels"] else "FAIL", r["seconds"], r["detail"][:70],
                                                    ("  [" + r["label_detail"] + "]") if r["label_detail"] else ""))
    n_ok = sum(r["ok"] for r in results)
    n_lab = sum(r["labels"] for r in results)
    print("-" * 100)
    print("%d/%d expected outcome · %d/%d labelled · %.0f s total" % (n_ok, len(results), n_lab, len(results), total))
    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (dt.datetime.now().strftime("%Y-%m-%d_%H%M") + ".json")
    out.write_text(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds"), "claude": h.get("version"),
                               "model": h.get("model"), "passed": n_ok, "labelled": n_lab, "total": len(results),
                               "seconds": round(total, 1), "results": results}, indent=1, ensure_ascii=False),
                   encoding="utf-8")
    print("Saved %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
