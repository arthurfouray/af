#!/usr/bin/env python3
"""Build the idempotent-writes runtime from the published v6.0.8 runtime.

Same-value setAttribute / dataset / className writes still queue MutationObserver
records (DOM spec). The runtime's per-scroll-frame layer pass rewrote ~187 unchanged
attributes per frame, waking the mode controller, heavy-page loader and bg-sync
observers every frame. Each replacement below writes only when the value differs.
toggleAttribute and classList.toggle are already no-ops when unchanged, and
same-value CSSOM style writes queue nothing, so those are left alone.

usage: make-idempotent.py IN OUT
"""
import sys, hashlib
src = open(sys.argv[1], encoding="utf-8").read()
R = [
    # helper, hoisted in the same scope as ensureBackdrop
    ('function ensureBackdrop(){let plane=document.getElementById("nav-backdrop");',
     'function afsAttr(node,name,value){node.getAttribute(name)!==value&&node.setAttribute(name,value)}function ensureBackdrop(){let plane=document.getElementById("nav-backdrop");', 1),
    ('plane.dataset.followerPlane="true",plane.dataset.controlLayers="blur surface content frame hit focus",plane.setAttribute("aria-hidden","true"),plane.inert=!0,plane}',
     'afsAttr(plane,"data-follower-plane","true"),afsAttr(plane,"data-control-layers","blur surface content frame hit focus"),afsAttr(plane,"aria-hidden","true"),plane.inert||(plane.inert=!0),plane}', 1),
    ('html.dataset.navTone=tone;const targets=',
     'afsAttr(html,"data-nav-tone",tone);const targets=', 1),
    ('layer.className=`nav-layer nav-${kind} nav-${kind}-${type}${"surface"===kind?` nav-invert nav-invert-${type}`:""}${active?" is-active":""}${hovered?" is-hover":""}${pressed?" is-pressed":""}`,layer.dataset.layerFor=type,layer.dataset.tone=tone;',
     'afsAttr(layer,"class",`nav-layer nav-${kind} nav-${kind}-${type}${"surface"===kind?` nav-invert nav-invert-${type}`:""}${active?" is-active":""}${hovered?" is-hover":""}${pressed?" is-pressed":""}`),afsAttr(layer,"data-layer-for",type),afsAttr(layer,"data-tone",tone);', 1),
    ('target.dataset.tone=tone;jobs.push([target,layers])',
     'afsAttr(target,"data-tone",tone);jobs.push([target,layers])', 1),
    ('for(const node of[menuPage,tools])node&&(node.toggleAttribute("inert",hidden),node.setAttribute("aria-hidden",String(hidden)));queueLayers()}',
     'for(const node of[menuPage,tools])node&&(node.toggleAttribute("inert",hidden),afsAttr(node,"aria-hidden",String(hidden)));queueLayers()}', 1),
]
for old, new, n in R:
    c = src.count(old)
    if c != n:
        sys.exit(f"expected {n} match(es), found {c}: {old[:80]}")
    src = src.replace(old, new)
open(sys.argv[2], "w", encoding="utf-8").write(src)
b = src.encode("utf-8")
print(f"{sys.argv[2]}: {len(b)} B sha256 {hashlib.sha256(b).hexdigest()}")
