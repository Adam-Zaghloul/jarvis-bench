# DEMO-1 decision tree

Start at the branch that matches the symptom. One measurement at a time.

## BRANCH 1 — No power

1. Power off. Measure VIN to GND at C10 (resistance). Below 10 Ω → go to `02-short-circuit-workflow.md`.
2. ⚡ POWER ON. Measure VIN at C10. Expect 12.0 V. Missing → check F1 and J1.
3. Measure the 5V rail at C20. Expect 5.02 V. Missing with VIN present → U1.
4. Measure the 3V3 rail at C30. Expect 3.31 V. Missing with 5V present → U2.

## BRANCH 2 — Status LED never blinks

1. Confirm all three rails first (BRANCH 1, steps 2–4).
2. ⚡ POWER ON. Scope U3 pin 10 (XOUT) for 8 MHz. Never probe pin 9 (XIN): see `test-points.md`.
   No clock → check Y1, C3 and C4 (22 pF load capacitors).
3. Scope U3 pin 15 (LED_STATUS). Expect a 1 Hz square wave, 0 to 3.3 V.
   Toggling but LED dark → measure R14 (330 Ω) and D1.
4. Clock present, pin 15 static → reflash firmware before suspecting U3 (firmware before silicon).

## BRANCH 3 — Button not detected

1. ⚡ POWER ON. Measure BTN at U3 pin 20. Expect 3.3 V released, 0 V pressed.
2. Stuck high when pressed → SW1. Stuck low when released → R8 (10 kΩ pull-up) open.
