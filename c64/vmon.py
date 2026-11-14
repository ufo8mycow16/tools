"""Tiny client for VICE's binary monitor (x64sc -binarymonitor, port 6502).

Lets a script drive a running emulator: read/write memory, grab the screen, press joystick
directions / fire, feed keys, wait N frames, save snapshots.
"""
import socket, struct, time, itertools
from PIL import Image

PALETTE = [(0, 0, 0), (255, 255, 255), (129, 51, 56), (117, 206, 200), (142, 60, 151), (86, 172, 77),
           (46, 44, 155), (237, 241, 113), (142, 80, 41), (85, 56, 0), (196, 108, 113), (74, 74, 74),
           (123, 123, 123), (169, 255, 159), (112, 109, 235), (178, 178, 178)]


class Mon:
    def __init__(self, host='127.0.0.1', port=6502, timeout=60):
        for _ in range(100):
            try:
                self.s = socket.create_connection((host, port), timeout=timeout)
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError('no monitor')
        self.ids = itertools.count(1)
        self.buf = b''

    def _recv(self, n):
        while len(self.buf) < n:
            d = self.s.recv(65536)
            if not d:
                raise EOFError
            self.buf += d
        r, self.buf = self.buf[:n], self.buf[n:]
        return r

    def _resp(self):
        h = self._recv(12)
        stx, api, ln, rtype, err, rid = struct.unpack('<BBIBBI', h)
        body = self._recv(ln)
        return rtype, err, rid, body

    def cmd(self, ctype, body=b''):
        rid = next(self.ids)
        self.s.sendall(struct.pack('<BBIIB', 2, 2, len(body), rid, ctype) + body)
        while True:
            rtype, err, r, b = self._resp()
            if r == rid:
                if err:
                    raise RuntimeError('monitor error %02x for cmd %02x' % (err, ctype))
                return b
            # unsolicited events (stopped/resumed/register) are ignored

    def mem(self, start, end, bank=0):
        b = self.cmd(0x01, struct.pack('<BHHBH', 0, start, end, 0, bank))
        n = struct.unpack('<H', b[:2])[0]
        return b[2:2 + n]

    def setmem(self, start, data, bank=0):
        self.cmd(0x02, struct.pack('<BHHBH', 0, start, start + len(data) - 1, 0, bank) + bytes(data))

    def regs(self):
        b = self.cmd(0x31, b'\x00')
        n = struct.unpack('<H', b[:2])[0]; out = {}; p = 2
        for _ in range(n):
            sz, rid = b[p], b[p + 1]; val = struct.unpack('<H', b[p + 2:p + 4])[0]
            out[rid] = val; p += sz + 1
        return out

    def resume(self):
        self.cmd(0xAA)

    def joy(self, value, port=1):
        """value bits pressed: 1 up, 2 down, 4 left, 8 right, 16 fire. port 1 = control port 2.
        Needs JoyPort<n>Device = 37 (IO simulation); the lines are active-low, so invert."""
        self.cmd(0xA2, struct.pack('<HH', port, 0x1f & ~value))

    def keys(self, text):
        t = text.encode('latin1')
        self.cmd(0x72, bytes([len(t)]) + t)

    def screen(self, path=None):
        b = self.cmd(0x84, b'\x00\x00')  # VIC-II, indexed 8bpp
        flen = struct.unpack('<I', b[:4])[0]
        dw, dh, ox, oy, iw, ih, bpp = struct.unpack('<HHHHHHB', b[4:17])
        p0 = 4 + flen
        ln = struct.unpack('<I', b[p0:p0 + 4])[0]
        px = b[p0 + 4:p0 + 4 + ln]
        px = px + bytes(dw * dh - len(px))
        im = Image.frombytes('P', (dw, dh), px)
        pal = []
        for c in PALETTE:
            pal += list(c)
        im.putpalette(pal + [0] * (768 - len(pal)))
        im = im.crop((ox - 32, oy - 35, ox - 32 + 384, oy - 35 + 272)).convert('RGB')
        if path:
            im.save(path)
        return im

    def snapshot(self, path):
        p = path.encode()
        self.cmd(0x41, b'\x01\x01' + bytes([len(p)]) + p)

    def load_snapshot(self, path):
        p = path.encode()
        self.cmd(0x42, bytes([len(p)]) + p)

    def run_for(self, seconds):
        """let the emulator run (in warp) for a wall-clock time, then stop it again"""
        self.resume()
        time.sleep(seconds)
        self.cmd(0x81)  # ping stops nothing; use a no-op that halts: request registers
        self.regs()


def _set_res_int(self, name, value):
    n = name.encode()
    self.cmd(0x52, bytes([1, len(n)]) + n + bytes([4]) + struct.pack('<I', value))
Mon.set_res_int = _set_res_int
