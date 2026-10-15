#!/usr/bin/env python3
"""Print one node's subtree from the saved Figma page metadata.

usage: python -I tools/figtree.py <node-id> [max-depth]
Reads reference/figma/page-metadata.xml (the get_metadata dump of page 0:1).
Positions are relative to each node's parent, as Figma reports them.
"""
import argparse
import sys
from pathlib import Path

XML_PATH = Path(__file__).resolve().parent.parent / "reference" / "figma" / "page-metadata.xml"


def print_subtree(nid, maxdepth=99, xml_path=XML_PATH, out=sys.stdout):
    """Stream xml_path and print the subtree for node `nid` up to `maxdepth`.
    Returns True if the node was found, False otherwise."""
    if ":" not in nid and "-" in nid:
        nid = nid.replace("-", ":", 1)
    needle = f' id="{nid}"'

    with Path(xml_path).open(encoding="utf-8") as f:
        for line in f:
            if needle in line:
                line_s = line.rstrip("\r\n")
                stripped = line_s.lstrip()
                base = len(line_s) - len(stripped)
                print(line_s, file=out)
                if stripped.endswith("/>") or "</" in stripped:
                    return True
                for sub in f:
                    sub_s = sub.rstrip("\r\n")
                    sub_stripped = sub_s.lstrip()
                    if not sub_stripped:
                        continue
                    ind = len(sub_s) - len(sub_stripped)
                    if ind <= base:
                        if ind == base and sub_stripped.startswith("</"):
                            print(sub_s, file=out)
                        break
                    if (ind - base) // 2 <= maxdepth:
                        print(sub_s, file=out)
                return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("node_id", help="Figma node id (e.g. 491:1779 or 491-1779)")
    ap.add_argument("max_depth", nargs="?", type=int, default=99,
                    help="maximum child depth to print (default: 99)")
    args = ap.parse_args()

    if not XML_PATH.is_file():
        sys.exit(f"error: missing {XML_PATH}")
    if not print_subtree(args.node_id, args.max_depth):
        sys.exit(f"error: node {args.node_id!r} not found in {XML_PATH.name}")


if __name__ == "__main__":
    main()
