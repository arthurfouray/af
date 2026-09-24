#!/usr/bin/env python3
"""Move the Custom HTML (c3-super field `html`) into one Freight file and leave a small stub inline.

usage: externalize.py IN.html OUTDIR [--freight-id X…] [--move-jsonld]

Writes to OUTDIR:
  afs-custom-html.<sha16>.js   the Freight file. It carries IN.html verbatim and, when the stub runs it,
                               inserts every node the stub no longer holds at its original place in
                               <customhtml>, in the original order. Inline scripts are recreated so they run
                               synchronously, exactly as they did inline.
  Custom-HTML.stub.html        the new Custom HTML: what must stay in the HTML (JSON-LD, the <noscript>
                               blocks, the preconnect), one <script src> for the file above (SRI pinned),
                               then the tail unchanged (section-menu CSS/JS and the ao-height guard, all
                               already on Freight, and the editor heading style).
  externalize.json             sizes, hashes, the node map and every assertion that was checked.

Why a .js file and not a .html file: only a parser-blocking <script src> runs before the rest of the page
is parsed, as the inline scripts do now (mode root, CSS controller, runtime loader, html-mode parser stop).
Fetching an .html file would be asynchronous: the page would render before the mode is set.

Why the bundle sits before the tail: a parser-blocking script waits for every stylesheet link above it.
The inline scripts run before the section-menu stylesheet today; the bundle keeps that.

html mode: afs-html-v1-preparse stops the parser with document.write('<plaintext>') and re-fetches the page.
The re-fetched text now holds the stub, so the bundle patches the preparse's single
`.then((t) => {` to put IN.html back between <customhtml> and </customhtml> before the projection runs.
The projected document is then the same as today's.

--freight-id  the id `c3-super upload` returned for the .js file. Without it the stub carries the
              placeholder F0000000000000000000000000000000 and must be rebuilt after the upload (the file
              name, bytes and SRI do not change, only the id).
--move-jsonld Option B: move the JSON-LD block into the bundle too (smaller stub, JSON-LD then only exists
              after JavaScript runs). SEO decision for the owner; default keeps it inline (Option A).

Nothing here talks to Cargo.
"""
import argparse, base64, gzip, hashlib, json, os, re, sys

LIMIT = 98500
PLACEHOLDER_ID = "F0000000000000000000000000000000"
HOOK = ".then((t) => {\n!(function (t) {"
HOOKED = ".then((t) => {\nt=globalThis.__afsCustomHtmlV1?.restore?.(t)??t;\n!(function (t) {"
PREPARSE_ID = "afs-html-v1-preparse"
SEG = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1\s*>|<link\b[^>]*>|\s+", re.S | re.I)

RUNTIME = r"""(()=>{"use strict";
const S=%(S)s,M=%(M)s,K=%(K)s,P=%(P)s,Q=%(Q)s,R=%(R)s;
const d=document,me=d.currentScript,root=d.documentElement,host=me&&me.parentNode||d.querySelector("customhtml")||d.body;
const api=globalThis.__afsCustomHtmlV1={version:1,sha256:%(H)s,t0:performance.now(),
restore(t){const o=/<customhtml\b[^>]*>/i.exec(t);if(!o)return t;const a=o.index+o[0].length,b=t.indexOf("</customhtml>",a);
if(b<0||t.slice(a,b).indexOf('id="afs-custom-html-bundle"')<0)return t;api.restored=(api.restored|0)+1;return t.slice(0,a)+S+t.slice(b)}};
const kept=[];for(let n=me&&me.previousElementSibling;n;n=n.previousElementSibling)kept.unshift(n);
const anchored=api.anchored=kept.length===K.length&&K.every((k,i)=>kept[i].localName===k[0]&&(kept[i].id||"")===k[1]);
const tpl=d.createElement("template");
const run=()=>{for(const[a,b,k]of M){const at=anchored&&k<kept.length?kept[k]:me,put=n=>at?at.before(n):host.append(n),html=S.slice(a,b);
if(!html.trim()){put(d.createTextNode(html));continue}
tpl.innerHTML=html;for(const n of[...tpl.content.childNodes]){if(n.localName!=="script"){put(d.importNode(n,!0));continue}
const x=d.createElement("script");for(const t of n.attributes)x.setAttribute(t.name,t.value);
let s=n.text;if(n.id===P){const i=s.indexOf(Q);if(i<0||s.indexOf(Q,i+1)>=0)api.patch="HOOK_COUNT";else{s=s.slice(0,i)+R+s.slice(i+Q.length);api.patch="ok"}}
x.text=s;put(x);if(root.dataset.afsHtmlV1Preparse==="loading"){api.stoppedAfter=n.id;return}}}};
run();api.t1=performance.now()})();
"""


def segments(s):
    out, pos = [], 0
    while pos < len(s):
        m = SEG.match(s, pos)
        if not m:
            sys.exit(f"cannot segment Custom HTML at byte {pos}: {s[pos:pos + 80]!r}")
        out.append((pos, m.end()))
        pos = m.end()
    if "".join(s[a:b] for a, b in out) != s:
        sys.exit("segmentation does not reconstruct the input")
    return out


def attrs(tag):
    return dict((k.lower(), v if v is not None else "") for k, v in
                re.findall(r'\s([\w:-]+)(?:\s*=\s*"([^"]*)")?', tag[:tag.index(">")]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("outdir")
    ap.add_argument("--freight-id", default=PLACEHOLDER_ID)
    ap.add_argument("--move-jsonld", action="store_true")
    a = ap.parse_args()
    if not re.fullmatch(r"[A-Z]\d+", a.freight_id):
        sys.exit("--freight-id must look like a Freight id (letter + digits)")
    raw = open(a.src, "rb").read()
    s = raw.decode("utf-8")
    if "customhtml" in s.lower():
        sys.exit("input mentions customhtml; restore() could not find its boundary safely")
    segs = segments(s)
    info = []
    for x, y in segs:
        t = s[x:y]
        if not t.strip():
            info.append({"a": x, "b": y, "kind": "ws", "id": ""}); continue
        name = re.match(r"<(\w+)", t).group(1).lower()
        at = attrs(t)
        info.append({"a": x, "b": y, "kind": name, "id": at.get("id", ""), "type": at.get("type", ""),
                     "src": "src" in at, "rel": at.get("rel", "")})
    # the tail: from the first external script or stylesheet link to the end, kept verbatim
    tail = next(i for i, e in enumerate(info) if (e["kind"] == "script" and e["src"]) or
                (e["kind"] == "link" and "stylesheet" in e["rel"].split()))
    for e in info[tail:]:
        if e["kind"] == "script" and not e["src"] and e["type"] not in ("application/ld+json", "application/json"):
            sys.exit(f"inline script {e['id']!r} after the tail start; it would run before its turn")

    def keep(e):
        if e["kind"] == "noscript" or e["kind"] == "link":
            return True
        return e["kind"] == "script" and e["type"] == "application/ld+json" and not a.move_jsonld

    k_el, kept_flag, last = [], [], None
    for i, e in enumerate(info[:tail]):
        if e["kind"] == "ws":
            kept_flag.append(last is not None and kept_flag[last]); continue
        kept_flag.append(keep(e)); last = i
        if kept_flag[-1]:
            k_el.append(i)
    moved = [i for i in range(tail) if not kept_flag[i]]
    for i in moved:
        e = info[i]
        if e["kind"] == "script" and e["src"]:
            sys.exit(f"external script {e['id']!r} would be moved; dynamic insertion changes its timing")
    # each moved node is inserted before the next kept element that precedes the bundle, or before the bundle.
    # Offsets are UTF-16 code units, which is how JavaScript indexes S.
    u16 = lambda i: len(s[:i].encode("utf-16-le")) // 2
    M = []
    for i in moved:
        nxt = next((j for j, ki in enumerate(k_el) if ki > i), len(k_el))
        M.append([u16(info[i]["a"]), u16(info[i]["b"]), nxt])
    K = [[info[i]["kind"], info[i]["id"]] for i in k_el]
    if s[info[tail]["a"]:].count(HOOK):
        sys.exit("preparse hook found in the tail")
    pp = [i for i in moved if info[i]["id"] == PREPARSE_ID]
    if len(pp) != 1 or s[info[pp[0]]["a"]:info[pp[0]]["b"]].count(HOOK) != 1 or s.count(HOOK) != 1:
        sys.exit("expected exactly one preparse script with exactly one `.then((t) => {` hook")

    js = RUNTIME % {"S": json.dumps(s), "M": json.dumps(M, separators=(",", ":")),
                    "K": json.dumps(K, separators=(",", ":")), "P": json.dumps(PREPARSE_ID),
                    "Q": json.dumps(HOOK), "R": json.dumps(HOOKED), "H": json.dumps(hashlib.sha256(raw).hexdigest())}
    jsb = js.encode("ascii")
    sha16 = hashlib.sha256(jsb).hexdigest()[:16]
    name = f"afs-custom-html.{sha16}.js"
    sri = "sha384-" + base64.b64encode(hashlib.sha384(jsb).digest()).decode()
    url = f"https://freight.cargo.site/m/{a.freight_id}/{name}"
    tag = f'<script id="afs-custom-html-bundle" src="{url}" integrity="{sri}" crossorigin="anonymous"></script>'
    stub = "".join(s[info[i]["a"]:info[i]["b"]] for i in range(tail) if kept_flag[i]) + tag + s[info[tail]["a"]:]
    stubb = stub.encode("utf-8")

    # offline reconstruction: interleave exactly as the runtime does (kept whitespace included) and compare
    doc = [i for i in range(tail) if kept_flag[i]] + ["bundle"]
    u16s = s.encode("utf-16-le")
    for (x, y, nxt), i in zip(M, moved):
        assert u16s[2 * x:2 * y].decode("utf-16-le") == s[info[i]["a"]:info[i]["b"]]
        doc.insert(doc.index(k_el[nxt] if nxt < len(k_el) else "bundle"), i)
    rebuilt = "".join(s[info[i]["a"]:info[i]["b"]] for i in doc if i != "bundle") + s[info[tail]["a"]:]
    if rebuilt != s:
        sys.exit("offline reconstruction differs from the input")
    if len(stubb) > LIMIT:
        sys.exit(f"stub is {len(stubb)} B > {LIMIT}")

    os.makedirs(a.outdir, exist_ok=True)
    open(os.path.join(a.outdir, name), "wb").write(jsb)
    open(os.path.join(a.outdir, "Custom-HTML.stub.html"), "wb").write(stubb)
    moved_ids = [info[i]["id"] or info[i]["kind"] for i in moved if info[i]["kind"] != "ws"]
    rep = {
        "input": {"path": os.path.basename(a.src), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
        "bundle": {"name": name, "bytes": len(jsb), "sha256": hashlib.sha256(jsb).hexdigest(), "sri": sri,
                   "freightId": a.freight_id, "placeholderId": a.freight_id == PLACEHOLDER_ID},
        "gzip9": {"input": len(gzip.compress(raw, 9)), "bundle": len(gzip.compress(jsb, 9)), "stub": len(gzip.compress(stubb, 9))},
        "stub": {"bytes": len(stubb), "sha256": hashlib.sha256(stubb).hexdigest(), "limit": LIMIT,
                 "headroom": LIMIT - len(stubb), "option": "B (JSON-LD moved)" if a.move_jsonld else "A (JSON-LD inline)"},
        "keptBeforeBundle": K, "movedNodes": moved_ids, "movedSegments": len(M),
        "tailFrom": info[tail]["a"], "checks": ["segmentation reconstructs input", "no external script moved",
                                                "no inline script after tail start", "exactly one preparse hook",
                                                "offline interleave == input", f"stub <= {LIMIT} B"],
    }
    json.dump(rep, open(os.path.join(a.outdir, "externalize.json"), "w"), indent=1)
    print(f"stub {len(stubb):,} B (was {len(raw):,} B, headroom {LIMIT - len(stubb):,} B); "
          f"{name} {len(jsb):,} B; {len(moved_ids)} nodes moved; kept before bundle: {K}")


if __name__ == "__main__":
    main()
