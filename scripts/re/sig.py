"""Скільки разів сигнатура трапляється в коді гри (має бути рівно 1).

    python sig.py "4C 8B DC 55 ? ? 41 56"
"""
import sys, re
from dsx import *
im = Img()
n, va, vs, ro, rs = im.text
text = im.m[ro:ro+rs]
def show(rva, k=48): print(hex(rva), ' '.join(f"{b:02X}" for b in im.read(rva, k)))
def count(sig):
    parts = sig.split()
    rx = b''.join(b'.' if p == '?' else re.escape(bytes([int(p, 16)])) for p in parts)
    return [hex(va + m.start()) for m in re.finditer(rx, text, re.S)]
for a in sys.argv[1:]: print(a, '=>', count(a))

