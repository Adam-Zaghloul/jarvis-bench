# DEMO-1 test points

Values marked [M] were measured on a known-good board. Power applied unless the row says otherwise.

| Test point | Net | Expected | Notes |
|---|---|---|---|
| C10 + | VIN | 12.0 V | Bench supply set to 12.0 V |
| C20 + | 5V | 5.02 V [M] | U1 output |
| C30 + | 3V3 | 3.31 V [M] | U2 output |
| U3 pin 15 | LED_STATUS | 1 Hz square wave, 0 to 3.3 V | Drives D1 through R14 |
| U3 pin 20 | BTN | 3.3 V released, 0 V pressed | R8 pull-up |
| U3 pin 10 | XOUT | 8 MHz | Probe the clock here only, with a 10x probe |
| U3 pin 9 | XIN | — | Never probe: high-impedance input, probe capacitance can stall the oscillator |

## Power off (resistance to GND)

See `normally-low-impedance.md`.
