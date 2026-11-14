"""Small 6502 CPU (documented opcodes + the common undocumented ones) for running C64 unpackers.

mem: bytearray(65536), plain RAM (no ROM/IO banking - unpackers usually switch $01 to all-RAM).
"""
class CPU:
    def __init__(self, mem):
        self.m = mem
        self.a = self.x = self.y = 0
        self.sp = 0xFF
        self.pc = 0
        self.c = self.z = self.i = self.d = self.v = self.n = 0
        self.cycles = 0
        self.on_write = None

    # --- memory helpers
    def rd(self, a):
        return self.m[a & 0xFFFF]

    def wr(self, a, v):
        a &= 0xFFFF
        self.m[a] = v & 0xFF
        if self.on_write:
            self.on_write(a, v & 0xFF)

    def rw(self, a):
        return self.m[a & 0xFFFF] | self.m[(a + 1) & 0xFFFF] << 8

    def rwzp(self, a):
        return self.m[a & 0xFF] | self.m[(a + 1) & 0xFF] << 8

    def push(self, v):
        self.m[0x100 | self.sp] = v & 0xFF
        self.sp = (self.sp - 1) & 0xFF

    def pull(self):
        self.sp = (self.sp + 1) & 0xFF
        return self.m[0x100 | self.sp]

    def p(self):
        return (self.n << 7 | self.v << 6 | 0x20 | 0x10 | self.d << 3 | self.i << 2 | self.z << 1 | self.c)

    def setp(self, v):
        self.n = v >> 7 & 1; self.v = v >> 6 & 1; self.d = v >> 3 & 1
        self.i = v >> 2 & 1; self.z = v >> 1 & 1; self.c = v & 1

    def nz(self, v):
        v &= 0xFF
        self.n = v >> 7; self.z = int(v == 0)
        return v

    # --- addressing: return effective address
    def fetch(self):
        v = self.m[self.pc]; self.pc = (self.pc + 1) & 0xFFFF; return v

    def fetchw(self):
        v = self.rw(self.pc); self.pc = (self.pc + 2) & 0xFFFF; return v

    def addr(self, mode):
        if mode == 'imm':
            a = self.pc; self.pc = (self.pc + 1) & 0xFFFF; return a
        if mode == 'zp': return self.fetch()
        if mode == 'zpx': return (self.fetch() + self.x) & 0xFF
        if mode == 'zpy': return (self.fetch() + self.y) & 0xFF
        if mode == 'abs': return self.fetchw()
        if mode == 'abx': return (self.fetchw() + self.x) & 0xFFFF
        if mode == 'aby': return (self.fetchw() + self.y) & 0xFFFF
        if mode == 'izx': return self.rwzp(self.fetch() + self.x)
        if mode == 'izy': return (self.rwzp(self.fetch()) + self.y) & 0xFFFF
        raise ValueError(mode)

    # --- ALU
    def adc(self, v):
        if self.d:
            lo = (self.a & 0xF) + (v & 0xF) + self.c
            hi = (self.a >> 4) + (v >> 4)
            if lo > 9: lo += 6; hi += 1
            if hi > 9: hi += 6
            r = ((hi << 4) | (lo & 0xF)) & 0xFF
            self.c = int(hi > 15); self.a = self.nz(r); return
        r = self.a + v + self.c
        self.v = int(((self.a ^ r) & (v ^ r) & 0x80) != 0)
        self.c = int(r > 0xFF)
        self.a = self.nz(r)

    def sbc(self, v):
        if self.d:
            r = self.a - v - (1 - self.c)
            lo = (self.a & 0xF) - (v & 0xF) - (1 - self.c)
            hi = (self.a >> 4) - (v >> 4)
            if lo < 0: lo -= 6; hi -= 1
            if hi < 0: hi -= 6
            self.c = int(r >= 0); self.a = self.nz(((hi << 4) | (lo & 0xF)) & 0xFF); return
        self.adc(v ^ 0xFF)

    def cmp(self, r, v):
        t = r - v
        self.c = int(t >= 0); self.nz(t & 0xFF)

    def branch(self, cond):
        o = self.fetch()
        if cond:
            if o > 127: o -= 256
            self.pc = (self.pc + o) & 0xFFFF

    def step(self):
        op = self.fetch()
        self.cycles += 1
        f = OPS.get(op)
        if f is None:
            raise RuntimeError('unknown opcode $%02X at $%04X' % (op, (self.pc - 1) & 0xFFFF))
        f(self)


OPS = {}
MODES = {'imm': 'imm', 'zp': 'zp', 'zpx': 'zpx', 'zpy': 'zpy', 'abs': 'abs', 'abx': 'abx', 'aby': 'aby', 'izx': 'izx', 'izy': 'izy'}

def _reg(op, fn):
    OPS[op] = fn

def _load(reg, table):
    for op, mode in table.items():
        def f(c, mode=mode, reg=reg):
            setattr(c, reg, c.nz(c.rd(c.addr(mode))))
        _reg(op, f)

def _store(reg, table):
    for op, mode in table.items():
        def f(c, mode=mode, reg=reg):
            c.wr(c.addr(mode), getattr(c, reg))
        _reg(op, f)

_load('a', {0xA9: 'imm', 0xA5: 'zp', 0xB5: 'zpx', 0xAD: 'abs', 0xBD: 'abx', 0xB9: 'aby', 0xA1: 'izx', 0xB1: 'izy'})
_load('x', {0xA2: 'imm', 0xA6: 'zp', 0xB6: 'zpy', 0xAE: 'abs', 0xBE: 'aby'})
_load('y', {0xA0: 'imm', 0xA4: 'zp', 0xB4: 'zpx', 0xAC: 'abs', 0xBC: 'abx'})
_store('a', {0x85: 'zp', 0x95: 'zpx', 0x8D: 'abs', 0x9D: 'abx', 0x99: 'aby', 0x81: 'izx', 0x91: 'izy'})
_store('x', {0x86: 'zp', 0x96: 'zpy', 0x8E: 'abs'})
_store('y', {0x84: 'zp', 0x94: 'zpx', 0x8C: 'abs'})

def _alu(name, base):
    modes = {base + 0x09 - 0x01 + 0x00: 'imm'}
    tbl = {base | 0x09: 'imm', base | 0x05: 'zp', base | 0x15: 'zpx', base | 0x0D: 'abs',
           base | 0x1D: 'abx', base | 0x19: 'aby', base | 0x01: 'izx', base | 0x11: 'izy'}
    for op, mode in tbl.items():
        def f(c, mode=mode):
            v = c.rd(c.addr(mode))
            if name == 'ora': c.a = c.nz(c.a | v)
            elif name == 'and': c.a = c.nz(c.a & v)
            elif name == 'eor': c.a = c.nz(c.a ^ v)
            elif name == 'adc': c.adc(v)
            elif name == 'sbc': c.sbc(v)
            elif name == 'cmp': c.cmp(c.a, v)
        _reg(op, f)

for nm, b in (('ora', 0x00), ('and', 0x20), ('eor', 0x40), ('adc', 0x60), ('cmp', 0xC0), ('sbc', 0xE0)):
    _alu(nm, b)
_reg(0xEB, lambda c: c.sbc(c.rd(c.addr('imm'))))

for op, mode, reg in ((0xE0, 'imm', 'x'), (0xE4, 'zp', 'x'), (0xEC, 'abs', 'x'),
                      (0xC0, 'imm', 'y'), (0xC4, 'zp', 'y'), (0xCC, 'abs', 'y')):
    _reg(op, lambda c, mode=mode, reg=reg: c.cmp(getattr(c, reg), c.rd(c.addr(mode))))

def _rmw(name, tbl):
    for op, mode in tbl.items():
        def f(c, mode=mode):
            if mode == 'acc':
                v = c.a
            else:
                ad = c.addr(mode); v = c.rd(ad)
            if name == 'asl': c.c = v >> 7; v = (v << 1) & 0xFF
            elif name == 'lsr': c.c = v & 1; v >>= 1
            elif name == 'rol': nc = v >> 7; v = ((v << 1) | c.c) & 0xFF; c.c = nc
            elif name == 'ror': nc = v & 1; v = (v >> 1) | (c.c << 7); c.c = nc
            elif name == 'inc': v = (v + 1) & 0xFF
            elif name == 'dec': v = (v - 1) & 0xFF
            c.nz(v)
            if mode == 'acc': c.a = v
            else: c.wr(ad, v)
        _reg(op, f)

_rmw('asl', {0x0A: 'acc', 0x06: 'zp', 0x16: 'zpx', 0x0E: 'abs', 0x1E: 'abx'})
_rmw('lsr', {0x4A: 'acc', 0x46: 'zp', 0x56: 'zpx', 0x4E: 'abs', 0x5E: 'abx'})
_rmw('rol', {0x2A: 'acc', 0x26: 'zp', 0x36: 'zpx', 0x2E: 'abs', 0x3E: 'abx'})
_rmw('ror', {0x6A: 'acc', 0x66: 'zp', 0x76: 'zpx', 0x6E: 'abs', 0x7E: 'abx'})
_rmw('inc', {0xE6: 'zp', 0xF6: 'zpx', 0xEE: 'abs', 0xFE: 'abx'})
_rmw('dec', {0xC6: 'zp', 0xD6: 'zpx', 0xCE: 'abs', 0xDE: 'abx'})

def _bit(c, mode):
    v = c.rd(c.addr(mode)); c.z = int((c.a & v) == 0); c.n = v >> 7; c.v = v >> 6 & 1
_reg(0x24, lambda c: _bit(c, 'zp')); _reg(0x2C, lambda c: _bit(c, 'abs'))

for op, flag, val in ((0x10, 'n', 0), (0x30, 'n', 1), (0x50, 'v', 0), (0x70, 'v', 1),
                      (0x90, 'c', 0), (0xB0, 'c', 1), (0xD0, 'z', 0), (0xF0, 'z', 1)):
    _reg(op, lambda c, flag=flag, val=val: c.branch(getattr(c, flag) == val))

def _jsr(c):
    t = c.fetchw(); r = (c.pc - 1) & 0xFFFF; c.push(r >> 8); c.push(r); c.pc = t
def _rts(c):
    lo = c.pull(); hi = c.pull(); c.pc = ((hi << 8 | lo) + 1) & 0xFFFF
def _rti(c):
    c.setp(c.pull()); lo = c.pull(); hi = c.pull(); c.pc = hi << 8 | lo
def _brk(c):
    c.pc = (c.pc + 1) & 0xFFFF; c.push(c.pc >> 8); c.push(c.pc); c.push(c.p()); c.i = 1; c.pc = c.rw(0xFFFE)
_reg(0x20, _jsr); _reg(0x60, _rts); _reg(0x40, _rti); _reg(0x00, _brk)
_reg(0x4C, lambda c: setattr(c, 'pc', c.fetchw()))
def _jmpi(c):
    a = c.fetchw(); c.pc = c.m[a] | c.m[(a & 0xFF00) | ((a + 1) & 0xFF)] << 8
_reg(0x6C, _jmpi)

for op, attr, val in ((0x18, 'c', 0), (0x38, 'c', 1), (0x58, 'i', 0), (0x78, 'i', 1),
                      (0xB8, 'v', 0), (0xD8, 'd', 0), (0xF8, 'd', 1)):
    _reg(op, lambda c, attr=attr, val=val: setattr(c, attr, val))

_reg(0xAA, lambda c: setattr(c, 'x', c.nz(c.a)))
_reg(0x8A, lambda c: setattr(c, 'a', c.nz(c.x)))
_reg(0xA8, lambda c: setattr(c, 'y', c.nz(c.a)))
_reg(0x98, lambda c: setattr(c, 'a', c.nz(c.y)))
_reg(0xBA, lambda c: setattr(c, 'x', c.nz(c.sp)))
_reg(0x9A, lambda c: setattr(c, 'sp', c.x))
_reg(0xE8, lambda c: setattr(c, 'x', c.nz(c.x + 1)))
_reg(0xCA, lambda c: setattr(c, 'x', c.nz(c.x - 1)))
_reg(0xC8, lambda c: setattr(c, 'y', c.nz(c.y + 1)))
_reg(0x88, lambda c: setattr(c, 'y', c.nz(c.y - 1)))
_reg(0x48, lambda c: c.push(c.a))
_reg(0x68, lambda c: setattr(c, 'a', c.nz(c.pull())))
_reg(0x08, lambda c: c.push(c.p()))
_reg(0x28, lambda c: c.setp(c.pull()))
for op in (0xEA, 0x1A, 0x3A, 0x5A, 0x7A, 0xDA, 0xFA):
    _reg(op, lambda c: None)
for op, mode in ((0x80, 'imm'), (0x82, 'imm'), (0x89, 'imm'), (0x04, 'zp'), (0x44, 'zp'), (0x64, 'zp'),
                 (0x14, 'zpx'), (0x34, 'zpx'), (0x54, 'zpx'), (0x74, 'zpx'), (0xD4, 'zpx'), (0xF4, 'zpx'),
                 (0x0C, 'abs'), (0x1C, 'abx'), (0x3C, 'abx'), (0x5C, 'abx'), (0x7C, 'abx'), (0xDC, 'abx'), (0xFC, 'abx')):
    _reg(op, lambda c, mode=mode: c.addr(mode))

# common undocumented: LAX, SAX, DCP, ISC, SLO, RLA, SRE, RRA
for op, mode in {0xA7: 'zp', 0xB7: 'zpy', 0xAF: 'abs', 0xBF: 'aby', 0xA3: 'izx', 0xB3: 'izy'}.items():
    def f(c, mode=mode):
        v = c.nz(c.rd(c.addr(mode))); c.a = v; c.x = v
    _reg(op, f)
for op, mode in {0x87: 'zp', 0x97: 'zpy', 0x8F: 'abs', 0x83: 'izx'}.items():
    _reg(op, lambda c, mode=mode: c.wr(c.addr(mode), c.a & c.x))

def _combo(base, fn):
    for off, mode in ((0x07, 'zp'), (0x17, 'zpx'), (0x0F, 'abs'), (0x1F, 'abx'), (0x1B, 'aby'), (0x03, 'izx'), (0x13, 'izy')):
        def f(c, mode=mode):
            ad = c.addr(mode); fn(c, ad)
        _reg(base | off, f)

def _dcp(c, ad):
    v = (c.rd(ad) - 1) & 0xFF; c.wr(ad, v); c.cmp(c.a, v)
def _isc(c, ad):
    v = (c.rd(ad) + 1) & 0xFF; c.wr(ad, v); c.sbc(v)
def _slo(c, ad):
    v = c.rd(ad); c.c = v >> 7; v = (v << 1) & 0xFF; c.wr(ad, v); c.a = c.nz(c.a | v)
def _rla(c, ad):
    v = c.rd(ad); nc = v >> 7; v = ((v << 1) | c.c) & 0xFF; c.c = nc; c.wr(ad, v); c.a = c.nz(c.a & v)
def _sre(c, ad):
    v = c.rd(ad); c.c = v & 1; v >>= 1; c.wr(ad, v); c.a = c.nz(c.a ^ v)
def _rra(c, ad):
    v = c.rd(ad); nc = v & 1; v = (v >> 1) | (c.c << 7); c.c = nc; c.wr(ad, v); c.adc(v)
_combo(0xC0, _dcp); _combo(0xE0, _isc); _combo(0x00, _slo); _combo(0x20, _rla); _combo(0x40, _sre); _combo(0x60, _rra)
