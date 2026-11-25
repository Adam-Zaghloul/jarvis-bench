# JARVIS V2 — upgrade spec

Upgrade the existing JARVIS in `jarvis/`. Read `JARVIS_BUILD_SPEC.md` (especially its Design notes) first, so you know what V1 does and why.

**All V1 ground rules still apply:** local only, read-only brain, no silent actions, verify CLI flags, Mac launcher `sh jarvis.sh`.

**New data rules:**

- Never alter the raw text of a log entry. Parsed fields sit beside it.
- Anything the AI generates that becomes stored data (close-out fields, patterns, golden-set answers) needs my confirmation before it's saved. Until then it's a draft.
- Generated text that leaves JARVIS (debriefs, handoff notes, weekly review) stays copy-only, as in V1.

Build the phases in order. Commit locally after each one. Decisions are summarized under **Design notes** at the bottom of this file.

---

## Phase 0 — Check before building

- If the broken links in `01-decision-tree.md`, `README.md` and `CLAUDE.md` are still broken, fix the links only. Don't move files.
- Baseline: run each mode once in real mode and record the timings.

## Phase 1 — Structured data (the foundation)

1. **Measurement parsing.** When a quick-log line looks like a reading (`TP4 4.98V`, `R47 4.7k`, `D3 diode 0.52`, `VIN short 0.4 ohm`), store `test_point`, `value`, `unit`, `mode` next to the raw text.
   - Before saving, show the parsed reading as a preview chip, so a garbled dictation gets caught.
   - If the parse is unsure, store the raw text only.
2. **Active board** gains revision and an optional ticket ID (alongside type and serial).
3. **Known-good reference tables.** One file per board type and revision: `jarvis/reference/<board_type>[_<rev>].csv` with columns `test_point, mode, min, max, source, note`.
   - **Range check:** a reading on a listed test point is flagged in or out of range, and the flag shows the source.
   - **Known-good capture:** a "Mark board known-good" action saves that board's readings as known-good samples. A range built from samples is shown separately; it never overwrites a range I typed in.
   - **Conflicts:** if a reference value disagrees with the docs, show both and flag it.
4. **Close-out card.** When I set a board to fixed, escalated or scrap, show a card with these fields: symptom, root cause, fix, parts, outcome, ticket ID, and root-cause status (confirmed or suspected).
   - The brain pre-fills it from that board's log, and I edit and confirm.
   - Nothing is saved until I confirm.
   - The root cause defaults to *suspected* unless I mark it confirmed.
5. **Recurring patterns.** When 3+ confirmed close-outs share a board type, a similar symptom and a similar root cause, create a pattern card that links its cases.
   - I can verify or dismiss each card, and verified patterns show first in Seen before.
   - Choose a simple similarity method and document it.

## Phase 2 — Trust

1. **Feedback on every answer.** Add 👍 / 👎 with an optional reason. A 👎 saves question, answer and citations to `jarvis/evals/candidates.jsonl`.
2. **Golden set.** Draft about 20 questions from my real docs and cases in `jarvis/evals/golden.jsonl`. Each one has an expected outcome: *must cite X*, *must say not in docs*, or *must give exactly one step*.
   - Mark them `draft`; I review them.
   - `sh jarvis.sh eval` runs the set in real mode, prints a pass/fail table and saves dated results.
   - Never edit the golden set automatically.
3. **Predict-first toggle** (default off). When on, troubleshooting questions show a "Your hypothesis (optional)" field before the answer appears.
   - The hypothesis is saved with the entry.
   - The close-out card shows whether it matched the root cause.
   - The weekly review reports my hit rate.
4. **Source label on every answer section:** *from your docs*, *from past cases*, or *general knowledge*.

## Phase 3 — Speed

- **Case index.** Build `jarvis/index/cases.json` with one card per case file and per confirmed close-out (board type, symptom, cause, fix, outcome, path).
  - Rebuild it when files change.
  - The Seen-before brain gets the index plus the top keyword matches instead of reading every file.
  - Target: Seen before under 12 s. Record before and after timings.
- **Ask hints.** Pass the top keyword-matched files to the brain as hints.

## Phase 4 — Daily work

1. **Debrief language per block** (Slack, Jira, open items): English or French. Ask me on the first debrief run, then remember the choice in `jarvis/settings.json`.
2. **Escalation handoff note.** For boards closed as escalated, produce a note covering what was measured, what was tried, what was ruled out, the suspected cause and the suggested next check. Copy-only.
3. **Weekly review** (on demand, plus a nudge on Fridays). It covers:
   - boards worked, with fixed / escalated / scrap counts
   - top symptoms and causes
   - patterns, and open boards
   - median time-on-board
   - predict-first hit rate

   It follows the language setting and saves to `jarvis/debriefs/week-YYYY-WW.md`.
4. **Competency log.** A separate block in the weekly review listing techniques and skills I used, written generally. No part numbers, serials, internal names, product names or ticket IDs; it's for my own career records.
5. **Work-instruction draft.** A verified pattern can produce a markdown draft in `jarvis/drafts/`, clearly marked DRAFT. Never put drafts into my docs.
6. **Time-on-board.** Measure from the first to the last entry per board, excluding gaps over 30 min, and show it on the board bar.

## Phase 5 — Capture friction

1. **Barcode / QR scanner.** Detect keyboard-wedge scans (fast keystrokes ending in Enter, minimum length) anywhere on the page, then ask "Switch to board <serial>?" and confirm with Enter. Normal typing must never trigger it; test that.
2. **Photos.** Paste or drag an image into the log line.
   - It's saved to `jarvis/logs/photos/YYYY-MM-DD/` and linked to the entry.
   - Location metadata is stripped.
   - The debrief lists photos per board.
3. **Quick-log from any app.**
   - Add an endpoint `POST /api/log` on `127.0.0.1` only, protected by a token stored in `jarvis/settings.json`.
   - In the README, write steps for a macOS **Shortcuts** shortcut (built-in app, nothing to install) with a keyboard shortcut. It asks for one line and sends it.

## Phase 6 — Health

1. **Doc audit view** (report only, no edits): broken links, references to missing folders, files never cited in 30 days, oldest files.
2. **Backup.** `sh jarvis.sh backup` copies logs, photos, debriefs, reference, evals and settings to a destination I choose once.
   - It keeps the last 10 copies.
   - The boot line warns if the last backup is over 7 days old.
3. **Usage panel** (local only), per week: entries, questions, Seen-before runs, debriefs, 👍/👎 ratio, and features I didn't use.

## Phase 7 — Interface touches

- **Reading gauge.** A small gauge shows each flagged reading against its range. This is the only new visual element; the orb stays the signature.
- **Board timeline.** Each board's entries in order, with range flags and photos.
- **Boot line** adds open boards from yesterday and the age of the last backup.
- Keep everything else quiet.

---

## Done means

- Mock tests are updated and pass, with new tests for parsing, scan detection and close-out confirmation.
- One real run of each new feature.
- `sh jarvis.sh eval` runs end to end against the draft golden set.
- Before and after timings are recorded for Seen before and Ask.
- The README covers every new feature, the Shortcuts setup and backup.

## Later (don't build now)

- Push-to-talk voice through a local dictation app with a custom vocabulary .
- Live instrument readings through a read-only SCPI MCP server.
- ESP32 arc-reactor status light.
- Microscope capture.

## Never

- Always-on microphone.
- Auto-posting to Slack or Jira.
- A brain that can write files.
- Screen recording.
- Vector DB / Docker / multi-agent stack; not needed at this scale.

---

## Design notes

These summarize the decisions made while building V2. (The original dated build log described a real board's
docs and cases, so it isn't included.)

- **Parsing (`parse.py`):** one reading per line: test point + optional mode word + value + unit. Test points are
  designators (`R47`, `TP4`, `U6 pin 32` → `U6.32`) or UPPERCASE nets. Anything unsure (extra words, no unit and no
  mode word, lowercase words, over 60 characters) is stored as raw text only.
- **Reference ranges (`reference.py`):** ranges you type live in `reference/<board>_<rev>.csv`; known-good samples
  are stored separately and never merged; a doc line that states a value outside a typed range shows as a conflict.
- **Recurring patterns (`closeout.py`):** two close-outs match when they have the same board type, Jaccard ≥ 0.4
  on symptom words, and either Jaccard ≥ 0.4 on root-cause words or a shared designator. Clusters are connected
  components; 3+ confirmed close-outs make a pattern. The pattern id is a hash of its case ids.
- **Eval (`eval.py`):** check types `must_cite`, `not_in_docs`, `one_step`, `expected_verdict`, plus an optional
  `must_contain` list on any type (whole word, case-insensitive, citations ignored; number terms match by value and
  may carry a unit: `2.5` matches `2.50 V` and `2.5V`). It refuses to run in mock mode and never writes the golden set.
- **Scanner (`static/scan.js`):** a scan is ≥ 6 characters, every gap < 50 ms, ended by Enter or Tab within 100 ms.
  It works anywhere on the page, takes the scanned characters back out of a focused field, and always asks before
  switching boards.
- **Photos:** pasted or dropped images are re-encoded in the browser (which drops EXIF/GPS) and saved under
  `logs/photos/YYYY-MM-DD/`.
- **Quick-log API:** `POST /api/log` on `127.0.0.1`, needing a token from `jarvis/settings.json`.
- **Competency log:** the brain is told to write generally, and a server filter drops any item that still contains a
  designator, a long number, a ticket ID, a value with a unit, or a name from the list in `daily.py`.
- **Health (`health.py`, `backup.py`):** the doc audit reports only; backups keep the 10 newest copies and refuse
  destinations inside the repo; the boot line warns after 7 days.
- **Narrated tour (`static/tour.html`):** captions plus a voiceover made with macOS `say` (`tour_audio.py`).
