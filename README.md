# jarvis-bench

Bench documentation for board-level repair, plus **JARVIS**: a local web app that answers questions from
those docs with citations, keeps a bench log with range flags, finds similar past cases, drafts close-outs
and end-of-shift debriefs, and checks itself with a golden-question eval.

The board docs in this repo describe **DEMO-1**, a fictional sensor-node controller. They exist so the app
and its tests run out of the box. Replace them with your own board's docs.

- Start it: `sh jarvis.sh` (Mac) or `jarvis.bat` (Windows). It runs on `127.0.0.1` only and opens in Google Chrome.
- Needs Python 3.9+ (standard library only) and Claude Code logged in (`claude`) for the AI features.
- Usage guide: [`jarvis/README.md`](jarvis/README.md). Specs and build notes: [`JARVIS_BUILD_SPEC.md`](JARVIS_BUILD_SPEC.md), [`JARVIS_V2_SPEC.md`](JARVIS_V2_SPEC.md).
- Tests: `cd jarvis && python3 -m unittest discover -s tests`

## Layout

| Path | What it is |
|---|---|
| `CLAUDE.md` | How the assistant should work with you |
| `00-methodology.md`, `01-decision-tree.md`, `02-short-circuit-workflow.md` | Process docs |
| `board-reference.md`, `test-points.md`, `normally-low-impedance.md`, `field-failure-data.md` | Reference docs |
| `board-log.md`, `case-writeup.md` | Templates |
| `001-*.md`, `<serial>-*.md` | Case write-ups; `*-WIP.md` are open board logs |
| `schematics/`, `datasheets/` | Source PDFs |
| `jarvis/` | The app |

## License

MIT. See [`LICENSE`](LICENSE). The vendored fonts in `jarvis/static/fonts/` are under the SIL Open Font License (see the `OFL-*.txt` files there).
