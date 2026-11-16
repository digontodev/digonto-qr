"""QR code encoder (ISO/IEC 18004), written for Digonto - standard library only.
encode(text, level="M", boost=True, mask=None) -> QR object with .size and .dark(x, y)."""

ECC_PER_BLOCK = (
    (None, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28),
    (None, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30),
    (None, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30))
BLOCKS = (
    (None, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25),
    (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49),
    (None, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68),
    (None, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 74, 77, 81))
LEVELS = {"L": 0, "M": 1, "Q": 2, "H": 3}
FORMAT_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}
ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"


class TooLong(ValueError):
    pass


def _raw_modules(ver):
    r = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        r -= (25 * n - 10) * n - 55
        if ver >= 7:
            r -= 36
    return r


def _data_codewords(ver, lvl):
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK[LEVELS[lvl]][ver] * BLOCKS[LEVELS[lvl]][ver]


def _gf_mul(x, y):
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    res = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = _gf_mul(res[j], root)
            if j + 1 < degree:
                res[j] ^= res[j + 1]
        root = _gf_mul(root, 2)
    return res


def _rs_remainder(data, divisor):
    res = [0] * len(divisor)
    for b in data:
        f = b ^ res.pop(0)
        res.append(0)
        for i, c in enumerate(divisor):
            res[i] ^= _gf_mul(c, f)
    return res


def _segment(text):
    """returns (mode, bit_string_of_payload, char_count)"""
    if text.isdigit() and text.isascii():
        bits = ""
        for i in range(0, len(text), 3):
            g = text[i:i + 3]
            bits += format(int(g), "0%db" % (len(g) * 3 + 1))
        return 1, bits, len(text)
    if all(c in ALNUM for c in text):
        bits = ""
        for i in range(0, len(text) - 1, 2):
            bits += format(ALNUM.index(text[i]) * 45 + ALNUM.index(text[i + 1]), "011b")
        if len(text) % 2:
            bits += format(ALNUM.index(text[-1]), "06b")
        return 2, bits, len(text)
    raw = text.encode("utf-8")
    return 4, "".join(format(b, "08b") for b in raw), len(raw)


def _count_bits(mode, ver):
    k = 0 if ver <= 9 else 1 if ver <= 26 else 2
    return {1: (10, 12, 14), 2: (9, 11, 13), 4: (8, 16, 16)}[mode][k]


class QR:
    def __init__(self, ver, lvl, data, mask):
        self.version, self.level = ver, lvl
        self.size = ver * 4 + 17
        s = self.size
        self.m = [[False] * s for _ in range(s)]
        self.f = [[False] * s for _ in range(s)]
        self._patterns()
        self._place(self._interleave(data))
        if mask is None:
            best, mask = None, 0
            for k in range(8):
                self._mask(k)
                self._format(k)
                p = self._penalty()
                if best is None or p < best:
                    best, mask = p, k
                self._mask(k)
            self.mask = mask
        else:
            self.mask = mask
        self._mask(self.mask)
        self._format(self.mask)

    def dark(self, x, y):
        return self.m[y][x]

    # ---- layout
    def _set(self, x, y, v):
        self.m[y][x] = v
        self.f[y][x] = True

    def _patterns(self):
        s = self.size
        for i in range(s):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (s - 4, 3), (3, s - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < s and 0 <= y < s:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = self._align_positions()
        n = len(pos)
        for i in range(n):
            for j in range(n):
                if (i == 0 and j == 0) or (i == 0 and j == n - 1) or (i == n - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(pos[i] + dx, pos[j] + dy, max(abs(dx), abs(dy)) != 1)
        self._format(0)
        if self.version >= 7:
            rem = self.version
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.version << 12 | rem
            for i in range(18):
                a, b = s - 11 + i % 3, i // 3
                v = (bits >> i) & 1 == 1
                self._set(a, b, v)
                self._set(b, a, v)

    def _align_positions(self):
        v = self.version
        if v == 1:
            return []
        n = v // 7 + 2
        step = 26 if v == 32 else (v * 4 + n * 2 + 1) // (n * 2 - 2) * 2
        res = [self.size - 7 - i * step for i in range(n - 1)] + [6]
        return res[::-1]

    def _format(self, mask):
        s = self.size
        data = FORMAT_BITS[self.level] << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1
        for i in range(6):
            self._set(8, i, bit(i))
        self._set(8, 7, bit(6))
        self._set(8, 8, bit(7))
        self._set(7, 8, bit(8))
        for i in range(9, 15):
            self._set(14 - i, 8, bit(i))
        for i in range(8):
            self._set(s - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self._set(8, s - 15 + i, bit(i))
        self._set(8, s - 8, True)

    def _interleave(self, data):
        lv = LEVELS[self.level]
        nb, el = BLOCKS[lv][self.version], ECC_PER_BLOCK[lv][self.version]
        raw = _raw_modules(self.version) // 8
        short_n = nb - raw % nb
        short_len = raw // nb
        div = _rs_divisor(el)
        blocks, k = [], 0
        for i in range(nb):
            dat = data[k:k + short_len - el + (0 if i < short_n else 1)]
            k += len(dat)
            ecc = _rs_remainder(dat, div)
            if i < short_n:
                dat = dat + [0]
            blocks.append(dat + ecc)
        out = []
        for i in range(len(blocks[0])):
            for j, b in enumerate(blocks):
                if i != short_len - el or j >= short_n:
                    out.append(b[i])
        return out

    def _place(self, data):
        s = self.size
        i = 0
        right = s - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(s):
                for j in range(2):
                    x = right - j
                    up = ((right + 1) & 2) == 0
                    y = s - 1 - vert if up else vert
                    if not self.f[y][x] and i < len(data) * 8:
                        self.m[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def _mask(self, k):
        f = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0, lambda x, y: (x + y) % 3 == 0,
             lambda x, y: (x // 3 + y // 2) % 2 == 0, lambda x, y: x * y % 2 + x * y % 3 == 0,
             lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0, lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[k]
        for y in range(self.size):
            row, fr = self.m[y], self.f[y]
            for x in range(self.size):
                if not fr[x] and f(x, y):
                    row[x] = not row[x]

    def _penalty(self):
        s, m = self.size, self.m
        score = 0
        for grid in (m, [list(c) for c in zip(*m)]):
            for row in grid:
                run, prev = 1, row[0]
                for x in range(1, s):
                    if row[x] == prev:
                        run += 1
                    else:
                        if run >= 5:
                            score += run - 2
                        run, prev = 1, row[x]
                if run >= 5:
                    score += run - 2
                bits = "".join("1" if c else "0" for c in row)
                score += 40 * (bits.count("10111010000") + bits.count("00001011101"))
        for y in range(s - 1):
            for x in range(s - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(c for r in m for c in r)
        total = s * s
        score += 10 * max(0, (abs(dark * 20 - total * 10) + total - 1) // total - 1)
        return score


def encode(text, level="M", boost=True, mask=None, min_version=1):
    mode, bits, count = _segment(text)
    for ver in range(min_version, 41):
        cap = _data_codewords(ver, level) * 8
        used = 4 + _count_bits(mode, ver) + len(bits)
        if used <= cap:
            break
    else:
        raise TooLong("This is too much text for a QR code.")
    if boost:
        for lvl in ("M", "Q", "H"):
            if LEVELS[lvl] > LEVELS[level] and used <= _data_codewords(ver, lvl) * 8:
                level = lvl
    cap = _data_codewords(ver, level) * 8
    stream = format(mode, "04b") + format(count, "0%db" % _count_bits(mode, ver)) + bits
    stream += "0" * min(4, cap - len(stream))
    stream += "0" * (-len(stream) % 8)
    data = [int(stream[i:i + 8], 2) for i in range(0, len(stream), 8)]
    pad = 0xEC
    while len(data) < cap // 8:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    return QR(ver, level, data, mask)
