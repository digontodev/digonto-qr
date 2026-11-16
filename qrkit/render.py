"""QR matrix -> SVG text with many styles (dots, eyes, gradient, logo, frame). Standard library only.
One SVG is the single source: the app previews it, and exports PNG / PDF / SVG from it."""
import base64

DOT_STYLES = ["square", "rounded", "dots", "diamond", "liquid", "leaf", "vbars", "hbars"]
EYE_OUTER = ["square", "rounded", "circle", "leaf"]
EYE_INNER = ["square", "rounded", "circle", "diamond"]
PLATES = ["none", "square", "rounded", "circle"]
FRAMES = ["none", "box", "banner"]

DEFAULT = {
    "dots": "square", "dot_size": 1.0, "eye_outer": "square", "eye_inner": "square",
    "fg": "#000000", "fg2": "#000000", "gradient": "none", "angle": 45,
    "eye_same": True, "eye_outer_color": "#000000", "eye_inner_color": "#000000",
    "bg": "#FFFFFF", "bg_on": True, "bg_round": 0.0, "quiet": 4,
    "logo_size": 0.2, "plate": "rounded", "plate_color": "#FFFFFF", "plate_pad": 0.12,
    "frame": "none", "frame_color": "#000000", "label_color": "#FFFFFF",
}


def n(v):
    s = ("%.3f" % v).rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def rrect(x, y, w, h, tl=0.0, tr=0.0, br=0.0, bl=0.0):
    p = [f"M{n(x + tl)} {n(y)}", f"H{n(x + w - tr)}"]
    if tr:
        p.append(f"A{n(tr)} {n(tr)} 0 0 1 {n(x + w)} {n(y + tr)}")
    p.append(f"V{n(y + h - br)}")
    if br:
        p.append(f"A{n(br)} {n(br)} 0 0 1 {n(x + w - br)} {n(y + h)}")
    p.append(f"H{n(x + bl)}")
    if bl:
        p.append(f"A{n(bl)} {n(bl)} 0 0 1 {n(x)} {n(y + h - bl)}")
    p.append(f"V{n(y + tl)}")
    if tl:
        p.append(f"A{n(tl)} {n(tl)} 0 0 1 {n(x + tl)} {n(y)}")
    return "".join(p) + "Z"


def circle(cx, cy, r):
    return f"M{n(cx - r)} {n(cy)}a{n(r)} {n(r)} 0 1 0 {n(2 * r)} 0a{n(r)} {n(r)} 0 1 0 {n(-2 * r)} 0Z"


def diamond(cx, cy, r):
    return f"M{n(cx)} {n(cy - r)}L{n(cx + r)} {n(cy)}L{n(cx)} {n(cy + r)}L{n(cx - r)} {n(cy)}Z"


def _is_finder(x, y, size):
    return (x < 8 and y < 8) or (x >= size - 8 and y < 8) or (x < 8 and y >= size - 8)


def _data_modules(qr, skip):
    size = qr.size
    dark = [[qr.dark(x, y) and not _is_finder(x, y, size) and not skip(x, y) for x in range(size)] for y in range(size)]
    return dark


def _dots_path(dark, size, style, sz):
    inset = (1 - sz) / 2
    g = lambda x, y: 0 <= x < size and 0 <= y < size and dark[y][x]
    out = []
    if style in ("vbars", "hbars"):
        for a in range(size):
            b = 0
            while b < size:
                x, y = (a, b) if style == "vbars" else (b, a)
                if dark[y][x]:
                    e = b
                    while e + 1 < size and (dark[e + 1][a] if style == "vbars" else dark[a][e + 1]):
                        e += 1
                    ln = e - b + 1
                    if style == "vbars":
                        out.append(rrect(a + inset, b + inset, sz, ln - 2 * inset, sz / 2, sz / 2, sz / 2, sz / 2))
                    else:
                        out.append(rrect(b + inset, a + inset, ln - 2 * inset, sz, sz / 2, sz / 2, sz / 2, sz / 2))
                    b = e + 1
                else:
                    b += 1
        return "".join(out)
    for y in range(size):
        for x in range(size):
            if not dark[y][x]:
                continue
            if style == "square":
                out.append(f"M{n(x + inset)} {n(y + inset)}h{n(sz)}v{n(sz)}h{n(-sz)}Z")
            elif style == "rounded":
                out.append(rrect(x + inset, y + inset, sz, sz, *(sz * 0.32,) * 4))
            elif style == "dots":
                out.append(circle(x + 0.5, y + 0.5, sz / 2))
            elif style == "diamond":
                out.append(diamond(x + 0.5, y + 0.5, sz * 0.62))
            elif style == "liquid":
                r = sz / 2
                tl = r if not g(x - 1, y) and not g(x, y - 1) else 0
                tr = r if not g(x + 1, y) and not g(x, y - 1) else 0
                br = r if not g(x + 1, y) and not g(x, y + 1) else 0
                bl = r if not g(x - 1, y) and not g(x, y + 1) else 0
                w = 1.0 if sz >= 0.999 else sz
                out.append(rrect(x + inset, y + inset, w, w, tl, tr, br, bl))
            elif style == "leaf":
                r = sz * 0.5
                tl = r if not g(x - 1, y) and not g(x, y - 1) else 0
                br = r if not g(x + 1, y) and not g(x, y + 1) else 0
                out.append(rrect(x + inset, y + inset, sz, sz, tl, 0, br, 0))
    return "".join(out)


def _eye(ox, oy, outer, inner):
    R = {"square": (0, 0, 0, 0), "rounded": (1.9,) * 4, "circle": (3.5,) * 4, "leaf": (3.5, 0.0, 3.5, 0.0)}[outer]
    r = {"square": (0, 0, 0, 0), "rounded": (1.0,) * 4, "circle": (2.5,) * 4, "leaf": (2.5, 0.0, 2.5, 0.0)}[outer]
    ring = rrect(ox, oy, 7, 7, *R) + rrect(ox + 1, oy + 1, 5, 5, *r)
    cx, cy = ox + 3.5, oy + 3.5
    if inner == "square":
        core = rrect(ox + 2, oy + 2, 3, 3)
    elif inner == "rounded":
        core = rrect(ox + 2, oy + 2, 3, 3, 0.9, 0.9, 0.9, 0.9)
    elif inner == "circle":
        core = circle(cx, cy, 1.5)
    else:
        core = diamond(cx, cy, 2.1)
    return ring, core


def logo_box(qr, st, logo):
    """(x, y, w, h) of the logo and (px, py, pw, ph) of its plate, in modules, inside the quiet-zone-less matrix"""
    if not logo:
        return None
    size = qr.size
    lw = size * st["logo_size"]
    lh = lw * logo["h"] / logo["w"]
    if lh > lw:
        lh, lw = lw, lw * logo["w"] / logo["h"]
    x, y = (size - lw) / 2, (size - lh) / 2
    pad = lw * st["plate_pad"] if st["plate"] != "none" else 0
    return (x, y, lw, lh), (x - pad, y - pad, lw + 2 * pad, lh + 2 * pad)


def coverage(qr, st, logo):
    b = logo_box(qr, st, logo)
    if not b:
        return 0.0
    _l, (px, py, pw, ph) = b
    return (pw * ph) / (qr.size * qr.size)


def build_svg(qr, style, logo=None, label=None, px_per_module=10):
    """logo: {"data": png/jpg bytes, "mime": "image/png", "w": int, "h": int}
    label: {"text": str, "d": path data (height ~1 unit, left at 0), "w": width} for a frame caption"""
    st = dict(DEFAULT)
    st.update(style)
    size, q = qr.size, int(st["quiet"])
    box = logo_box(qr, st, logo)
    if box:
        _l, (px, py, pw, ph) = box

        def skip(x, y):
            return x + 1.0 > px - 0.1 and x < px + pw + 0.1 and y + 1.0 > py - 0.1 and y < py + ph + 0.1
    else:
        skip = lambda x, y: False
    dark = _data_modules(qr, skip)
    dots_d = _dots_path(dark, size, st["dots"], max(0.4, min(1.0, float(st["dot_size"]))))
    eye_outer_d, eye_inner_d = [], []
    for ox, oy in ((0, 0), (size - 7, 0), (0, size - 7)):
        a, b = _eye(ox, oy, st["eye_outer"], st["eye_inner"])
        eye_outer_d.append(a)
        eye_inner_d.append(b)

    N = size + 2 * q
    frame = st["frame"]
    pad = N * 0.05 if frame != "none" else 0
    band = max(5.5, N * 0.17) if (frame != "none" and label and label.get("text")) else 0
    W = N + 2 * pad
    H = N + 2 * pad + band
    defs, fg = "", st["fg"]
    if st["gradient"] != "none":
        import math
        if st["gradient"] == "linear":
            a = math.radians(float(st["angle"]))
            dx, dy = math.cos(a) * size / 2, math.sin(a) * size / 2
            defs = (f'<linearGradient id="g" gradientUnits="userSpaceOnUse" x1="{n(size / 2 - dx)}" y1="{n(size / 2 - dy)}" '
                    f'x2="{n(size / 2 + dx)}" y2="{n(size / 2 + dy)}"><stop offset="0" stop-color="{st["fg"]}"/>'
                    f'<stop offset="1" stop-color="{st["fg2"]}"/></linearGradient>')
        else:
            defs = (f'<radialGradient id="g" gradientUnits="userSpaceOnUse" cx="{n(size / 2)}" cy="{n(size / 2)}" r="{n(size * 0.72)}">'
                    f'<stop offset="0" stop-color="{st["fg"]}"/><stop offset="1" stop-color="{st["fg2"]}"/></radialGradient>')
        fg = "url(#g)"
    ec = fg if st["eye_same"] else st["eye_outer_color"]
    ei = fg if st["eye_same"] else st["eye_inner_color"]

    s = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 {n(W)} {n(H)}" '
         f'width="{n(W * px_per_module)}" height="{n(H * px_per_module)}">']
    if defs:
        s.append("<defs>" + defs + "</defs>")
    rad = float(st["bg_round"]) * min(W, H)
    if frame == "box":
        s.append(f'<rect x="0" y="0" width="{n(W)}" height="{n(H)}" rx="{n(max(rad, N * 0.04))}" fill="{st["bg"] if st["bg_on"] else "none"}"/>')
        s.append(f'<rect x="{n(pad * 0.5)}" y="{n(pad * 0.5)}" width="{n(W - pad)}" height="{n(H - pad)}" rx="{n(N * 0.04)}" '
                 f'fill="none" stroke="{st["frame_color"]}" stroke-width="{n(max(0.5, pad * 0.35))}"/>')
    elif frame == "banner":
        s.append(f'<rect x="0" y="0" width="{n(W)}" height="{n(H)}" rx="{n(max(rad, N * 0.04))}" fill="{st["frame_color"]}"/>')
        s.append(f'<rect x="{n(pad)}" y="{n(pad)}" width="{n(N)}" height="{n(N)}" rx="{n(N * 0.025)}" fill="{st["bg"]}"/>')
    elif st["bg_on"]:
        s.append(f'<rect x="0" y="0" width="{n(W)}" height="{n(H)}" rx="{n(rad)}" fill="{st["bg"]}"/>')
    s.append(f'<g transform="translate({n(pad + q)} {n(pad + q)})">')
    if dots_d:
        s.append(f'<path d="{dots_d}" fill="{fg}"/>')
    s.append(f'<path d="{"".join(eye_outer_d)}" fill="{ec}" fill-rule="evenodd"/>')
    s.append(f'<path d="{"".join(eye_inner_d)}" fill="{ei}"/>')
    if box:
        (lx, ly, lw, lh), (px, py, pw, ph) = box
        pc = st["plate_color"]
        if st["plate"] == "square":
            s.append(f'<rect x="{n(px)}" y="{n(py)}" width="{n(pw)}" height="{n(ph)}" fill="{pc}"/>')
        elif st["plate"] == "rounded":
            s.append(f'<rect x="{n(px)}" y="{n(py)}" width="{n(pw)}" height="{n(ph)}" rx="{n(min(pw, ph) * 0.22)}" fill="{pc}"/>')
        elif st["plate"] == "circle":
            r = max(pw, ph) / 2
            s.append(f'<circle cx="{n(size / 2)}" cy="{n(size / 2)}" r="{n(r)}" fill="{pc}"/>')
        b64 = base64.b64encode(logo["data"]).decode()
        s.append(f'<image x="{n(lx)}" y="{n(ly)}" width="{n(lw)}" height="{n(lh)}" preserveAspectRatio="xMidYMid meet" '
                 f'href="data:{logo.get("mime", "image/png")};base64,{b64}" xlink:href="data:{logo.get("mime", "image/png")};base64,{b64}"/>')
    s.append("</g>")
    if band and label:
        th = band * 0.46
        tw = label["w"] * th
        scale = th
        if tw > W * 0.8:
            scale = th * (W * 0.8) / tw
            tw = W * 0.8
        tx = (W - tw) / 2
        ty = N + 2 * pad + band / 2 - scale / 2 + (0 if frame == "banner" else 0)
        col = st["label_color"] if frame == "banner" else st["frame_color"]
        s.append(f'<path transform="translate({n(tx)} {n(ty)}) scale({n(scale)})" d="{label["d"]}" fill="{col}"/>')
    s.append("</svg>")
    return "".join(s)
