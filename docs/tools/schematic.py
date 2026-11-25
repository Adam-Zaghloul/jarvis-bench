"""Draw the DEMO-1 schematic as SVG. Values match the demo docs (board-reference.md, test-points.md)."""
import sys

W, H = 1200, 770
INK, NET, MUTED, SHEET = "#1d2733", "#1f5fae", "#7a8794", "#fbfaf6"
out = []
a = out.append


def line(*pts, w=2, c=INK):
    a('<polyline points="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linejoin="round" stroke-linecap="round"/>'
      % (" ".join("%g,%g" % p for p in pts), c, w))


def text(x, y, s, size=14, anchor="start", c=INK, weight="normal", italic=False):
    a('<text x="%g" y="%g" font-size="%g" text-anchor="%s" fill="%s" font-weight="%s"%s>%s</text>'
      % (x, y, size, anchor, c, weight, ' font-style="italic"' if italic else "", s))


def dot(x, y):
    a('<circle cx="%g" cy="%g" r="4" fill="%s"/>' % (x, y, INK))


def gnd(x, y):
    line((x, y), (x, y + 10))
    for i, hw in enumerate((12, 8, 4)):
        line((x - hw, y + 10 + i * 5), (x + hw, y + 10 + i * 5))


def res_v(x, y1, y2, ref, val):          # vertical resistor between y1 and y2 (body 44 px)
    m = (y1 + y2) / 2
    line((x, y1), (x, m - 22)); line((x, m + 22), (x, y2))
    a('<rect x="%g" y="%g" width="16" height="44" fill="%s" stroke="%s" stroke-width="2"/>' % (x - 8, m - 22, SHEET, INK))
    text(x + 16, m - 3, ref, 14, weight="bold"); text(x + 16, m + 14, val, 13, c=MUTED)


def res_h(x1, x2, y, ref, val, below=False):
    m = (x1 + x2) / 2
    line((x1, y), (m - 22, y)); line((m + 22, y), (x2, y))
    a('<rect x="%g" y="%g" width="44" height="16" fill="%s" stroke="%s" stroke-width="2"/>' % (m - 22, y - 8, SHEET, INK))
    if below:
        text(m, y + 28, ref, 14, "middle", weight="bold"); text(m, y + 44, val, 13, "middle", c=MUTED)
    else:
        text(m, y - 16, ref, 14, "middle", weight="bold"); text(m, y + 26, val, 13, "middle", c=MUTED)


def cap_v(x, y1, y2, ref, val, polar=False):
    m = (y1 + y2) / 2
    line((x, y1), (x, m - 5)); line((x, m + 5), (x, y2))
    line((x - 14, m - 5), (x + 14, m - 5), w=2.5)
    if polar:
        a('<path d="M%g %g Q%g %g %g %g" fill="none" stroke="%s" stroke-width="2.5"/>' % (x - 14, m + 9, x, m + 1, x + 14, m + 9, INK))
        text(x - 24, m - 8, "+", 13, "middle")
    else:
        line((x - 14, m + 5), (x + 14, m + 5), w=2.5)
    text(x + 20, m - 3, ref, 14, weight="bold"); text(x + 20, m + 14, val, 13, c=MUTED)


def ic(x, y, w, h, ref, name, left=(), right=(), top=(), bottom=(), ref_left=False):
    a('<rect x="%g" y="%g" width="%g" height="%g" rx="3" fill="#ffffff" stroke="%s" stroke-width="2.2"/>' % (x, y, w, h, INK))
    text(x + 4, y - 10, ref, 15, weight="bold") if ref_left else text(x + w / 2, y - 10, ref, 15, "middle", weight="bold")
    text(x + w / 2, y + h / 2 + 5, name, 13, "middle", c=MUTED)
    pins = {}
    for i, (num, lab, py) in enumerate(left):
        line((x - 22, py), (x, py)); text(x + 8, py + 5, lab, 12); text(x - 6, py - 6, num, 11, "end", c=MUTED)
        pins[lab] = (x - 22, py)
    for num, lab, py in right:
        line((x + w, py), (x + w + 22, py)); text(x + w - 8, py + 5, lab, 12, "end"); text(x + w + 6, py - 6, num, 11, c=MUTED)
        pins[lab] = (x + w + 22, py)
    for num, lab, px in top:
        line((px, y - 22), (px, y)); text(px, y + 18, lab, 12, "middle"); text(px + 6, y - 8, num, 11, c=MUTED)
        pins[lab] = (px, y - 22)
    for num, lab, px in bottom:
        line((px, y + h), (px, y + h + 22)); text(px, y + h - 8, lab, 12, "middle"); text(px + 6, y + h + 16, num, 11, c=MUTED)
        pins[lab] = (px, y + h + 22)
    return pins


def netlabel(x, y, s, anchor="start"):
    text(x, y, s, 13, anchor, c=NET, weight="bold")


def probe(x, y, s, anchor="start"):       # expected reading from test-points.md
    text(x, y, s, 12, anchor, c="#b26b00", italic=True)


a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
  'font-family="Helvetica Neue, Helvetica, Arial, sans-serif">' % (W, H, W, H))
a('<rect width="%d" height="%d" fill="%s"/>' % (W, H, SHEET))
a('<rect x="14" y="14" width="%d" height="%d" fill="none" stroke="%s" stroke-width="1.5"/>' % (W - 28, H - 28, INK))
text(36, 50, "Power", 15, c=MUTED, weight="bold")
text(36, 330, "Controller", 15, c=MUTED, weight="bold")
line((30, 300), (W - 30, 300), w=1, c="#d5d1c6")

# ---------------------------------------------------------------- power row (y = 110)
Y = 110
# J1 connector
a('<rect x="50" y="%g" width="44" height="70" rx="3" fill="#ffffff" stroke="%s" stroke-width="2"/>' % (Y - 20, INK))
text(72, Y - 30, "J1", 15, "middle", weight="bold"); text(72, Y + 70, "12 V in", 12, "middle", c=MUTED)
text(60, Y + 5, "1", 11, c=MUTED); text(60, Y + 35, "2", 11, c=MUTED)
line((94, Y), (130, Y)); line((94, Y + 30), (112, Y + 30), (112, Y + 60)); gnd(112, Y + 60)
# F1 fuse
line((130, Y), (160, Y))
a('<rect x="160" y="%g" width="48" height="16" fill="%s" stroke="%s" stroke-width="2"/>' % (Y - 8, SHEET, INK))
line((160, Y), (208, Y), w=1.5)
text(184, Y - 16, "F1", 14, "middle", weight="bold"); text(184, Y + 28, "1 A", 13, "middle", c=MUTED)
line((208, Y), (420, Y))
netlabel(232, Y - 10, "VIN")
probe(232, Y - 28, "12.0 V")
# C10, C12 on VIN
for cx, ref, val, pol in ((270, "C10", "47 µF", True), (350, "C12", "10 µF", False)):
    dot(cx, Y); cap_v(cx, Y, Y + 100, ref, val, pol); gnd(cx, Y + 100)
# U1 buck
u1 = ic(420, Y - 40, 120, 110, "U1", "5 V buck",
        left=(("1", "IN", Y),), right=(("4", "OUT", Y),), bottom=(("2", "GND", 480),))
gnd(480, Y + 92)
line((562, Y), (700, Y))
netlabel(586, Y - 10, "5V"); probe(586, Y - 28, "5.02 V")
dot(620, Y); cap_v(620, Y, Y + 100, "C20", "22 µF"); gnd(620, Y + 100)
# U2 LDO
u2 = ic(700, Y - 40, 110, 110, "U2", "3.3 V LDO",
        left=(("1", "IN", Y),), right=(("3", "OUT", Y),), bottom=(("2", "GND", 755),))
gnd(755, Y + 92)
line((832, Y), (1010, Y))
netlabel(856, Y - 10, "3V3"); probe(856, Y - 28, "3.31 V")
dot(900, Y); cap_v(900, Y, Y + 100, "C30", "10 µF"); gnd(900, Y + 100)
line((1010, Y), (1010, Y - 14)); line((996, Y - 14), (1024, Y - 14), w=2.5); text(1010, Y - 24, "3V3", 13, "middle", c=NET, weight="bold")

# ---------------------------------------------------------------- controller row
ux, uy, uw, uh = 470, 410, 210, 250
u3 = ic(ux, uy, uw, uh, "U3", "8-bit MCU",
        left=(("9", "XIN", 470), ("10", "XOUT", 560)),
        right=(("15", "LED_STATUS", 450), ("20", "BTN", 610)),
        top=(("4", "VCC", 575),), bottom=(("5", "GND", 575),), ref_left=True)
# VCC / GND
line((575, uy - 22), (575, uy - 40)); line((561, uy - 40), (589, uy - 40), w=2.5); text(575, uy - 50, "3V3", 13, "middle", c=NET, weight="bold")
gnd(575, uy + uh + 22)
# Crystal Y1 between XIN and XOUT with C3/C4
xin, xout = u3["XIN"], u3["XOUT"]
cx = 330
line(xin, (cx, 470)); line(xout, (cx, 560))
# crystal symbol vertical between y 470 and 560 at x = cx
line((cx, 470), (cx, 496)); line((cx, 534), (cx, 560))
line((cx - 16, 496), (cx + 16, 496), w=2.5); line((cx - 16, 534), (cx + 16, 534), w=2.5)
a('<rect x="%g" y="502" width="20" height="26" fill="#ffffff" stroke="%s" stroke-width="2"/>' % (cx - 10, INK))
text(cx + 24, 512, "Y1", 14, weight="bold"); text(cx + 24, 528, "8 MHz", 13, c=MUTED)
for (py, ref) in ((470, "C3"), (560, "C4")):
    dot(cx, py); line((cx, py), (250, py)); cap_v(250, py, py + 70, ref, "22 pF"); gnd(250, py + 70)
probe(xout[0] - 4, 584, "8 MHz: probe here", "end")
probe(xin[0] - 4, 494, "never probe XIN", "end")
# LED path: pin 15 -> R14 -> D1 -> GND
lx = u3["LED_STATUS"]
res_h(lx[0], 860, 450, "R14", "330 Ω", below=True)
probe(lx[0] + 4, 436, "1 Hz square, 0–3.3 V")
line((860, 450), (930, 450), (930, 490))
# LED symbol pointing down
a('<polygon points="%g,490 %g,490 %g,520" fill="#ffffff" stroke="%s" stroke-width="2" stroke-linejoin="round"/>' % (914, 946, 930, INK))
line((914, 520), (946, 520), w=2.5); line((930, 520), (930, 546)); gnd(930, 546)
for dy in (0, 12):
    line((952, 496 + dy), (968, 486 + dy), w=1.5)
    a('<polygon points="%g,%g %g,%g %g,%g" fill="%s"/>' % (968, 486 + dy, 961, 486 + dy, 966, 492 + dy, INK))
text(960, 518, "D1", 14, weight="bold"); text(960, 534, "status LED", 13, c=MUTED)
# BTN: pin 20 with R8 pull-up and SW1 to GND
bx = u3["BTN"]
line(bx, (1000, 610))
dot(840, 610)
res_v(840, 525, 610, "R8", "10 kΩ")
line((840, 525), (840, 514)); line((826, 514), (854, 514), w=2.5); text(840, 504, "3V3", 13, "middle", c=NET, weight="bold")
probe(bx[0] + 4, 632, "3.3 V released · 0 V pressed")
# SW1 vertical at x=1000 from 590 down
line((1000, 610), (1000, 620)); dot(1000, 620)
line((1000, 620), (1020, 648), w=2); dot(1000, 652)
line((1000, 652), (1000, 664)); gnd(1000, 664)
text(1030, 636, "SW1", 14, weight="bold"); text(1030, 652, "button", 13, c=MUTED)
netlabel(bx[0] + 30, 602, "BTN")

# ---------------------------------------------------------------- title block
tx, ty = 760, 690
a('<rect x="%d" y="%d" width="%d" height="50" fill="#ffffff" stroke="%s" stroke-width="1.5"/>' % (tx, ty, W - 30 - tx, INK))
text(tx + 14, ty + 21, "DEMO-1 · sensor-node controller · rev A", 15, weight="bold")
text(tx + 14, ty + 40, "Fictional board for the jarvis-bench demo", 12, c=MUTED)
text(40, H - 34, "Orange italics: expected readings from test-points.md", 12, c="#b26b00", italic=True)
a("</svg>")
sys.stdout.write("\n".join(out))
