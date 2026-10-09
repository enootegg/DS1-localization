"""Де в коді гри використовується рядок: друкує RVA кожного посилання й функцію, що його містить.

    python xrefs_strings.py "*.bin" "source:"
"""
import re
import sys

from dsx import *

im = Img()
for text in sys.argv[1:]:
    for match in re.finditer(re.escape(text.encode() + b'\0'), im.m):
        rva = im.rva(match.start())
        if rva is None:
            continue
        refs = [(hex(x), hex(im.func_of(x)[0]) if im.func_of(x) else None) for x in im.xrefs(rva)]
        print(f'"{text}" @ {rva:#x}: {refs}')
