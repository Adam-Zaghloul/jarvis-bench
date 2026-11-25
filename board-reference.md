# DEMO-1 board reference

Fictional sensor-node controller, rev A. 12 V in, 5 V and 3.3 V rails, one 8-bit MCU.

| Ref | Value / part | Net | Role | Rework |
|---|---|---|---|---|
| F1 | 1 A fuse | VIN | Input protection | Trivial |
| C10 | 47 µF electrolytic | VIN | Input bulk | Easy |
| C12 | 10 µF MLCC 25 V | VIN | Input decoupling | Easy |
| U1 | 5 V buck regulator | VIN → 5V | Main supply | Medium |
| C20 | 22 µF MLCC | 5V | Buck output | Easy |
| U2 | 3.3 V LDO | 5V → 3V3 | Logic supply | Easy |
| C30 | 10 µF MLCC | 3V3 | LDO output | Easy |
| U3 | 8-bit MCU, 32 pins | 3V3 | Controller | Hard |
| Y1 | 8 MHz crystal | XIN / XOUT | MCU clock | Easy |
| C3, C4 | 22 pF | XIN / XOUT | Crystal load capacitors | Easy |
| D1 | Green LED | LED_STATUS | Status LED | Easy |
| R14 | 330 Ω | LED_STATUS | LED series resistor | Trivial |
| R8 | 10 kΩ | BTN | Button pull-up to 3V3 | Trivial |
| SW1 | Tactile switch | BTN | User button | Easy |
