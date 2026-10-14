"""Print one node's subtree from the saved Figma page metadata.

usage: python -I tools/figtree.py <node-id> [max-depth]
Reads reference/figma/page-metadata.xml (the get_metadata dump of page 0:1).
Positions are relative to each node's parent, as Figma reports them.
"""
import sys
from pathlib import Path

lines = (Path(__file__).resolve().parent.parent / "reference/figma/page-metadata.xml").read_text(encoding="utf-8").splitlines()
nid = sys.argv[1]
maxdepth = int(sys.argv[2]) if len(sys.argv) > 2 else 99
for i, l in enumerate(lines):
    if f'id="{nid}"' in l:
        base = len(l) - len(l.lstrip())
        print(l)
        for m in lines[i + 1:]:
            ind = len(m) - len(m.lstrip())
            if ind <= base:
                break
            if (ind - base) // 2 <= maxdepth:
                print(m)
        break
