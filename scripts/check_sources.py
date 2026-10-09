"""Звіряє кожен файл у теці замін з оригіналом в архівах гри: чи є він у грі, чи той самий
склад об'єктів (тип + UUID) у .core і чи той самий розмір у .stream.

    python check_sources.py <корінь гри> <тека з файлами>
"""
import sys, os
from packfile import *
root = sys.argv[1]; src = sys.argv[2]
g = Game(root)
print("archives:", len(g.packs), "files:", sum(len(p.files) for p in g.packs))
missing, differ, same, streams = [], [], 0, []
for dp, _, fs in os.walk(src):
    for f in fs:
        rel = os.path.relpath(os.path.join(dp, f), src).replace('\\', '/')
        new = open(os.path.join(dp, f), 'rb').read()
        old = g.read(rel)
        if old is None: missing.append(rel); continue
        if rel.endswith('.stream'):
            if len(old) != len(new): streams.append((rel, len(old), len(new)))
            continue
        a = [(t, u) for t, u, n in core_objects(old)]; b = [(t, u) for t, u, n in core_objects(new)]
        if a == b: same += 1
        else: differ.append((rel, a, b))
print("same structure:", same)
print("MISSING in game:", len(missing))
for m in missing: print("   ", m)
print("stream size differs:", len(streams))
for s in streams: print("   ", s)
print("OBJECT LIST DIFFERS:", len(differ))
for rel, a, b in differ:
    sa, sb = set(a), set(b)
    print(f"    {rel}: game {len(a)} objs, ours {len(b)}; only in game {len(sa - sb)}, only in ours {len(sb - sa)}")
    for t, u in list(sa - sb)[:3]: print(f"        game-only type={t:016x} uuid={u}")

