# Case 001 — VIN shorted to GND, C12

**Board / rev:** DEMO-1 rev A
**Date:** 2026-01-12
**Status:** RESOLVED

## Symptom
No power. Bench supply hit its current limit at 12 V.

## Root cause
C12 (10 µF MLCC on VIN) cracked and shorted. VIN read 0.3 Ω to GND after subtracting a 0.2 Ω lead offset.

## Fix
Replaced C12. VIN reads 2.4 kΩ to GND, matching `normally-low-impedance.md`. Rails 12.0 V / 5.02 V / 3.31 V.

## Lesson
Thermal camera at 1 A found C12 in under a minute. Zero the leads first.
