# Project context for Claude Code

This repo is bench documentation for board-level repair, plus **JARVIS**, a local bench
assistant that answers from these docs. The docs here describe **DEMO-1**, a fictional
sensor-node controller board. Replace them with your own board's docs.

## What I want help with

- **Live diagnosis.** I describe a symptom and measurements; help me work
  `01-decision-tree.md` and narrow the fault.
- **Logging.** Copy `board-log.md` to a new `<serial>-<symptom>-WIP.md` in the repo root and fill it as I
  report measurements.
- **Write-ups.** Turn a completed log into a case file from `case-writeup.md`, and update the
  reference files with any new known-good values.
- **Keeping the reference accurate.** When a value is confirmed or disproven, update
  `board-reference.md` / `test-points.md` / `normally-low-impedance.md` and flag anything now contradicted elsewhere.

## How I work — please match this

- **One step at a time.** Give me one measurement, wait for the result, then the next.
- **Explain *why* I am measuring something**, not just what to probe.
- **Accuracy over speed.** Every claim traceable to the schematic, the BOM, or a datasheet. If something is
  derived, show the arithmetic. If it is an assumption, say so.
- **Tell me when you are wrong or unsure.**
- **Do not carry forward discarded assumptions.**
- **Concise.** No hedging, no padding.

## Conventions in these files

- **[V]** verified from schematic/datasheet/hardware · **[D]** derived, arithmetic shown · **[A]** assumed, unconfirmed
- **[M]** measured on a known-good board
- **⚠** marks a contradiction or unreliable reading that needs re-verification before anyone acts on it
- One board per log file, serial number at the top.

## Hard-won rules worth enforcing on me

1. **Zero the meter leads before trusting any low reading.** A lead offset can make a copper short look like a
   part failure. Ask me for the offset if I have not recorded it.
2. **Map the full net across all sheets before removing the first part.**
3. **Above ~10 kΩ on a power rail is not a short.**
4. **A block that was never commanded cannot be the fault.**
5. **Firmware before silicon** when every hardware block measures healthy.
6. **Static output is not a fault if the input is also static.**
7. If several readings look impossible, **check the meter against a known voltage** first.

## Missing pieces

`schematics/` holds `DEMO_Schematic.pdf` (one sheet). `datasheets/` is empty. If a question needs a
datasheet that isn't loaded, say so rather than working from recall.

`docs/` holds README images, demo-board drawings and the scripts that generate them. It is not repair
documentation and its demo data is not a real case: never cite it.

## JARVIS (bench app in `jarvis/`)

A local web app (`sh jarvis.sh` on Mac, `jarvis.bat` on Windows; opens in Chrome only) that
runs `claude -p` in this repo as a **read-only** brain (Read/Grep/Glob only). Its rules live in
`jarvis/brain.py` (`ANSWER_RULES`, `MODE_RULES`). Specs and build notes are in
`JARVIS_BUILD_SPEC.md` (V1) and `JARVIS_V2_SPEC.md` (V2), and usage is in `jarvis/README.md`.
Bench logs are `jarvis/logs/YYYY-MM-DD.jsonl`, one board per entry; close-outs are
`jarvis/logs/closeouts.jsonl`. JARVIS's Health view (Alt+8) audits these docs for stale links.
Don't move or rename docs without checking `jarvis/store.py` `classify()`, which sorts files by name.

## Current state (demo)

- `001-vin-short-c12.md` — resolved, C12 shorted MLCC on VIN
- `10000000000011-led-not-blinking-R14.md` — resolved, R14 open (status LED series resistor)
- `10000000000012-led-not-blinking-C4.md` — resolved, C4 open (crystal load capacitor)
- `10000000000013-led-not-blinking-WIP.md` — open
