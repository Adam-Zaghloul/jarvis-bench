# Repair methodology

## 1. Before any instrument

### 1.1 Confirm the symptom
Reproduce the fault on the bench before measuring anything. Write the exact symptom in the log.

### 1.1a Rule out the test setup
Check cables, fixtures and how the board is powered. A wrong setup produces "faults" that aren't on the board.

### 1.2 Zero the meter
Short the leads and record the offset. Subtract it from every low-resistance reading.

## 2. Power first
Measure each rail against `test-points.md` before looking at signals. A missing rail explains most downstream faults.

## 3. Compare against a known-good board
When a reading looks odd, measure the same point on a known-good board (A/B). Record both values.

## 4. One change at a time
Replace one part, re-test, log the result. Never replace two parts before re-testing.

## 5. Close out
Write the case from `case-writeup.md`. Update the reference docs with any new known-good values.
