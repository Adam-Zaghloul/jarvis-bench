# JARVIS — bench assistant

A local web app on top of this repo. It runs on your machine only (`127.0.0.1`) and opens in **Google Chrome**.

| View | Key | What it does | Uses Claude? |
|---|---|---|---|
| Ask | Alt+1 | Answers from the repo docs, with clickable citations, in three labelled sections | yes |
| Seen before | Alt+2 | Verified patterns first, then a keyword search over past cases and logs, then a brain pass that groups them | keyword pass no, brain pass yes |
| Log | Alt+3 | The day's bench log: readings with range flags, photos, undo last entry | no |
| Debrief | Alt+4 | Slack update + per-board Jira notes + open items + gap check + photos | yes |
| Board | Alt+5 | One board's timeline, its close-outs, its known-good reference | close-out draft only |
| Patterns | Alt+6 | Recurring faults across close-outs: verify or dismiss, draft a work instruction | WI draft only |
| Weekly review | Alt+7 | The week's counts, top causes, patterns, competency log | competency log only |
| Health | Alt+8 | Backup status, weekly usage, doc audit | no |

Specs: [`../JARVIS_BUILD_SPEC.md`](../JARVIS_BUILD_SPEC.md) (V1) and [`../JARVIS_V2_SPEC.md`](../JARVIS_V2_SPEC.md) (V2). Decisions are under **Design notes** at the bottom of each.

## Start it

**Mac:** `sh jarvis.sh` (from the repo root). It starts the server on `http://127.0.0.1:8765/` and opens it in Google Chrome.
**Windows:** double-click `jarvis.bat`. Close the black JARVIS window (or press Ctrl+C in it) to stop.

JARVIS opens **Google Chrome only**. It never falls back to another browser. If Chrome isn't found it prints the address; paste that into Chrome.

You need:
- Python 3.9 or newer (`python3 --version`). No pip installs.
- Claude Code, logged in (`claude --version`, then run `claude` once to log in). If the boot screen says **Brain offline**, follow its message. Quick log, scanning, photos, Board, Patterns and Health still work without it.

Other commands:

| Command | What it does |
|---|---|
| `sh jarvis.sh backup` | Back up your bench data (see **Backup** below) |
| `sh jarvis.sh eval` | Run the golden set (20 draft questions) against the real brain (~1 min). Results go to `jarvis/evals/results/` |
| `sh jarvis.sh --port 8800` | Use another port |

Environment options: `JARVIS_MOCK=1` (canned answers, no Claude usage) · `JARVIS_CLAUDE=/path/to/claude` (if `claude` isn't on PATH) · `JARVIS_MODEL=opus` · `JARVIS_TIMEOUT=180`. On Windows, use `set NAME=value` first.

## Keys

`/` jump to the quick log · `Enter` save or send · `m:` `a:` `o:` `r:` at the start of a log line set the kind (measurement / action / observation / result) · `Alt+B` switch board · `Alt+Z` undo last entry · `Alt+X` save the current line as text only (ignore the parsed reading) · `Alt+N` new question · `Alt+1`…`Alt+8` views · `Esc` stop an answer or close a dialog.

## Logging

**Board details.** Switch board (Alt+B) asks for type, serial, **revision** (e.g. A) and an optional **ticket** (e.g. `DEMO-1234`). They show on the board bar with **time on board**: first to last entry, counting only gaps of 30 min or less.

**Readings are parsed as you type.** A line that is a single reading, like `TP4 4.98V`, `U6 pin 32 4.9 V`, `R47 4.7k`, `VIN to GND 0.4 ohm` or `Y1 10 MHz`, shows a preview chip (`TP4 = 4.98 V · dcv`) before you press Enter.
- Your raw text is always stored exactly as typed. The parsed value is stored next to it.
- If the parse is wrong, press **Alt+X** and only the text is saved.
- A line with anything extra (`TP4 4.98 V after reflow`) stays text only; that's intended.

**Range flags.** A parsed reading is checked against `jarvis/reference/<TYPE>_<REV>.csv`:
- **in** or **OUT** (with a small gauge), using the min/max you typed
- **no range** if there's no row for that test point
- the spread of readings from boards you marked known-good, shown separately
- ⚠ when your range disagrees with the doc line it cites

You type the ranges; JARVIS never invents tolerances. `DEMO_A.draft.csv` has 11 candidate rows with the doc value quoted and min/max left blank. Fill one in and move it to `DEMO_A.csv`.

**Known-good.** In the Board view, "Mark known-good" (you confirm the serial) adds that board's parsed readings to `<TYPE>_<REV>.samples.jsonl`.

**Barcode / QR scanner.** Scan a serial anywhere on the page. JARVIS asks "Scanned: switch to board `<serial>`?"; press Enter to switch or Esc to cancel. A scan is at least 6 characters, each under 50 ms apart, ended by Enter or Tab. Normal typing (even fast) never triggers it, and the scanned characters are taken back out of whatever field had focus.

**Photos.** Paste an image into the log line (Cmd+V) or drop it onto the log bar.
- Location data and all other metadata are stripped twice: once in Chrome (re-encoded, longest side 2400 px) and again on the server before saving.
- Saved to `jarvis/logs/photos/YYYY-MM-DD/`. The chips under the log line attach to the next entry; an entry can be photo-only.
- Thumbnails show in the Log and Board views; the debrief lists photos per board.

## Close-outs and patterns

**Close-out card.** When a board gets fixed / escalated / scrap, JARVIS offers a close-out card: symptom, root cause, confirmed or suspected, parts replaced, measurements that proved it, time on board.
- The brain pre-fills it from the board's log. Root cause always starts as **suspected**; only you can mark it **confirmed**.
- **Nothing is saved until you press Confirm** (unsaved edits survive a reload). Saved to `jarvis/logs/closeouts.jsonl`.

**Patterns** (Alt+6).
- **What counts as a pattern:** 3 or more close-outs whose symptoms match and that share a root cause or a part.
- **Your call:** verify or dismiss each one. Verified patterns show first in Seen before.
- **Work-instruction draft:** for verified patterns only. Saved to `jarvis/drafts/<pattern>-YYYY-MM-DD.md` with a **DRAFT — not reviewed** banner. It never goes into your docs.

## Trust

- **Labelled answers.** Ask answers are split into **From your docs**, **From past cases** and **General knowledge (not in your docs)**. Troubleshooting answers give **one step** and ask for the reading.
- **Predict first** (Settings ⚙): before a troubleshooting answer is shown, you type your hypothesis. The close-out and weekly review then show how often you were right.
- **👍 / 👎** under each answer. A 👎 with a reason goes to `jarvis/evals/candidates.jsonl`, for you to promote into the golden set by hand. JARVIS never edits the golden set.

## Daily and weekly

- **Escalation handoff note:** in the Board view, for escalated boards only. It covers what was measured, tried and ruled out (with evidence), plus one next check. Copy only; not saved.
- **Weekly review** (Alt+7): pick the ISO week and press Run. It shows boards, fixed / escalated / scrap / open, top symptoms, causes and parts, patterns, median time on board and the predict-first hit rate.
  - **Competency log:** written generally. Serials, designators, values, ticket IDs and product names are removed, and the review says how many items were removed.
  - **Saved** to `jarvis/debriefs/week-YYYY-WW.md`.
  - **Reminder:** on Fridays the status line nudges you until it's done.

## Quick-log from any app (macOS Shortcuts)

`POST http://127.0.0.1:8765/api/log` adds one line to the **active board**. It needs your token.

**1. Get your token.** It's created on first start, in `jarvis/settings.json` (git-ignored; keep it private):

```sh
grep api_token jarvis/settings.json
```

**2. Build the shortcut** (Shortcuts app, built in, nothing to install):
1. Shortcuts → **File → New Shortcut**. Name it `Bench log`.
2. Add **Ask for Input**. Input type: **Text**. Prompt: `Log line`.
3. Add **Get Contents of URL**:
   - URL: `http://127.0.0.1:8765/api/log`
   - Click **Show More**. Method: **POST**.
   - Headers: add `Authorization` = `Bearer <your token>`.
   - Request Body: **JSON**. Add a **Text** field with key `text` and value **Provided Input** (the variable from step 2).
4. Optional: add **Show Notification** with **Contents of URL**, so you see the saved line or the error.
5. Open the shortcut's details (ⓘ in the right sidebar) → **Add Keyboard Shortcut**. Press something free, e.g. ⌃⌥L.

Now press ⌃⌥L in any app, type `TP4 4.98V`, and press Enter. It lands on the active board, parsed and flagged like a line typed in JARVIS. JARVIS must be running.

You can also send `kind` and `status` (`{"text": "Replaced R14", "kind": "action", "status": "fixed"}`), or plain text. From Terminal:

```sh
curl -H "Authorization: Bearer <token>" --data-binary "C64 5.03 V" http://127.0.0.1:8765/api/log
```

A missing or wrong token gets **401**. If no board is active you get **400** ("No active board. Set the board first.").

## Backup

```sh
sh jarvis.sh backup                    # first time: asks for the folder, then remembers it
sh jarvis.sh backup --dest /Volumes/BENCHUSB/jarvis   # set or change the folder
sh jarvis.sh backup --status           # where, and when the last one was
```

(Windows: `jarvis.bat backup --dest E:\jarvis`.)

- **What's copied:** `logs/` (bench logs, photos, close-outs, patterns, usage), `debriefs/`, `reference/`, `evals/`, `drafts/` and `settings.json`, into `<folder>/jarvis-backup-YYYY-MM-DD_HHMMSS/`, with a `manifest.json`.
- **Keeps the newest 10 copies.** It only ever deletes folders with that exact name.
- **Pick a USB drive or a local backed-up disk**, not a synced cloud folder: the logs are confidential and `settings.json` holds your token. The folder must be outside this repo.
- **Reminders:** the boot screen shows the last backup's age, and the status line turns amber after 7 days or if there's never been one. The Health view (Alt+8) shows the same.
- Backup runs only from Terminal; the web page can't write outside JARVIS's own folders.

## Health (Alt+8)

- **Backup:** last backup, folder, and the command.
- **Usage, per week:**
  - entries, boards, questions, Seen-before runs, debriefs
  - 👍/👎 ratio
  - a table of every feature with its count, and which ones you didn't use
  - counts only: no question text is stored
- **Doc audit (report only; it never edits your docs):**
  - broken markdown links
  - back-ticked paths to folders or files that don't exist (e.g. old `reference/…` paths)
  - docs the brain hasn't cited in 30 days. Tracking started with V2; it records cited paths only.
  - the oldest files by last-modified date

## What it can and can't do

- **Read-only brain.** The brain is `claude -p` running in this repo with **Read, Grep and Glob only**. Bash, Edit, Write, WebFetch, WebSearch and every MCP connector are blocked. It can't change your docs or post anything.
- **Where JARVIS writes:** only to `jarvis/logs/`, `jarvis/debriefs/`, `jarvis/drafts/`, `jarvis/reference/` (known-good samples), `jarvis/evals/` (👎 candidates, eval results) and `jarvis/settings.json`. Backups go to the folder you chose.
- **No AI data without you:**
  - Close-out cards are saved only when you press Confirm.
  - Root causes start as suspected.
  - Work instructions are drafts outside your docs.
- **Nothing is sent anywhere.** Debrief, handoff and weekly text are copy-to-clipboard; nothing goes to Slack or Jira.
- **Local only.** The server listens on 127.0.0.1, so other machines can't reach it. POSTs need a custom header; `/api/log` also needs the token.

## Where your data lives

| What | Where |
|---|---|
| Bench log, one file per day | `jarvis/logs/YYYY-MM-DD.jsonl` (`ts, board_type, serial, kind, text, status`, plus `rev`, `ticket`, `reading`, `photos`, `source` when set) |
| Photos | `jarvis/logs/photos/YYYY-MM-DD/` |
| Close-outs / pattern states / hypotheses | `jarvis/logs/closeouts.jsonl`, `patterns.json`, `hypotheses.jsonl` |
| Usage counts / brain citations | `jarvis/logs/usage.jsonl`, `citations.jsonl` (counts and paths only) |
| Active board | `jarvis/logs/active.json` |
| Brain call timings | `jarvis/logs/brain.log` (mode, duration, ok; question text is not stored) |
| Debriefs and weekly reviews | `jarvis/debriefs/YYYY-MM-DD.md`, `week-YYYY-WW.md` |
| Work-instruction drafts | `jarvis/drafts/` |
| Reference ranges | `jarvis/reference/<TYPE>_<REV>.csv` (yours), `.draft.csv`, `.samples.jsonl` |
| Golden set / 👎 candidates / eval results | `jarvis/evals/golden.jsonl`, `candidates.jsonl`, `results/` |
| Token, backup folder, last backup | `jarvis/settings.json` (git-ignored) |

## Tests

`python3 -m unittest discover -s jarvis/tests -v`. These run in mock mode against a temp folder; they don't use Claude or touch your real logs. The scanner timing tests (`jarvis/tests/scan_test.js`) run inside the suite when `node` is installed.
