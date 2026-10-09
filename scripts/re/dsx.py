"""Shared helpers: load ds.exe, find xrefs to an RVA via RIP-relative disp32, disassemble functions."""
import lief, mmap, os, struct, bisect, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

EXE = os.environ.get("DS_EXE") or sys.exit("Вкажіть шлях до exe гри у змінній середовища DS_EXE")
BASE = 0x140000000

class Img:
    def __init__(self, path=EXE):
        self.f = open(path, 'rb')
        self.m = mmap.mmap(self.f.fileno(), 0, access=mmap.ACCESS_READ)
        pe = lief.PE.parse(path)
        self.secs = [(s.name, s.virtual_address, s.virtual_size, s.pointerto_raw_data, s.sizeof_raw_data) for s in pe.sections]
        self.text = next(s for s in self.secs if s[0] == '.text')
        pd = next(s for s in self.secs if s[0] == '.pdata')
        raw = self.m[pd[3]:pd[3] + pd[2]]
        self.funcs = []
        for i in range(0, len(raw) - 11, 12):
            b, e, u = struct.unpack_from('<III', raw, i)
            if b: self.funcs.append((b, e))
        self.funcs.sort()
        self.starts = [f[0] for f in self.funcs]
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
    def off(self, rva):
        for n, va, vs, ro, rs in self.secs:
            if va <= rva < va + max(vs, rs):
                o = rva - va
                return ro + o if o < rs else None
        return None
    def rva(self, off):
        for n, va, vs, ro, rs in self.secs:
            if ro <= off < ro + rs: return va + off - ro
        return None
    def read(self, rva, n):
        o = self.off(rva)
        return self.m[o:o + n] if o is not None else b'\0' * n
    def cstr(self, rva, maxlen=200):
        b = self.read(rva, maxlen); i = b.find(b'\0')
        return b[:i if i >= 0 else maxlen].decode('latin1')
    def func_of(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        if i >= 0 and self.funcs[i][0] <= rva < self.funcs[i][1]: return self.funcs[i]
        return None
    def xrefs(self, target_rva):
        """all positions in .text where a rel32 resolves to target_rva (lea/mov/call/jmp)"""
        n, va, vs, ro, rs = self.text
        m = self.m; out = []
        import numpy as np
        buf = np.frombuffer(m, dtype=np.uint8, count=rs, offset=ro)
        # candidate positions i such that int32 at i + (va+i+4) == target
        for shift in range(4):
            a = np.frombuffer(m, dtype='<i4', count=(rs - shift) // 4, offset=ro + shift)
            idx = np.arange(a.size, dtype=np.int64) * 4 + shift
            hit = np.nonzero(a.astype(np.int64) + va + idx + 4 == target_rva)[0]
            out += [int(va + h * 4 + shift) for h in hit]
        return sorted(out)
    def dis(self, rva, size):
        return list(self.md.disasm(self.read(rva, size), BASE + rva))
    def print_func(self, rva, maxins=400, annotate=True):
        f = self.func_of(rva)
        if not f: print("no func for", hex(rva)); return
        print(f"--- func {f[0]:#x}..{f[1]:#x}")
        for k, ins in enumerate(self.dis(f[0], f[1] - f[0])):
            if k >= maxins: print("..."); break
            note = ''
            if annotate and 'rip' in ins.op_str:
                try:
                    import re
                    mm = re.search(r'rip ([+-]) (0x[0-9a-f]+)', ins.op_str)
                    if mm:
                        t = ins.address + ins.size + (int(mm.group(2), 16) * (1 if mm.group(1) == '+' else -1)) - BASE
                        s = self.cstr(t, 60)
                        note = f"   ; -> {t:#x}" + (f' "{s}"' if len(s) >= 3 and all(31 < ord(c) < 127 for c in s) else '')
                except Exception: pass
            print(f"{ins.address - BASE:#010x}: {ins.mnemonic} {ins.op_str}{note}")

