"""Draw a stylized top view of the fictional DEMO-1 PCB (100 x 60 mm) as SVG."""
import sys

S = 9                                   # px per mm
M = 40                                  # margin
BW, BH = 100 * S, 60 * S
W, H = BW + 2 * M, BH + 2 * M + 40
BOARD, CU, MASK_CU, SILK, PAD, TP = "#17633f", "#2f8a5c", "#3b9a69", "#f3f1e8", "#d8b25a", "#ff9f1c"
out = []
a = out.append


def X(mm): return M + mm * S
def Y(mm): return M + mm * S


def rect(x, y, w, h, fill, stroke="none", sw=0, rx=0):
    a('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s" stroke="%s" stroke-width="%g"/>' % (X(x), Y(y), w * S, h * S, rx * S, fill, stroke, sw))


def circ(x, y, r, fill, stroke="none", sw=0):
    a('<circle cx="%g" cy="%g" r="%g" fill="%s" stroke="%s" stroke-width="%g"/>' % (X(x), Y(y), r * S, fill, stroke, sw))


def silk(x, y, s, size=2.6, anchor="middle", weight="bold"):
    a('<text x="%g" y="%g" font-size="%g" text-anchor="%s" fill="%s" font-weight="%s">%s</text>' % (X(x), Y(y), size * S, anchor, SILK, weight, s))


def trace(*pts, w=0.6):
    a('<polyline points="%s" fill="none" stroke="%s" stroke-width="%g" stroke-linejoin="round" stroke-linecap="round"/>'
      % (" ".join("%g,%g" % (X(px), Y(py)) for px, py in pts), MASK_CU, w * S))


def chip(x, y, w, h, ref, lx=None, ly=None, vertical=False):
    """Two-terminal SMD part centered at x,y (mm)."""
    if vertical:
        rect(x - w / 2, y - h / 2, w, h * 0.32, PAD); rect(x - w / 2, y + h / 2 - h * 0.32, w, h * 0.32, PAD)
        a('<rect x="%g" y="%g" width="%g" height="%g" fill="none" stroke="%s" stroke-width="1.2"/>' % (X(x - w / 2 - .5), Y(y - h / 2 - .5), (w + 1) * S, (h + 1) * S, SILK))
    else:
        rect(x - w / 2, y - h / 2, w * 0.32, h, PAD); rect(x + w / 2 - w * 0.32, y - h / 2, w * 0.32, h, PAD)
        a('<rect x="%g" y="%g" width="%g" height="%g" fill="none" stroke="%s" stroke-width="1.2"/>' % (X(x - w / 2 - .5), Y(y - h / 2 - .5), (w + 1) * S, (h + 1) * S, SILK))
    silk(lx if lx is not None else x, ly if ly is not None else y - h / 2 - 1.4, ref)


def testpoint(x, y):
    circ(x, y, 1.9, "none", TP, 2.4)


a('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" font-family="Helvetica Neue, Helvetica, Arial, sans-serif">' % (W, H, W, H))
a('<rect width="%d" height="%d" fill="#0f1720"/>' % (W, H))
# board + copper pour hint
rect(0, 0, 100, 60, BOARD, "#0b3d26", 3, rx=2.5)
a('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="none" stroke="%s" stroke-width="1" stroke-dasharray="4 4" opacity="0.5"/>' % (X(2), Y(2), 96 * S, 56 * S, 2 * S, CU))
for hx, hy in ((4, 4), (96, 4), (4, 56), (96, 56)):
    circ(hx, hy, 2.2, PAD); circ(hx, hy, 1.3, "#0f1720")

# U3 TQFP-32: pins 1-8 left (top→bottom), 9-16 bottom (left→right), 17-24 right (bottom→top), 25-32 top
ux, uy = 55, 40
def pin(n):
    k = (n - 1) % 8; off = -3.15 + k * 0.9
    side = (n - 1) // 8
    if side == 0: return (ux - 5.25, uy + off)
    if side == 1: return (ux + off, uy + 5.25)
    if side == 2: return (ux + 5.25, uy - off)
    return (ux - off, uy - 5.25)

# traces
trace((6, 12), (12, 12), (12, 14), (13, 14), w=1.2)                       # J1 -> F1
trace((17, 14), (36, 14), (36, 10.95), (38.6, 10.95), w=1.2)             # VIN -> U1 IN
trace((22, 14), (22, 17.8), w=0.8); trace((30, 14), (30, 17.4), w=0.8)   # C10, C12
trace((50.4, 16.95), (53, 16.95), (53, 14), (62, 14), (62, 20.5), (67.4, 20.5), (67.4, 18.4), w=1.0)  # 5V
trace((57, 14), (57, 17.4), w=0.8)                                         # C20
trace((72.6, 18.4), (72.6, 22), (86, 22), (86, 28), (46, 28), (46, pin(4)[1]), (pin(4)[0] - .7, pin(4)[1]), w=0.8)  # 3V3 -> VCC
trace((82, 22), (82, 23.4), w=0.8)                                         # C30
p9, p10, p15, p20 = pin(9), pin(10), pin(15), pin(20)
trace((p9[0], p9[1] + .7), (p9[0], 50.9), (39, 50.9))                     # XIN -> Y1
trace((p10[0], p10[1] + .7), (p10[0], 56), (27, 56), (27, 50.9), (29.5, 50.9))  # XOUT -> Y1
trace((44, 50.9), (44, 53.4)); trace((27, 53), (27, 53.5))                # C3, C4 stubs
trace((p15[0], p15[1] + .7), (p15[0], 52), (70.4, 52))                    # LED_STATUS -> R14
trace((74.6, 52), (83.6, 52))                                              # R14 -> D1
trace((p20[0] + .7, p20[1]), (84, p20[1]))                                 # BTN -> SW1
trace((74, 28), (74, 31.5)); trace((74, 36.5), (74, p20[1]))              # R8 pull-up

# J1 2-pin header
rect(3, 9, 6, 11, "#1c1c1c", SILK, 1.2, rx=.6)
circ(6, 12, 1.2, PAD); circ(6, 17, 1.2, PAD)
silk(6, 23.5, "J1"); silk(6, 7.6, "12V", 2.0, weight="normal")
chip(15, 14, 6, 3, "F1")
# C10 electrolytic
circ(22, 22, 4.2, "#2a2a2a", SILK, 1.2); circ(22, 22, 3.2, "#3a3a3a")
a('<path d="M%g %g A%g %g 0 0 1 %g %g" fill="none" stroke="%s" stroke-width="2"/>' % (X(18.6), Y(19.6), 4.2 * S, 4.2 * S, X(25.4), Y(19.6), SILK))
silk(22, 29.2, "C10")
chip(30, 19, 2.2, 4, "C12", vertical=True)
# U1 SOIC-8
rect(40, 9.5, 9, 9, "#222", rx=.4)
for i in range(4):
    rect(38.6, 10.5 + i * 2, 1.4, .9, PAD); rect(49, 10.5 + i * 2, 1.4, .9, PAD)
circ(41.3, 10.9, .45, "#666"); silk(44.5, 8.2, "U1")
chip(57, 19, 2.2, 4, "C20", vertical=True)
# U2 SOT-223
rect(66, 10, 8, 6.5, "#222", rx=.3); rect(67.2, 7.6, 5.6, 2, PAD)
for i in range(3):
    rect(66.8 + i * 2.6, 16.6, 1.2, 1.8, PAD)
silk(76.5, 13.6, "U2", anchor="start")
chip(82, 25, 2.2, 4, "C30", vertical=True, lx=86.5, ly=26.2)

# U3
rect(ux - 4.5, uy - 4.5, 9, 9, "#1f1f1f", rx=.3)
for n in range(1, 33):
    px, py = pin(n)
    side = (n - 1) // 8
    if side in (0, 2): rect(px - .65, py - .2, 1.3, .4, PAD)
    else: rect(px - .2, py - .65, .4, 1.3, PAD)
circ(ux - 3.4, uy - 3.4, .5, "#5a5a5a")
silk(ux - 8, uy - 5.5, "U3", anchor="end")
# Y1, C3, C4
rect(29.5, 49, 9.5, 3.8, "#c9ccd1", "#9aa0a8", 1, rx=1.9); silk(34.2, 47.4, "Y1")
chip(44, 54.5, 2.2, 3.2, "C3", vertical=True, lx=47.5, ly=55.4)
chip(27, 54.8, 2.2, 3.2, "C4", vertical=True, lx=23.4, ly=55.6)
# R14, D1
chip(72.5, 52, 4, 2.2, "R14")
circ(86, 52, 2.4, "#e6f7ea", "#9cd3ab", 1); circ(86, 52, 1.2, "#7be08f"); silk(86, 57.4, "D1")
# R8, SW1
chip(74, 34, 2.2, 4, "R8", vertical=True, lx=70.4, ly=35)
rect(84, 35.5, 9, 9, "#2b2b2b", SILK, 1.2, rx=.6); circ(88.5, 40, 2.4, "#4a4a4a"); silk(88.5, 47.4, "SW1")

# test points from test-points.md
for tx, ty in ((22, 18.6), (57, 17.6), (82, 23.6), (p10[0], p10[1] + 1.2), (p15[0], p15[1] + 1.2), (p20[0] + 1.2, p20[1])):
    testpoint(tx, ty)
silk(50, 3.9, "DEMO-1  rev A", 2.6)
# caption
a('<circle cx="%g" cy="%g" r="9" fill="none" stroke="%s" stroke-width="3"/>' % (M + 10, H - 28, TP))
a('<text x="%g" y="%g" font-size="15" fill="#c9d2dc">Test points from test-points.md: C10 (VIN), C20 (5V), C30 (3V3), U3 pins 10 / 15 / 20</text>' % (M + 30, H - 23))
a('<text x="%g" y="%g" font-size="15" fill="#7d8a97" text-anchor="end">Fictional board · 100 × 60 mm</text>' % (W - M, H - 23))
a("</svg>")
sys.stdout.write("\n".join(out))
