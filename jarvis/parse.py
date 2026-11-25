"""Measurement parsing for quick-log lines. Conservative: if unsure, return None (raw text only).

Accepted shapes (whole line, nothing else):
    TP4 4.98V          C64 5.03 V         U6 pin 32 4.9 V      R47 4.7k
    D3 diode 0.52      VIN short 0.4 ohm  VIN to GND 0.4 ohm    Y1 10 MHz
    PSU_FB 1.25V       R33 1.00 MΩ        C58 0.1 uF           R32 current 12 mA
"""
import re

# Test point: a reference designator (R47, TP4, U6, C64, Y1) optionally with "pin N" / ".N" / "-N",
# or an UPPERCASE net name (VIN, PSU_FB, 5V_SENSOR, BTN, LED_STATUS).
_DESIG = r"(?:[A-Z]{1,3}\d{1,4})(?:\s*(?:pin|p|\.|-|#)\s*\d{1,3})?"
_NET = r"(?:\d?[A-Z][A-Z0-9_]{1,30})"
_TP = r"(?P<tp>%s|%s)" % (_DESIG, _NET)
_MODE_WORDS = {
    "diode": "diode", "d": "diode",
    "short": "resistance", "res": "resistance", "resistance": "resistance", "ohms": "resistance",
    "cont": "resistance", "continuity": "resistance",
    "dc": "dcv", "dcv": "dcv", "volts": "dcv", "voltage": "dcv",
    "ac": "acv", "acv": "acv",
    "cap": "capacitance", "capacitance": "capacitance",
    "freq": "frequency", "frequency": "frequency",
    "current": "current", "amps": "current",
}
_UNITS = {
    # unit text -> (base unit, multiplier, mode)
    "v": ("V", 1, "dcv"), "mv": ("V", 1e-3, "dcv"), "uv": ("V", 1e-6, "dcv"), "µv": ("V", 1e-6, "dcv"),
    "vac": ("V", 1, "acv"),
    "a": ("A", 1, "current"), "ma": ("A", 1e-3, "current"), "ua": ("A", 1e-6, "current"), "µa": ("A", 1e-6, "current"),
    "ohm": ("ohm", 1, "resistance"), "ohms": ("ohm", 1, "resistance"), "ω": ("ohm", 1, "resistance"),
    "r": ("ohm", 1, "resistance"),
    "k": ("ohm", 1e3, "resistance"), "kohm": ("ohm", 1e3, "resistance"), "kω": ("ohm", 1e3, "resistance"),
    "kohms": ("ohm", 1e3, "resistance"),
    "m": ("ohm", 1e6, "resistance"), "mohm": ("ohm", 1e6, "resistance"), "mω": ("ohm", 1e6, "resistance"),
    "meg": ("ohm", 1e6, "resistance"),
    "pf": ("F", 1e-12, "capacitance"), "nf": ("F", 1e-9, "capacitance"), "uf": ("F", 1e-6, "capacitance"),
    "µf": ("F", 1e-6, "capacitance"),
    "hz": ("Hz", 1, "frequency"), "khz": ("Hz", 1e3, "frequency"), "mhz": ("Hz", 1e6, "frequency"),
}
_LINE = re.compile(
    r"^\s*" + _TP +
    r"(?:\s+(?P<mw>[A-Za-z]+))?"            # optional mode word
    r"(?:\s+to\s+GND)?"                      # 'VIN to GND 0.4 ohm'
    r"\s*[:=]?\s+(?P<val>[-+]?\d+(?:[.,]\d+)?)\s*(?P<unit>[A-Za-zµΩω]{1,5})?\s*$", re.I)


def _norm_tp(tp):
    tp = tp.strip()
    m = re.match(r"^([A-Za-z]{1,3}\d{1,4})\s*(?:pin|p|\.|-|#)\s*(\d{1,3})$", tp, re.I)
    if m:
        return "%s.%s" % (m.group(1).upper(), m.group(2))
    return tp.upper()


def parse_reading(text):
    """Return {test_point, value, unit, mode} or None when the line isn't clearly a single reading."""
    if not text or len(text) > 60:
        return None
    t = text.strip()
    m = _LINE.match(t)
    if not m:
        return None
    tp_raw, mw, val, unit = m.group("tp"), m.group("mw"), m.group("val"), m.group("unit")
    # Uppercase-only test points: a lowercase word ("status 5") is not a test point.
    if tp_raw != tp_raw.upper() and not re.match(r"^[A-Z]{1,3}\d", tp_raw):
        return None
    mode = None
    if mw:
        mwl = mw.lower()
        if mwl in _MODE_WORDS:
            mode = _MODE_WORDS[mwl]
        elif mwl in _UNITS and unit is None:
            # 'C64 5 V' parsed as mw=None; 'R47 4.7 k' could land here as mode word 'k'? no: val comes after mw.
            return None
        else:
            return None  # an unknown word between test point and value: not sure
    try:
        v = float(val.replace(",", "."))
    except ValueError:
        return None
    base, mult = None, 1
    if unit:
        u = unit.lower()
        if u not in _UNITS:
            return None
        base, mult, umode = _UNITS[u]
        # 'M' alone: megohm only in resistance context; refuse if mode says otherwise.
        if mode and mode != umode:
            if not (mode == "diode" and base == "V"):
                return None
        mode = mode or umode
    else:
        if mode == "diode":
            base = "V"
        elif mode == "resistance":
            base = "ohm"
        else:
            return None  # a bare number with no unit and no mode word: unsure
    return {"test_point": _norm_tp(tp_raw), "value": round(v * mult, 12), "unit": base, "mode": mode}


_PREFIX = [(1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"), (1e-9, "n"), (1e-12, "p")]


def fmt(value, unit):
    """Human display: 4700 ohm -> '4.7 kΩ', 0.52 V -> '520 mV'."""
    if value is None:
        return ""
    sym = {"ohm": "Ω"}.get(unit, unit)
    a = abs(value)
    if a == 0:
        return "0 %s" % sym
    for mult, p in _PREFIX:
        if unit == "V" and p in ("M", "k"):
            continue
        if a >= mult:
            n = value / mult
            s = ("%.4g" % n)
            return "%s %s%s" % (s, p, sym)
    return "%g %s" % (value, sym)
