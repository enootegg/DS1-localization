"""Дизасемблює діапазони RVA з підписами рядків, на які посилається код.

    python rng.py 1924850-1924c3c
"""
import sys, re
from dsx import *
im = Img()
def rng(a, b):
    print(f"=== {a:#x}..{b:#x}")
    for ins in im.dis(a, b - a):
        note = ''
        mm = re.search(r'rip ([+-]) (0x[0-9a-f]+)', ins.op_str)
        if mm:
            t = ins.address + ins.size + (int(mm.group(2), 16) * (1 if mm.group(1) == '+' else -1)) - BASE
            s = im.cstr(t, 60)
            note = f"   ; -> {t:#x}" + (f' "{s}"' if len(s) >= 3 and all(31 < ord(c) < 127 for c in s) else '')
        print(f"{ins.address - BASE:#010x}: {ins.mnemonic} {ins.op_str}{note}")
for a in sys.argv[1:]:
    x, y = a.split('-')
    rng(int(x, 16), int(y, 16))

