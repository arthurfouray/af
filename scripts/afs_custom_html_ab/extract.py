#!/usr/bin/env python3
"""Write the <customhtml> body of a served page (the published Custom HTML) to a file.
usage: extract.py HOME.html OUT.html"""
import hashlib, json, re, sys
h = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"<customhtml\b[^>]*>(.*?)</customhtml>", h, re.S)
if not m:
    sys.exit("no <customhtml> in the served page")
c = m.group(1)
state = json.dumps(c, ensure_ascii=False)[1:-1].replace("<", "\\u003c")
print(f"published Custom HTML: {len(c.encode()):,} B, sha256 {hashlib.sha256(c.encode()).hexdigest()}; "
      f"in <customhtml> {h.count(c)}x, in the preloaded state {h.count(state)}x")
open(sys.argv[2], "w", encoding="utf-8").write(c)
