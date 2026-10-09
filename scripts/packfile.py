"""Read-only Decima (DS/DSDC) packfile reader."""
import struct, hashlib, ctypes, os, glob, mmh3

HEADER_KEY = (0xF41CAB62FA3A9443, 0xD2A89E3EF376811C)
DATA_KEY = (0x7E159D956C084A37, 0x18AA7D3F3D5AF7E8)
PATCH = "59b95a781c9170b0d13773766e27ad90.bin"

def mm(b): return mmh3.hash64(b, seed=42, x64arch=True, signed=False)
def path_hash(p): return mm(p.encode() + b'\0')[0]

def swizzle(buf, off, k1, k2):
    for i, k in ((0, k1), (16, k2)):
        key = bytearray(struct.pack('<QQ', *HEADER_KEY)); struct.pack_into('<I', key, 0, k)
        h = mm(bytes(key))
        a, b = struct.unpack_from('<QQ', buf, off + i)
        struct.pack_into('<QQ', buf, off + i, a ^ h[0], b ^ h[1])

class Oodle:
    def __init__(self, dll):
        self.lib = ctypes.WinDLL(dll)
        f = self.lib.OodleLZ_Decompress
        f.restype = ctypes.c_int64
        f.argtypes = [ctypes.c_char_p, ctypes.c_int64, ctypes.c_char_p, ctypes.c_int64, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                      ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64, ctypes.c_int]
        self.f = f
    def decompress(self, src, n):
        dst = ctypes.create_string_buffer(n)
        r = self.f(bytes(src), len(src), dst, n, 1, 1, 0, None, 0, None, None, None, 0, 3)
        if r != n: raise IOError(f"oodle: {r} != {n}")
        return dst.raw

class Packfile:
    def __init__(self, path, oodle):
        self.path, self.oodle = path, oodle
        self.f = open(path, 'rb')
        h = bytearray(self.f.read(40))
        magic, key = struct.unpack_from('<II', h)
        self.enc = magic == 0x21304050
        assert magic in (0x20304050, 0x21304050), path
        if self.enc: swizzle(h, 8, key, key + 1)
        fsize, dsize, nfiles, nchunks, csize = struct.unpack_from('<QQQII', h, 8)
        t = bytearray(self.f.read((nfiles + nchunks) * 32))
        self.files = {}
        for i in range(nfiles):
            o = i * 32
            if self.enc:
                k1, k2 = struct.unpack_from('<I', t, o + 4)[0], struct.unpack_from('<I', t, o + 28)[0]
                swizzle(t, o, k1, k2); struct.pack_into('<I', t, o + 4, k1); struct.pack_into('<I', t, o + 28, k2)
            idx, k, hsh, off, size, sk = struct.unpack_from('<IIQQII', t, o)
            self.files[hsh] = (off, size)
        self.chunks = []
        for i in range(nchunks):
            o = (nfiles + i) * 32
            if self.enc:
                k1, k2 = struct.unpack_from('<I', t, o + 12)[0], struct.unpack_from('<I', t, o + 28)[0]
                swizzle(t, o, k1, k2); struct.pack_into('<I', t, o + 12, k1); struct.pack_into('<I', t, o + 28, k2)
            self.chunks.append(struct.unpack_from('<QIIQII', t, o))
        self.chunks.sort()
        self.starts = [c[0] for c in self.chunks]
    def read_chunk(self, c):
        doff, dsize, dkey, coff, csize, ckey = c
        self.f.seek(coff); src = bytearray(self.f.read(csize))
        if self.enc:
            h = mm(struct.pack('<QII', doff, dsize, dkey))
            k = hashlib.md5(struct.pack('<QQ', h[0] ^ DATA_KEY[0], h[1] ^ DATA_KEY[1])).digest()
            key = (k * (len(src) // 16 + 1))[:len(src)]
            src = bytearray((int.from_bytes(src, 'little') ^ int.from_bytes(key, 'little')).to_bytes(len(src), 'little'))
        return self.oodle.decompress(src, dsize)
    def read(self, hsh):
        import bisect
        off, size = self.files[hsh]
        i = bisect.bisect_right(self.starts, off) - 1
        out = bytearray()
        while len(out) < size:
            c = self.chunks[i]; d = self.read_chunk(c)
            s = off - c[0] if not out else 0
            out += d[s:s + size - len(out)]; i += 1
        return bytes(out)

class Game:
    def __init__(self, root, extra=()):
        self.oodle = Oodle(os.path.join(root, 'oo2core_7_win64.dll'))
        names = sorted(glob.glob(os.path.join(root, 'data', '*.bin')), key=lambda p: (os.path.basename(p) == PATCH, p))
        self.packs = [Packfile(p, self.oodle) for p in names] + [Packfile(p, self.oodle) for p in extra]
    def find(self, path):
        h = path_hash(path)
        for p in reversed(self.packs):
            if h in p.files: return p, h
        return None, h
    def read(self, path):
        p, h = self.find(path)
        return p.read(h) if p else None

def core_objects(data):
    """[(type_hash, uuid_hex, size)]"""
    out, o = [], 0
    while o + 12 <= len(data):
        t, n = struct.unpack_from('<QI', data, o)
        out.append((t, data[o + 12:o + 28].hex(), n)); o += 12 + n
    return out
