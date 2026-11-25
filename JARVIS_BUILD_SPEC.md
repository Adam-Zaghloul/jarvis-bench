# JARVIS — bench assistant build spec

Build a local web app called JARVIS on top of this repo. While I repair boards it gives me:

1. **Ask the docs** — answers from this repo's docs, with sources.
2. **Seen this before?** — finds similar past cases in my case write-ups and logs.
3. **End-of-shift debrief** — turns today's log into a Slack update and Jira-style notes.
4. **Quick log** — the data source for 2 and 3.

Put all app code in `jarvis/`. Don't rename, move or restructure my existing docs.

---

## Ground rules (non-negotiable)

- **Local only.** Server binds to `127.0.0.1`. No new cloud services, no API keys, no telemetry, no CDN. Vendor any library or font into `jarvis/`.
- **The brain is Claude Code headless** (`claude -p`), run with this repo as the working directory. That reuses my existing Claude Code login.
- **The brain is read-only.** Allow only Read, Grep, Glob. Explicitly disallow Bash, Edit, Write, WebFetch, WebSearch. Test it: send the brain a prompt that tells it to create a file, and confirm nothing gets written. Record the result in Design notes.
- **Never build a shell string from my text.** Pass the question as an argument list or via stdin.
- **Verify every CLI flag** in this spec against `claude --help` on this machine before relying on it. If a flag doesn't exist or behaves differently, use the real equivalent and note it in Design notes.
- **No silent actions.** JARVIS writes only inside `jarvis/logs/` and `jarvis/debriefs/`. It never sends, posts or edits anything else. Debrief output is copy-to-clipboard only.
- **Bench data stays private.** Logs, debriefs, drafts and settings are git-ignored.
- **Windows first.** I work on Windows from cmd.exe. On Windows, resolve the claude executable with `shutil.which("claude")` (or equivalent), because it may be a `.cmd` shim.
- **One-command start:** `jarvis.bat` at the repo root starts the server and opens the browser.
- Check what's installed (`python --version`, `node --version`) before choosing a stack. Prefer Python with minimal dependencies unless the repo already uses something else.

---

## Phase 0 — Learn the repo (before writing code)

- Read `CLAUDE.md` and map the repo: case write-ups, decision trees, reference tables, datasheets, and their file types.
- Confirm the brain can read the PDFs in this repo. If it can't, note which ones.
- Write the doc map, chosen stack and assumptions under **Design notes** at the bottom of this file.

## Phase 1 — Brain service

Write a backend function `ask(mode, question, context)` that runs `claude -p` with these settings:

- **Rules:** pass the rules below plus the mode's rules. Use the system-prompt append flag if it exists, otherwise prepend them to the prompt.
- **Streaming:** stream the answer to the UI with `--output-format stream-json`. The docs say this also needs `--verbose` and `--include-partial-messages`; verify. Fall back to `--output-format json` if streaming doesn't work.
- **Follow-ups:** use `--resume <session_id>` so follow-ups keep context. "New question" starts a fresh session.
- **Startup time:** measure it with and without `--bare`. If you use `--bare`, it skips CLAUDE.md, so pass the needed project context explicitly.
- **Timeout:** 120 s, with a clear error in the UI that says what happened and what to try.
- **Mock mode:** `JARVIS_MOCK=1` returns canned answers for every mode, so the UI can be built and tested without using my Claude usage.
- **Timing log:** log each call's duration to `jarvis/logs/brain.log`.

### Answer rules (all modes)

- Every factual claim cites file path plus heading or line.
- Separate the answer into two labeled sections: **From your docs** and **General knowledge (not in your docs)**. Keep the second short.
- If the docs don't cover something, say so plainly. Don't guess.
- If two docs disagree, show both and flag the conflict.
- If my question assumes something the docs contradict, say that first.
- Troubleshooting goes one step at a time. Explain why each step is taken, then wait for my reading.
- Flag any step that needs power applied, and any destructive step (desoldering, lifting a pin, cutting a trace).
- Answer in the language I asked in (English or French).
- Keep answers terse and technical. No personality in technical content.

## Phase 2 — Quick log

- **Active board bar:** always visible at the top, showing board type and serial. Every entry attaches to the active board. Switching boards is a deliberate action with a clear visual change, so readings from two boards never get mixed.
- **Entry:** one line of free text, an optional kind (measurement / action / observation / result), and an optional closing status (fixed / escalated / scrap / open).
- **Storage:** `jarvis/logs/YYYY-MM-DD.jsonl`, one JSON object per line with fields `ts`, `board_type`, `serial`, `kind`, `text`, `status`. Append-only, plus an undo for the last entry.
- **Keyboard-first:** one hotkey focuses the log input, and Enter saves.

## Phase 3 — Ask the docs

- **Answer:** streams in, with citations as clickable chips. A chip opens the source file in a side viewer with the cited section highlighted. Render markdown.
- **Buttons:** "Follow-up" and "New question".
- **Board context:** a toggle adds the active board and its log entries from today to the question.

## Phase 4 — Seen this before?

- **Input:** a symptom, prefilled from the active board's latest observation.
- **Fast pass (no AI, instant):** keyword search over the case write-ups and all past logs (markdown, text, csv, jsonl). Shows matching entries right away.
- **Brain pass:** ranks and groups matches into cases, then summarizes the pattern: number of similar cases, fixes that worked, fixes that didn't.
- **Result cards:** date, board type, serial, symptom, fix, outcome, and a link to the source. Never invent a case; every card links to a real entry.
- **Unresolved cases:** shown separately and labeled unresolved.

## Phase 5 — End-of-shift debrief

- **Run:** a "Run debrief" button for today, plus a date picker for other days.
- **Output:** use `--json-schema` for structured output if available. The brain produces:
  1. **Slack update:** 3–6 short lines covering boards worked, fixed / escalated / open, and blockers.
  2. **Per-board Jira-style comment:** symptom, measurements, actions, result, next step. Each line traces back to a log timestamp.
  3. **Open items for tomorrow.**
- **Gap check:** lists boards with no closing status and entries it couldn't place.
- **Copy only:** every block gets a Copy button. Nothing is sent anywhere.
- **Saving:** writes `jarvis/debriefs/YYYY-MM-DD.md`.
- **Language:** a setting for English or French, English by default.

## Phase 6 — The interface (the fun part)

- **Direction:** Iron Man JARVIS HUD meets bench oscilloscope.
- **Signature element: the arc-reactor orb.** It shows state: idle is a slow pulse, thinking is rotating segments or a scope-trace sweep, answering is steady, error is amber. Keep everything else quiet and disciplined.
- **Background:** a faint scope graticule grid.
- **Palette:** deep blue-black base, cyan holographic accent, amber for warnings. Use red only for real failures.
- **Type:** readable at arm's length from the bench (18 px+ body). One technical display face and one body face, both vendored locally.
- **Layout:**
  - Active board bar across the top.
  - Mode switcher on the left (Ask / Seen before / Log / Debrief), each with a visible keyboard shortcut.
  - Conversation in the center.
  - Source viewer on the right.
- **Boot sequence:** once at launch, 2 s max, skippable. It shows real numbers: docs found, past cases on file, today's entries.
- **Status voice:** status lines are dry, brief and butler-like, e.g. "Good morning. 3 boards still open from yesterday." This voice is for status only, never answers, and there's a setting to turn it off.
- **Spoken answers:** optional, off by default. Use browser speech synthesis restricted to voices where `localService === true`. No speech recognition in this version, because browser speech recognition can send audio to a cloud service.
- **Sound effects:** off by default.
- **Quality floor:**
  - Dark theme, but it must stay legible under bright shop lighting; check contrast.
  - Visible keyboard focus.
  - Respects reduced motion.

---

## Done means

- `jarvis.bat` starts everything. The app works offline except for the brain's Claude Code calls.
- Mock-mode smoke tests pass for all four modes.
- One real end-to-end run per mode against my actual docs, with results in Design notes.
- The read-only test from Ground rules has passed.
- A README in `jarvis/` covers how to start it, where logs live, and how to back them up.
- A short entry in `CLAUDE.md` tells future sessions that JARVIS exists and where its rules live.

## How to work

- Build the phases in order and commit locally after each one.
- Don't stop to ask unless something truly blocks you. Record assumptions in Design notes and keep going.
- If something in this spec is wrong for this repo or this machine, say so in Design notes and pick the better option.

## Later (don't build now)

- Local push-to-talk voice input (local Whisper) with a USB foot pedal.
- ESP32 arc-reactor status light over serial.
- Live bench instrument readouts over SCPI.

---

## Design notes

These summarize the decisions made while building V1. (The original dated build log described a real board's
docs and cases, so it isn't included.)

**Brain (`brain.py`, `mock.py`)**
- Rules go in a temp file via `--append-system-prompt-file`; the question goes on **stdin**. argv holds only fixed
  flags, a temp path, a regex-checked session UUID and our own JSON schema. On Windows, if the executable is a
  `.cmd`/`.bat` shim, `_check_argv` refuses any argument containing `& | < > ^ % !` or a newline.
- Read-only: `--allowedTools Read Grep Glob` plus an explicit disallow list (Bash, Edit, Write, WebFetch, WebSearch).
- Streaming: `--output-format stream-json` needs `--verbose`; `--include-partial-messages` gives text deltas.
  Seen before and Debrief use `--output-format json` + `--json-schema` + `--no-session-persistence`.
- Follow-ups use `--resume <session_id>`; "New question" drops the id.
- `--bare` isn't used: it skips the login, so CLAUDE.md loads normally and the brain gets the repo's working rules.
- Timeout: a watchdog kills the process tree (Windows: `taskkill /T /F`) and the UI says what happened and what to try.
- Startup health check: `claude --version` plus one tiny `-p` call with no tools; the result shows on the boot screen.
- Child env strips `CLAUDE_CODE_*`, `CLAUDE_AGENT_SDK*`, `CLAUDE_PID`, `CLAUDE_EFFORT` (set when JARVIS is started
  from inside a Claude Code session).
- `brain.log` gets one JSON line per call (ts, mode, duration, ok, mock); question text is never logged.

**App (`server.py`, `store.py`, `static/`)**
- Python 3.9+ standard library only; no build step; fonts vendored in `static/fonts/`.
- Binds to `127.0.0.1`; checks the Host header; POSTs need `X-Jarvis: 1`; CSP is `'self'` only.
- Every path the UI asks for is resolved inside the repo (or the log folder) before it's read.
- Seen before drops any case whose source file doesn't exist, so the brain can't invent one.
- Debrief text is re-rendered by the server so every line shows the log timestamp it came from; a line whose
  timestamp isn't in the log is marked `⚠ not in log`.
