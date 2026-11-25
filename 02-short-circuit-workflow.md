# Short-circuit workflow

1. Zero the meter leads and record the offset (`00-methodology.md` §1.2).
2. Measure the rail to GND, power off. Compare with `normally-low-impedance.md`.
3. Decide if it is a short:

| Reading (rail to GND) | Meaning |
|---|---|
| < 10 Ω | Short. Continue below. |
| 10 Ω – 10 kΩ | Suspicious. Compare with a known-good board. |
| > 10 kΩ | Not a short. Stop chasing it. |

4. Map every part on the net across all schematic sheets before removing anything.
5. Inject a limited current (1 A max, 1 V) and find the hot part with a thermal camera or by touch.
6. Remove only the hot part. Re-measure.
