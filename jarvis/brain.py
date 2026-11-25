"""JARVIS brain: a read-only Claude Code headless session (`claude -p`).

Rules that matter here:
- The user's text never reaches argv. It goes to the child via stdin.
- argv only holds fixed flags, file paths we created, UUIDs and our own JSON schema.
- Tools are hard-limited to Read, Grep, Glob. No MCP servers, no skills.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

JARVIS_DIR = Path(__file__).resolve().parent
REPO = JARVIS_DIR.parent
DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR") or JARVIS_DIR)
LOG_DIR = DATA_DIR / "logs"
TIMEOUT_S = int(os.environ.get("JARVIS_TIMEOUT", "120"))

READ_ONLY_TOOLS = "Read,Grep,Glob"
DENIED_TOOLS = "Bash,Edit,Write,MultiEdit,NotebookEdit,WebFetch,WebSearch,Task,Agent"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# Characters cmd.exe treats specially when a .cmd shim relays our argv.
CMD_META = re.compile(r'[&|<>^%!\r\n]')

# Env vars set when JARVIS itself is launched from inside a Claude Code session.
# Stripped so the child behaves like a fresh `claude` started from cmd.exe.
_STRIP_ENV_PREFIXES = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK")
_STRIP_ENV = {"CLAUDE_PID", "CLAUDE_EFFORT"}

# ---------------------------------------------------------------- rules

ANSWER_RULES = """You are JARVIS, a read-only bench assistant for board-level repair of the boards documented in this repo.
The working directory is the technician's repair-docs repo. Read files with Read/Grep/Glob only.
PDFs: read with page ranges (datasheets can run to hundreds of pages; never read one whole).

ANSWER RULES (all modes):
- Every factual claim cites its source as [[path#Lstart-Lend]], [[path#Heading text]] or, for PDFs, [[path p.N]].
  path is repo-relative and exact, e.g. [[01-decision-tree.md#BRANCH 2 — Status LED never blinks]] or [[test-points.md#L40-L52]].
- Every part of the answer sits under one of these labelled sections, in this order (omit any that would be empty):
  "## From your docs" (reference docs, decision tree, methodology, datasheets, schematic),
  "## From past cases" (case write-ups, *-WIP.md board logs, jarvis/logs bench logs and close-outs),
  "## General knowledge (not in your docs)" (keep it short).
  Start the reply with the first section heading. No text before it, no other ## headings (use ### inside a section).
  If nothing in the docs or cases covers it, the first section is "## From your docs" and says so plainly.
- If the docs don't cover something, say so plainly. Don't guess.
- If two docs disagree, show both with citations and flag the conflict with ⚠.
- If the question assumes something the docs contradict, say that first.
- Troubleshooting: one step at a time. Give exactly ONE measurement or action per reply (never a numbered list of
  several), explain why, then stop and wait for the reading. If an earlier requested reading is missing, ask for that one.
- Flag any step that needs power applied with "⚡ POWER ON" and any destructive step
  (desoldering, lifting a pin, cutting a trace) with "⚠ DESTRUCTIVE".
- Answer in the language of the question (English or French).
- Terse and technical. No personality, no pleasantries.
- Respect the repo conventions: [V] verified, [D] derived, [A] assumed, ⚠ contradiction.
"""

MODE_RULES = {
    "ask": """MODE: Ask the docs. Answer the technician's question from the repo docs.
If a "Board context" block is given, it is the active board and today's log for it. Use it; never mix in other boards' readings.""",
    "seen": """MODE: Seen this before? You get a symptom and a list of keyword-search hits from case write-ups, board logs and JSONL bench logs.
Read the hit sources as needed. Group hits that describe the same board+fault into one case.
Only report cases that exist in the hits or in files you actually read; never invent a case, serial, date or fix.
Each case's source_path must be an exact repo-relative path (for JSONL logs use the path given in the hit) and source_line the line of the entry.
resolved=false for anything still open, WIP, or without a confirmed fix.
Fill summary.worked / summary.did_not_work only with fixes the sources state.""",
    "debrief": """MODE: End-of-shift debrief. You get one day's bench log as JSONL lines (ts, board_type, serial, kind, text, status).
Produce: slack (3-6 short lines: boards worked, fixed/escalated/open counts, blockers),
boards (one per serial: symptom, measurements, actions, result, next_step; every line keeps the ts of the log entry it came from),
open_items (for tomorrow), unplaced (entries you could not attribute, with reason).
Use only the log. You may read the repo to name a known fault, but never add measurements or actions that are not in the log.
This output is pasted into Slack and Jira: do NOT use [[...]] citation markup here; name a doc in plain words if needed.
Write in the requested language. Copy-only output: nothing is sent anywhere.""",
    "closeout": """MODE: Close-out pre-fill. You get ONE board's bench log (JSONL). Draft the close-out card fields:
symptom, root_cause, fix, parts (designators/part numbers that were replaced, comma-separated), outcome.
Use ONLY what the log states. If the log does not state a root cause, write "Not stated in log" — do not infer one.
root_cause_status: "confirmed" only if the log explicitly shows the fix resolved the fault (e.g. a result entry after
the fix); otherwise "suspected". The technician will edit and confirm; this is a draft. No [[...]] markup.""",
    "handoff": """MODE: Escalation handoff note. You get ONE escalated board's bench log (JSONL) and its close-out card.
Write for the engineer receiving the board: measured (with values), tried, ruled out, suspected cause, suggested next check.
Each measured/tried line keeps the log ts it came from. Ruled-out items only if the log shows the evidence.
Suggested next check: one step, from 01-decision-tree.md or the case files if they cover it; say if they don't.
Plain text, no [[...]] markup (it is pasted outside JARVIS). English.""",
    "competency": """MODE: Competency log. You get a week of bench log entries and close-outs. List the techniques and skills used,
written generally for a career record (e.g. "Isolated a power-rail short by comparing in-circuit resistance against a
known-good board"). STRICTLY NO part numbers, reference designators, serial numbers, ticket IDs, product names,
board names, company or internal names, part values. 3-8 items. English. No [[...]] markup.""",
    "workinstruction": """MODE: Work-instruction draft. You get one VERIFIED recurring pattern and its close-out cases.
Draft a short work instruction in markdown: title, when to use (symptom), steps (numbered, one action each, why),
expected readings (only values stated in the cases or the repo docs, cite them in plain words), and what to do if it doesn't fix it.
Flag ⚡ POWER ON and ⚠ DESTRUCTIVE steps. Start with the line "DRAFT — not reviewed. Do not use until reviewed."
English. No [[...]] markup.""",
}

LANG_NAMES = {"en": "English", "fr": "French (technical French)"}

SEEN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "object",
            "properties": {
                "similar_count": {"type": "integer"},
                "pattern": {"type": "string"},
                "worked": {"type": "array", "items": {"type": "string"}},
                "did_not_work": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["similar_count", "pattern", "worked", "did_not_work"],
        },
        "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_path": {"type": "string"},
                    "source_line": {"type": "integer"},
                    "date": {"type": "string"},
                    "board_type": {"type": "string"},
                    "serial": {"type": "string"},
                    "symptom": {"type": "string"},
                    "fix": {"type": "string"},
                    "outcome": {"type": "string"},
                    "resolved": {"type": "boolean"},
                },
                "required": ["source_path", "source_line", "date", "board_type", "serial",
                             "symptom", "fix", "outcome", "resolved"],
            },
        },
    },
    "required": ["summary", "cases"],
}

_LINE = {"type": "object", "properties": {"ts": {"type": "string"}, "text": {"type": "string"}},
         "required": ["ts", "text"]}
DEBRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "slack": {"type": "array", "items": {"type": "string"}},
        "boards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "serial": {"type": "string"},
                    "board_type": {"type": "string"},
                    "status": {"type": "string"},
                    "symptom": _LINE,
                    "measurements": {"type": "array", "items": _LINE},
                    "actions": {"type": "array", "items": _LINE},
                    "result": _LINE,
                    "next_step": {"type": "string"},
                },
                "required": ["serial", "board_type", "status", "symptom", "measurements",
                             "actions", "result", "next_step"],
            },
        },
        "open_items": {"type": "array", "items": {"type": "string"}},
        "unplaced": {
            "type": "array",
            "items": {"type": "object",
                      "properties": {"ts": {"type": "string"}, "text": {"type": "string"},
                                     "reason": {"type": "string"}},
                      "required": ["ts", "text", "reason"]},
        },
    },
    "required": ["slack", "boards", "open_items", "unplaced"],
}

CLOSEOUT_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in ("symptom", "root_cause", "fix", "parts", "outcome")},
    "required": ["symptom", "root_cause", "fix", "parts", "outcome", "root_cause_status"],
}
CLOSEOUT_SCHEMA["properties"]["root_cause_status"] = {"type": "string", "enum": ["suspected", "confirmed"]}
TEXT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
LIST_SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "string"}}},
               "required": ["items"]}

SCHEMAS = {"seen": SEEN_SCHEMA, "debrief": DEBRIEF_SCHEMA, "closeout": CLOSEOUT_SCHEMA,
           "handoff": TEXT_SCHEMA, "competency": LIST_SCHEMA, "workinstruction": TEXT_SCHEMA}


class BrainError(Exception):
    def __init__(self, message, hint=""):
        super().__init__(message)
        self.message = message
        self.hint = hint


# ---------------------------------------------------------------- executable

def find_claude():
    """Resolve the claude executable. On Windows this finds claude.cmd / claude.exe too."""
    override = os.environ.get("JARVIS_CLAUDE")
    if override:
        return override if Path(override).exists() else None
    return shutil.which("claude")


def child_env():
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(_STRIP_ENV_PREFIXES) and k not in _STRIP_ENV}
    return env


def is_mock():
    return os.environ.get("JARVIS_MOCK") == "1"


def _check_argv(argv):
    """A .cmd/.bat shim is run through cmd.exe, which re-parses argv. Refuse anything it could misread."""
    exe = argv[0].lower()
    if exe.endswith((".cmd", ".bat")):
        for a in argv[1:]:
            if CMD_META.search(a):
                raise BrainError("Refused to start claude: an argument contains a cmd.exe metacharacter.",
                                 "This is a JARVIS bug. Report the mode you used.")


def build_argv(exe, mode, rules_file, session_id=None, structured=False):
    argv = [exe, "-p",
            "--tools", READ_ONLY_TOOLS,
            "--allowedTools", READ_ONLY_TOOLS,
            "--disallowedTools", DENIED_TOOLS,
            "--permission-mode", "dontAsk",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--append-system-prompt-file", str(rules_file)]
    model = os.environ.get("JARVIS_MODEL")
    if model and re.fullmatch(r"[A-Za-z0-9._\[\]-]+", model):
        argv += ["--model", model]
    if structured:
        argv += ["--output-format", "json", "--no-session-persistence",
                 "--json-schema", json.dumps(SCHEMAS[mode], separators=(",", ":"))]
    else:
        argv += ["--output-format", "stream-json", "--verbose", "--include-partial-messages"]
        if session_id:
            if not UUID_RE.match(session_id):
                raise BrainError("Bad session id.", "Press New question.")
            argv += ["--resume", session_id]
    _check_argv(argv)
    return argv


def write_rules(mode, lang=None):
    rules = ANSWER_RULES + "\n" + MODE_RULES[mode]
    if lang in LANG_NAMES:
        rules += "\nOutput language: " + LANG_NAMES[lang] + "."
    fd, path = tempfile.mkstemp(prefix="jarvis-rules-", suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(rules)
    return path


def build_prompt(mode, question, context):
    parts = []
    if context:
        parts.append(context.strip())
    parts.append(("Question:\n" if mode == "ask" else "") + (question or "").strip())
    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------- logging

def log_call(mode, duration, ok, detail=""):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": mode, "duration_s": round(duration, 2),
               "ok": ok, "mock": is_mock()}
        if detail:
            rec["detail"] = detail[:300]
        with open(LOG_DIR / "brain.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- process

def _kill(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        # Kill the whole tree: a .cmd shim leaves node.exe running otherwise.
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        proc.kill()


def _spawn(argv, prompt):
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(argv, cwd=str(REPO), env=child_env(), stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    proc.stdin.write(prompt.encode("utf-8"))
    proc.stdin.close()
    return proc


def _timeout_error():
    return BrainError(
        "No answer after %d s. JARVIS stopped the request." % TIMEOUT_S,
        "Try a narrower question (name the net, part or file), or retry. "
        "If it keeps happening, run `claude -p \"hi\"` in cmd.exe to check Claude Code itself.")


def _failure(stderr, result=None):
    text = (result or "") + " " + (stderr or "")
    low = text.lower()
    if "not logged in" in low or "/login" in low:
        return BrainError("Claude Code is not logged in.", "Open cmd.exe, run `claude`, log in, then retry.")
    if "rate limit" in low or "usage limit" in low:
        return BrainError("Claude usage limit reached.", "Wait for the limit to reset. Quick log still works.")
    if "selected model" in low:
        return BrainError("Claude Code rejected the model.", "Run `claude update` in cmd.exe.")
    msg = (result or stderr or "unknown error").strip().splitlines()
    return BrainError("Claude Code failed: " + (msg[-1][:200] if msg else "no output"),
                      "Check jarvis/logs/brain.log. Run `claude -p \"hi\"` in cmd.exe to test.")


# ---------------------------------------------------------------- public API

def ask(mode, question, context="", session_id=None, lang=None):
    """Streaming modes (ask): yields events
       {"type":"session","id"} {"type":"delta","text"} {"type":"tool","name","detail"}
       {"type":"done","text","session_id","duration_s"} {"type":"error","message","hint"}
    Structured modes (seen, debrief): yields one {"type":"done","data",...} or an error.
    """
    if mode not in MODE_RULES:
        yield {"type": "error", "message": "Unknown mode: %s" % mode, "hint": ""}
        return
    t0 = time.time()
    if is_mock():
        from mock import mock_events
        ok = True
        for ev in mock_events(mode, question, context, session_id):
            ok = ok and ev["type"] != "error"
            yield ev
        log_call(mode, time.time() - t0, ok, "mock")
        return
    exe = find_claude()
    if not exe:
        log_call(mode, 0, False, "claude not found")
        yield {"type": "error", "message": "Claude Code executable not found.",
               "hint": "Install Claude Code, or set JARVIS_CLAUDE to the full path of claude.exe / claude.cmd."}
        return
    structured = mode in SCHEMAS
    rules_file = write_rules(mode, lang)
    try:
        try:
            argv = build_argv(exe, mode, rules_file, session_id, structured)
            proc = _spawn(argv, build_prompt(mode, question, context))
        except BrainError as e:
            log_call(mode, time.time() - t0, False, e.message)
            yield {"type": "error", "message": e.message, "hint": e.hint}
            return
        except OSError as e:
            log_call(mode, time.time() - t0, False, str(e))
            yield {"type": "error", "message": "Could not start Claude Code: %s" % e,
                   "hint": "Check that `claude --version` works in cmd.exe."}
            return
        timed_out = threading.Event()

        def watchdog():
            timed_out.set()
            _kill(proc)
        timer = threading.Timer(TIMEOUT_S, watchdog)
        timer.daemon = True
        timer.start()
        stderr_buf = []
        err_thread = threading.Thread(target=lambda: stderr_buf.append(proc.stderr.read()), daemon=True)
        err_thread.start()
        try:
            gen = _run_structured(proc, mode) if structured else _run_stream(proc)
            final = None
            for ev in gen:
                if ev["type"] == "_final":
                    final = ev
                    continue
                yield ev
            proc.wait()
            err_thread.join(2)
            stderr = (stderr_buf[0] if stderr_buf else b"").decode("utf-8", "replace")
            dur = time.time() - t0
            if timed_out.is_set():
                e = _timeout_error()
                log_call(mode, dur, False, "timeout")
                yield {"type": "error", "message": e.message, "hint": e.hint}
                return
            if final is None or final.get("is_error"):
                e = _failure(stderr, final.get("result") if final else None)
                log_call(mode, dur, False, e.message)
                yield {"type": "error", "message": e.message, "hint": e.hint}
                return
            log_call(mode, dur, True, "session=%s" % final.get("session_id", ""))
            done = {"type": "done", "session_id": final.get("session_id"), "duration_s": round(dur, 1)}
            if structured:
                done["data"] = final.get("data")
            else:
                done["text"] = final.get("result", "")
            yield done
        finally:
            timer.cancel()
            _kill(proc)
    finally:
        try:
            os.unlink(rules_file)
        except OSError:
            pass


def _run_stream(proc):
    for raw in proc.stdout:
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            yield {"type": "session", "id": d.get("session_id")}
        elif t == "stream_event":
            ev = d.get("event") or {}
            if d.get("parent_tool_use_id"):
                continue
            if ev.get("type") == "content_block_delta" and (ev.get("delta") or {}).get("type") == "text_delta":
                yield {"type": "delta", "text": ev["delta"].get("text", "")}
            elif ev.get("type") == "content_block_start" and (ev.get("content_block") or {}).get("type") == "tool_use":
                yield {"type": "tool", "name": ev["content_block"].get("name", "")}
        elif t == "assistant":
            # Tool inputs arrive complete on the assistant message: show which file is being read.
            for block in (d.get("message") or {}).get("content") or []:
                if block.get("type") == "tool_use":
                    inp = block.get("input") or {}
                    detail = inp.get("file_path") or inp.get("pattern") or inp.get("path") or ""
                    if detail:
                        yield {"type": "tool", "name": block.get("name", ""),
                               "detail": _rel(str(detail))}
        elif t == "result":
            yield {"type": "_final", "is_error": d.get("is_error"), "result": d.get("result", ""),
                   "session_id": d.get("session_id")}


def _run_structured(proc, mode):
    out = proc.stdout.read().decode("utf-8", "replace")
    try:
        d = json.loads(out)
    except ValueError:
        yield {"type": "_final", "is_error": True, "result": out[-300:]}
        return
    data = d.get("structured_output")
    if data is None and not d.get("is_error"):
        try:
            data = json.loads(d.get("result") or "")
        except ValueError:
            yield {"type": "_final", "is_error": True, "result": "No structured output returned."}
            return
    yield {"type": "_final", "is_error": d.get("is_error"), "result": d.get("result", ""),
           "session_id": d.get("session_id"), "data": data}


def _rel(p):
    if not Path(p).is_absolute():
        return p
    try:
        return str(Path(p).resolve().relative_to(REPO)).replace("\\", "/")
    except (ValueError, OSError):
        return p


def health_check():
    """Startup check: does `claude` exist, run, and answer? Returns a dict for the boot screen."""
    if is_mock():
        return {"ok": True, "mock": True, "version": "mock", "detail": "Mock mode: no Claude calls."}
    exe = find_claude()
    if not exe:
        return {"ok": False, "version": None, "detail": "Claude Code executable not found.",
                "hint": "Install Claude Code, or set JARVIS_CLAUDE to its full path."}
    res = {"exe": exe}
    try:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20, env=child_env(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        res["version"] = (v.stdout or v.stderr).strip().splitlines()[0] if (v.stdout or v.stderr) else ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return dict(res, ok=False, detail="`claude --version` failed: %s" % e,
                    hint="Reinstall Claude Code or set JARVIS_CLAUDE.")
    t0 = time.time()
    p = None
    try:
        p = subprocess.run([exe, "-p", "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
                            "--no-session-persistence", "--output-format", "json"],
                           input="Reply with exactly: OK", capture_output=True, text=True, timeout=60,
                           cwd=str(REPO), env=child_env(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
        d = json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        return dict(res, ok=False, detail="Claude Code did not answer a test prompt within 60 s.",
                    hint="Check your network and run `claude -p \"hi\"` in cmd.exe.")
    except (OSError, ValueError):
        e = _failure(p.stderr if p is not None else "", p.stdout if p is not None else None)
        return dict(res, ok=False, detail=e.message, hint=e.hint)
    res["startup_s"] = round(time.time() - t0, 1)
    if d.get("is_error"):
        e = _failure(p.stderr, d.get("result"))
        return dict(res, ok=False, detail=e.message, hint=e.hint)
    res["model"] = ", ".join(d.get("modelUsage", {}).keys())
    log_call("health", time.time() - t0, True, res.get("version", ""))
    return dict(res, ok=True, detail="Claude Code answered in %.1f s." % res["startup_s"])


if __name__ == "__main__":
    # Manual test: python brain.py ask "question"
    m = sys.argv[1] if len(sys.argv) > 1 else "ask"
    q = sys.argv[2] if len(sys.argv) > 2 else "What is the first step for a VIN short?"
    for ev in ask(m, q):
        if ev["type"] == "delta":
            print(ev["text"], end="", flush=True)
        else:
            print("\n", ev)
