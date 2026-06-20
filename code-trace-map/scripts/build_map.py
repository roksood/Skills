#!/usr/bin/env python3
"""
build_map.py — render a use-case execution-trace spec into a single,
self-contained interactive HTML page.

Usage:
    python3 build_map.py <trace_spec.json> -o <output.html>

The spec is plain JSON. Only stdlib is used, so this runs anywhere Python 3
runs, with no pip install. See references/spec-schema.md for the full schema.

The script does almost no "thinking": the analysis (reading the codebase,
finding entry points, tracing call paths) happens before this, and is captured
in the spec. This script just renders that spec consistently. All interactivity
is vanilla JS embedded in the output, so the page works offline as one file.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def _scan_owners(spec):
    """Scan all steps, grouping by owning symbol (the class or module-level
    function a step's `object` belongs to). Records the file(s) each owner is
    found in, the use cases it's in, and the individual members (methods) seen
    with their location — enough to draw a per-file mini-map when an object's
    traced code is spread across more than one file.
    """
    owners = {}
    for uc in spec.get("use_cases", []):
        for step in uc.get("steps", []):
            sym = (step.get("object") or "").strip()
            if not sym:
                continue
            name = sym.split("(")[0].strip()          # drop arg list
            owner = name.rsplit(".", 1)[0] if "." in name else name
            entry = owners.setdefault(owner, {"files": [], "appears_in": [], "members": []})
            loc = (step.get("location") or "").strip()
            f, line = "", ""
            if loc:
                f, _, line = loc.rpartition(":") if ":" in loc else (loc, "", "")
                if f and f not in entry["files"]:
                    entry["files"].append(f)
            if uc["id"] not in entry["appears_in"]:
                entry["appears_in"].append(uc["id"])
            # member display = the part of the symbol after the owner
            member = sym[len(owner) + 1:] if sym.startswith(owner + ".") else sym
            rec = {"member": member, "file": f, "line": line}
            if f and rec not in entry["members"]:
                entry["members"].append(rec)
    return owners


def _file_map(members):
    """Group a list of member records into [{file, members:[{member,line}]}]."""
    fm, order = {}, []
    for m in members:
        if m["file"] not in fm:
            fm[m["file"]] = []
            order.append(m["file"])
        fm[m["file"]].append({"member": m["member"], "line": m["line"]})
    return [{"file": f, "members": fm[f]} for f in order]


def derive_objects(spec):
    """Build the objects index.

    If the spec has a curated `objects` array, keep it but backfill each
    object's `defined_in` from the scanned step locations when it's missing.
    Otherwise build the index from the steps, including the defining file(s),
    ordered by reuse (most-shared first — those carry the most of the system).
    """
    owners = _scan_owners(spec)

    if spec.get("objects"):
        out = []
        for o in spec["objects"]:
            o = dict(o)
            scan = owners.get(o.get("name", ""), {})
            if not o.get("defined_in"):
                files = scan.get("files", [])
                if files:
                    o["defined_in"] = ", ".join(files)
            if not o.get("file_map"):
                fm = _file_map(scan.get("members", []))
                if fm:
                    o["file_map"] = fm
            out.append(o)
        return out

    objs = [
        {
            "name": owner,
            "role": "",
            "defined_in": ", ".join(info["files"]),
            "file_map": _file_map(info["members"]),
            "appears_in": info["appears_in"],
        }
        for owner, info in owners.items()
    ]
    return sorted(objs, key=lambda o: (-len(o["appears_in"]), o["name"]))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ — code trace map</title>
<style>
  :root {
    --bg: #f7f7f5; --panel: #ffffff; --line: #e6e4dd; --line-strong: #d4d1c7;
    --ink: #232320; --muted: #6b6a63; --faint: #97958c;
    --mono: ui-monospace, "SF Mono", "Cascadia Code", "JetBrains Mono", Menlo, Consolas, monospace;
    --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    --radius: 12px;
    --c-blue:#3b82f6; --c-purple:#8b5cf6; --c-teal:#14b8a6; --c-amber:#f59e0b;
    --c-coral:#f97316; --c-pink:#ec4899; --c-green:#22c55e; --c-red:#ef4444; --c-gray:#94a3b8;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#1a1a18; --panel:#232320; --line:#333330; --line-strong:#444440;
      --ink:#ecebe4; --muted:#a3a199; --faint:#76746c;
    }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font-family:var(--sans);
         font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased; }
  a { color:inherit; }
  code, .mono { font-family:var(--mono); font-size:0.86em; }

  header.top { padding:22px 28px; border-bottom:1px solid var(--line); background:var(--panel); }
  header.top h1 { margin:0 0 4px; font-size:20px; font-weight:600; letter-spacing:-0.01em; }
  .meta { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:6px 0 0; }
  .badge { font-size:12px; padding:2px 9px; border-radius:999px; border:1px solid var(--line-strong);
           color:var(--muted); }
  .summary { margin:10px 0 0; color:var(--muted); max-width:70ch; font-size:14px; }

  .shell { display:flex; align-items:flex-start; gap:0; min-height:60vh; }
  aside { width:280px; flex:0 0 280px; border-right:1px solid var(--line); padding:18px 16px;
          position:sticky; top:0; align-self:flex-start; }
  .search { width:100%; padding:8px 11px; border:1px solid var(--line-strong); border-radius:8px;
            background:var(--bg); color:var(--ink); font:inherit; font-size:13px; margin-bottom:14px; }
  .nav-label { font-size:11px; text-transform:uppercase; letter-spacing:0.07em; color:var(--faint);
               margin:14px 4px 7px; font-weight:600; }
  .uc-btn { display:block; width:100%; text-align:left; padding:9px 11px; border:1px solid transparent;
            border-radius:9px; background:none; color:var(--ink); font:inherit; font-size:13.5px;
            cursor:pointer; margin-bottom:3px; line-height:1.35; }
  .uc-btn:hover { background:var(--bg); }
  .uc-btn.active { background:var(--bg); border-color:var(--line-strong); font-weight:500; }
  .uc-btn .trig { display:block; font-family:var(--mono); font-size:11px; color:var(--faint); margin-top:2px; }
  .view-toggle { display:flex; gap:4px; margin-bottom:6px; }
  .view-toggle button { flex:1; padding:7px; border:1px solid var(--line-strong); background:var(--bg);
            color:var(--muted); border-radius:8px; font:inherit; font-size:12.5px; cursor:pointer; }
  .view-toggle button.active { background:var(--ink); color:var(--panel); border-color:var(--ink); }

  main { flex:1; padding:24px 30px 60px; min-width:0; }
  .uc-head h2 { margin:0 0 2px; font-size:18px; font-weight:600; letter-spacing:-0.01em; }
  .uc-head .trig { font-family:var(--mono); font-size:13px; color:var(--muted); }
  .uc-head .desc { margin:8px 0 0; color:var(--muted); font-size:14px; max-width:74ch; }

  .legend { display:flex; gap:7px; flex-wrap:wrap; margin:18px 0 22px; }
  .chip { font-size:12px; padding:3px 10px; border-radius:999px; line-height:1.3; }

  .step { display:grid; grid-template-columns:30px 1fr; gap:13px; align-items:start;
          background:var(--panel); border:1px solid var(--line); border-left-width:4px;
          border-radius:var(--radius); padding:13px 15px; }
  .step .num { width:26px; height:26px; border-radius:50%; background:var(--bg);
               display:flex; align-items:center; justify-content:center; font-size:13px;
               color:var(--muted); font-variant-numeric:tabular-nums; }
  .step .row1 { display:flex; justify-content:space-between; gap:14px; align-items:baseline; flex-wrap:wrap; }
  .step .task { font-size:15px; font-weight:500; }
  .step .loc { font-family:var(--mono); font-size:12px; color:var(--faint); white-space:nowrap; }
  .step .does { color:var(--muted); font-size:13.5px; margin:3px 0 7px; }
  .step .obj { font-family:var(--mono); font-size:13px; }
  .step .detail-toggle { margin-top:8px; font-size:12.5px; color:var(--muted); background:none;
            border:none; padding:0; cursor:pointer; display:inline-flex; align-items:center; gap:5px; }
  .step .detail-toggle:hover { color:var(--ink); }
  .step .detail { margin-top:9px; padding:11px 13px; background:var(--bg); border-radius:8px;
            font-size:13px; color:var(--muted); white-space:pre-wrap; display:none; }
  .step.open .detail { display:block; }
  .connector { display:flex; align-items:center; padding:5px 0 5px 14px; color:var(--line-strong); }
  .connector svg { width:14px; height:14px; }

  .obj-grid { display:grid; gap:10px; }
  .obj-card { background:var(--panel); border:1px solid var(--line); border-radius:var(--radius);
              padding:13px 15px; }
  .obj-card .name { font-family:var(--mono); font-size:14px; font-weight:500; }
  .obj-card .defloc { font-family:var(--mono); font-size:12px; color:var(--faint); margin-top:3px; }
  .obj-card .minimap { margin-top:8px; }
  .obj-card .mm-cap { font-size:10.5px; color:var(--faint); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:5px; }
  .obj-svg { display:block; overflow:visible; }
  .obj-svg .obj-box { fill:var(--bg); stroke:var(--line-strong); stroke-width:1; }
  .obj-svg .obj-box-title { fill:var(--muted); font-family:var(--mono); font-size:11.5px; }
  .obj-svg .obj-mem { fill:var(--ink); font-family:var(--mono); font-size:12px; }
  .obj-svg .obj-mem-ext { fill:var(--muted); }
  .obj-svg .obj-sep { stroke:var(--line); stroke-width:1; }
  .obj-svg .obj-arrow { fill:none; stroke:var(--faint); stroke-width:1.4; }
  .obj-svg .obj-arrow-head { fill:var(--faint); }
  .obj-svg .obj-line { fill:var(--faint); font-family:var(--mono); font-size:11px; }
  .obj-svg .obj-guide { stroke:var(--line); stroke-width:1; }
  .obj-card .role { color:var(--muted); font-size:13.5px; margin:6px 0 9px; }
  .obj-card .links { display:flex; gap:6px; flex-wrap:wrap; }
  .obj-card .links button { font-size:12px; padding:3px 9px; border-radius:999px; cursor:pointer;
              border:1px solid var(--line-strong); background:var(--bg); color:var(--muted); font:inherit; }
  .obj-card .links button:hover { color:var(--ink); border-color:var(--faint); }

  .empty { color:var(--faint); padding:40px 0; text-align:center; font-size:14px; }
  @media (max-width:720px) {
    .shell { display:block; }
    aside { width:auto; flex:none; position:static; border-right:none; border-bottom:1px solid var(--line); }
    main { padding:20px 18px 50px; }
  }
</style>
</head>
<body>
<header class="top">
  <h1 id="proj-name"></h1>
  <div class="meta" id="proj-meta"></div>
  <p class="summary" id="proj-summary"></p>
</header>
<div class="shell">
  <aside>
    <input class="search" id="search" placeholder="Filter use cases & steps…" autocomplete="off">
    <div class="view-toggle">
      <button id="vt-trace" class="active" onclick="setView('trace')">Use cases</button>
      <button id="vt-objects" onclick="setView('objects')">Objects</button>
    </div>
    <div class="nav-label" id="nav-label">Traced flows</div>
    <div id="uc-list"></div>
  </aside>
  <main id="main"></main>
</div>
<script>
const DATA = __DATA__;
const COLORS = {blue:'var(--c-blue)',purple:'var(--c-purple)',teal:'var(--c-teal)',
  amber:'var(--c-amber)',coral:'var(--c-coral)',pink:'var(--c-pink)',green:'var(--c-green)',
  red:'var(--c-red)',gray:'var(--c-gray)'};

let activeUC = (DATA.use_cases[0] || {}).id || null;
let view = 'trace';
let query = '';

function esc(s){ return String(s==null?'':s).replace(/[&<>"]/g,
  c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function layer(id){ return (DATA.layers||[]).find(l=>l.id===id) || null; }
function colorOf(id){ const l=layer(id); return COLORS[l && l.color] || COLORS.gray; }
function layerName(id){ const l=layer(id); return l ? l.label : (id||'—'); }
function ucById(id){ return DATA.use_cases.find(u=>u.id===id); }

function matchUC(uc){
  if(!query) return true;
  const hay = [uc.name, uc.trigger, uc.summary,
    ...(uc.steps||[]).flatMap(s=>[s.task,s.object,s.location,s.does,s.detail])]
    .join(' ').toLowerCase();
  return hay.includes(query);
}

function header(){
  const p = DATA.project || {};
  document.getElementById('proj-name').textContent = p.name || 'Code trace map';
  const meta = [];
  if(p.language) meta.push(p.language);
  if(p.framework) meta.push(p.framework);
  document.getElementById('proj-meta').innerHTML =
    meta.map(m=>`<span class="badge">${esc(m)}</span>`).join('');
  document.getElementById('proj-summary').textContent = p.summary || '';
}

function sidebar(){
  document.getElementById('nav-label').textContent =
    view==='trace' ? 'Traced flows' : 'Objects index';
  document.getElementById('vt-trace').classList.toggle('active', view==='trace');
  document.getElementById('vt-objects').classList.toggle('active', view==='objects');
  const list = document.getElementById('uc-list');
  if(view==='objects'){ list.innerHTML=''; return; }
  const shown = DATA.use_cases.filter(matchUC);
  list.innerHTML = shown.map(uc=>`
    <button class="uc-btn ${uc.id===activeUC?'active':''}" onclick="pick('${esc(uc.id)}')">
      ${esc(uc.name)}
      ${uc.trigger?`<span class="trig">${esc(uc.trigger)}</span>`:''}
    </button>`).join('') || `<div class="empty" style="padding:20px 4px">No matches.</div>`;
}

function traceView(){
  const uc = ucById(activeUC);
  if(!uc){ return `<div class="empty">Select a use case.</div>`; }
  const usedLayers = [...new Set((uc.steps||[]).map(s=>s.layer))].filter(Boolean);
  const legend = usedLayers.map(id=>{
    const c = colorOf(id);
    return `<span class="chip" style="background:color-mix(in srgb, ${c} 14%, transparent);color:${c}">${esc(layerName(id))}</span>`;
  }).join('');
  const steps = (uc.steps||[]).map((s,i)=>{
    const c = colorOf(s.layer);
    const detail = s.detail ? `
      <button class="detail-toggle" onclick="this.closest('.step').classList.toggle('open')">
        <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 3l3 3 3-3" stroke="currentColor" stroke-width="1.3" fill="none" stroke-linecap="round"/></svg>
        Detail</button>
      <div class="detail">${esc(s.detail)}</div>` : '';
    const conn = i < uc.steps.length-1 ? `
      <div class="connector"><svg viewBox="0 0 12 12"><path d="M6 1v9M3 7l3 3 3-3" stroke="currentColor" stroke-width="1.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>` : '';
    return `
      <div class="step" style="border-left-color:${c}">
        <div class="num">${s.n!=null?esc(s.n):i+1}</div>
        <div>
          <div class="row1">
            <span class="task">${esc(s.task)}</span>
            ${s.location?`<span class="loc">${esc(s.location)}</span>`:''}
          </div>
          ${s.does?`<div class="does">${esc(s.does)}</div>`:''}
          ${s.object?`<code class="obj">${esc(s.object)}</code>`:''}
          ${detail}
        </div>
      </div>${conn}`;
  }).join('');
  return `
    <div class="uc-head">
      <h2>${esc(uc.name)}</h2>
      ${uc.trigger?`<span class="trig">${esc(uc.trigger)}</span>`:''}
      ${uc.summary?`<p class="desc">${esc(uc.summary)}</p>`:''}
    </div>
    <div class="legend">${legend}</div>
    ${steps || '<div class="empty">No steps recorded for this flow.</div>'}`;
}

function slug(s){ return String(s).replace(/[^a-zA-Z0-9]/g,'-'); }
function truncEnd(s,n){ s=String(s); return s.length>n?'…'+s.slice(-(n-1)):s; }
function truncStart(s,n){ s=String(s); return s.length>n?s.slice(0,n-1)+'…':s; }

// Draw an object whose code spans >1 file as a boxes-and-arrows map: its
// primary file (the one with the most traced methods) drawn as a box of its
// methods, with an arrow from each borrowed method to the *exact* method in the
// file that supplies it. Methods are indented under their file, the way they
// nest under a class in source.
function objMiniSvg(o){
  const fm = o.file_map || [];
  let pIdx = 0, mx = -1;
  fm.forEach((f,i)=>{ if(f.members.length>mx){ mx=f.members.length; pIdx=i; } });
  const primary = fm[pIdx];
  const foreign = fm.filter((_,i)=>i!==pIdx);

  const Wmain=252, Wsat=200, gap=72, padX=10, padTop=12;
  const rowH=22, headH=28, boxPad=10, vGap=16;
  const methodX=padX+34, guideX=padX+24, lineX=padX+Wmain-10;

  // main-box rows: native methods (primary file) first, then borrowed ones,
  // each tagged with its satellite file index (t) and row within it (mi)
  const rows=[];
  primary.members.forEach(m=>rows.push({m, t:-1}));
  foreign.forEach((f,fi)=> f.members.forEach((m,mi)=>rows.push({m, t:fi, mi})));
  const mainH = headH + rows.length*rowH + boxPad;

  const satX = padX + Wmain + gap;
  let y = padTop; const sat=[];
  foreign.forEach(f=>{ const h=headH+f.members.length*rowH+boxPad; sat.push({f, x:satX, y, h}); y+=h+vGap; });
  const satBottom = sat.length ? sat[sat.length-1].y+sat[sat.length-1].h : 0;
  const totalH = Math.max(padTop+mainH, satBottom) + padTop;
  const totalW = (sat.length ? satX+Wsat : padX+Wmain) + padX;
  const mid = slug(o.name);
  const memY  = (by,j)=> by + headH + j*rowH + 15;       // text baseline
  const rowMid = (by,j)=> by + headH + j*rowH + rowH/2;   // arrow anchor

  const box = (x,by,w,h,file,nchar)=>
      `<rect class="obj-box" x="${x}" y="${by}" width="${w}" height="${h}" rx="9"/>`
    + `<text class="obj-box-title" x="${x+12}" y="${by+18}"><title>${esc(file)}</title>${esc(truncEnd(file,nchar))}</text>`
    + `<line class="obj-sep" x1="${x}" y1="${by+headH-4}" x2="${x+w}" y2="${by+headH-4}"/>`;
  const guide = (x,by,n)=> n>1
    ? `<line class="obj-guide" x1="${x}" y1="${by+headH+2}" x2="${x}" y2="${by+headH+(n-1)*rowH+rowH/2}"/>` : '';

  let s = `<svg class="obj-svg" role="img" aria-label="File map for ${esc(o.name)}: primary file ${esc(primary.file)} with ${foreign.length} linked file(s)" viewBox="0 0 ${totalW} ${totalH}" style="width:100%;height:auto;max-width:${totalW}px">`;
  s += `<defs><marker id="ar-${mid}" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto"><path d="M0 0L6 3L0 6Z" class="obj-arrow-head"/></marker></defs>`;

  // arrows: borrowed method (main) -> the exact method row in its file (satellite)
  rows.forEach((r,i)=>{
    if(r.t<0) return;
    const sb=sat[r.t];
    const y1=rowMid(padTop,i), y2=rowMid(sb.y,r.mi);
    const x1=padX+Wmain, x2=sb.x, mxp=(x1+x2)/2;
    s += `<path class="obj-arrow" d="M${x1} ${y1} C ${mxp} ${y1}, ${mxp} ${y2}, ${x2-3} ${y2}" marker-end="url(#ar-${mid})"/>`;
  });

  // main box
  s += box(padX, padTop, Wmain, mainH, primary.file, 32);
  s += guide(guideX, padTop, rows.length);
  rows.forEach((r,i)=>{
    const ext = r.t>=0;
    s += `<text class="obj-mem${ext?' obj-mem-ext':''}" x="${methodX}" y="${memY(padTop,i)}">${esc(truncStart(r.m.member,22))}</text>`;
    if(!ext && r.m.line) s += `<text class="obj-line" text-anchor="end" x="${lineX}" y="${memY(padTop,i)}">:${esc(r.m.line)}</text>`;
  });

  // satellite boxes: list their methods (indented), arrow lands on the row
  sat.forEach(sb=>{
    s += box(sb.x, sb.y, Wsat, sb.h, sb.f.file, 26);
    s += guide(sb.x+24, sb.y, sb.f.members.length);
    sb.f.members.forEach((m,j)=>{
      s += `<text class="obj-mem" x="${sb.x+34}" y="${memY(sb.y,j)}">${esc(truncStart(m.member,18))}</text>`;
      if(m.line) s += `<text class="obj-line" text-anchor="end" x="${sb.x+Wsat-10}" y="${memY(sb.y,j)}">:${esc(m.line)}</text>`;
    });
  });

  s += `</svg>`;
  return `<div class="minimap"><div class="mm-cap">code traced across ${fm.length} files</div>${s}</div>`;
}

function objectsView(){
  let objs = DATA._objects;
  const q = query;
  if(q) objs = objs.filter(o=>{
    const ucNames = (o.appears_in||[]).map(id=>(ucById(id)||{}).name||'').join(' ');
    const members = (o.file_map||[]).flatMap(f=>f.members.map(m=>m.member)).join(' ');
    return (o.name+' '+(o.role||'')+' '+(o.defined_in||'')+' '+members+' '+ucNames).toLowerCase().includes(q);
  });
  if(!objs.length) return `<div class="empty">No objects match.</div>`;
  const cards = objs.map(o=>{
    const links = (o.appears_in||[]).map(id=>{
      const uc = ucById(id); if(!uc) return '';
      return `<button onclick="setView('trace');pick('${esc(id)}')">${esc(uc.name)}</button>`;
    }).join('');
    const fm = o.file_map || [];
    let loc;
    if (fm.length > 1) {
      loc = objMiniSvg(o);
    } else {
      loc = o.defined_in ? `<div class="defloc">${esc(o.defined_in)}</div>` : '';
    }
    return `
      <div class="obj-card">
        <div class="name">${esc(o.name)}</div>
        ${loc}
        ${o.role?`<div class="role">${esc(o.role)}</div>`:''}
        <div class="links">${links}</div>
      </div>`;
  }).join('');
  return `<div class="uc-head"><h2>Objects index</h2>
    <p class="desc">Each object and the use cases it takes part in. The most reused objects sit at the top — those are usually where the system's real work concentrates.</p></div>
    <div class="obj-grid" style="margin-top:18px">${cards}</div>`;
}

function render(){
  header(); sidebar();
  document.getElementById('main').innerHTML =
    view==='trace' ? traceView() : objectsView();
}
function pick(id){ activeUC = id; render(); window.scrollTo({top:0,behavior:'smooth'}); }
function setView(v){ view = v; render(); }
document.getElementById('search').addEventListener('input', e=>{
  query = e.target.value.trim().toLowerCase();
  const shown = DATA.use_cases.filter(matchUC);
  if(view==='trace' && shown.length && !shown.some(u=>u.id===activeUC)) activeUC = shown[0].id;
  render();
});
render();
</script>
</body>
</html>
"""


def build_digest(spec):
    """Render a compact markdown digest of the same trace — built for an LLM or
    agent to ingest and grasp the codebase's shape and behavior quickly. Same
    information as the HTML page, linearized and token-light.
    """
    objs = derive_objects(spec)
    p = spec.get("project", {})
    out = [f"# {p.get('name', 'Code trace map')} — code trace map"]
    tags = " · ".join(t for t in [p.get("language"), p.get("framework")] if t)
    if tags:
        out.append(tags)
    if p.get("summary"):
        out.append("\n" + p["summary"])

    out.append("\n## How to read this")
    out.append("Each use case is one real flow traced through the code, in order. "
               "A step is: `task` — `Object.method()` — `file:line` `[layer]` — what it does. "
               "`file:line` is where the code *runs*, so inherited/borrowed methods point at "
               "the file that defines them, not the caller.")
    layers = spec.get("layers") or []
    if layers:
        out.append("\nLayers: " + ", ".join(f"`{l['id']}`={l.get('label', l['id'])}" for l in layers))

    out.append("\n## Use cases")
    for uc in spec.get("use_cases", []):
        head = f"\n### {uc.get('name', uc['id'])}"
        if uc.get("trigger"):
            head += f"  (`{uc['trigger']}`)"
        out.append(head)
        if uc.get("summary"):
            out.append(uc["summary"])
        for i, s in enumerate(uc.get("steps", []), 1):
            seg = [f"{s.get('n', i)}. {s.get('task', '')}"]
            if s.get("object"):
                seg.append(f"`{s['object']}`")
            if s.get("location"):
                seg.append(f"`{s['location']}`")
            line = " — ".join(seg)
            if s.get("layer"):
                line += f" [{s['layer']}]"
            if s.get("does"):
                line += f" — {s['does']}"
            out.append(line)

    out.append("\n## Objects")
    out.append("Each object, the file(s) its traced code lives in, and the use cases it serves.")
    for o in objs:
        fm = o.get("file_map", [])
        files = o.get("defined_in") or ", ".join(f["file"] for f in fm)
        line = f"- `{o['name']}`"
        if files:
            line += f" — {files}"
        if o.get("role"):
            line += f" — {o['role']}"
        if o.get("appears_in"):
            line += f" — used in: {', '.join(o['appears_in'])}"
        out.append(line)
        if len(fm) > 1:  # spans files: show which method lives where
            spread = " · ".join(
                (f"{m['member']} {f['file']}:{m['line']}" if m["line"] else f"{m['member']} {f['file']}")
                for f in fm for m in f["members"])
            out.append(f"  - spans files: {spread}")

    return "\n".join(out) + "\n"


def build(spec):
    spec = dict(spec)
    spec["_objects"] = derive_objects(spec)
    blob = json.dumps(spec, ensure_ascii=False)
    blob = blob.replace("</", "<\\/")  # keep a literal </script> in data from closing the tag
    title = (spec.get("project") or {}).get("name", "Code trace map")
    return TEMPLATE.replace("__DATA__", blob).replace("__TITLE__", title)


def main():
    ap = argparse.ArgumentParser(description="Render a use-case trace spec into an interactive HTML page (for people) and a markdown digest (for agents).")
    ap.add_argument("spec", help="Path to the trace spec JSON file")
    ap.add_argument("-o", "--output", default="code_trace_map.html", help="Output HTML path")
    ap.add_argument("--no-digest", action="store_true", help="Skip the markdown digest written alongside the HTML")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.exists():
        sys.exit(f"Spec not found: {spec_path}")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"Spec is not valid JSON: {e}")

    if not spec.get("use_cases"):
        sys.exit("Spec has no `use_cases` — nothing to render.")

    out = Path(args.output)
    out.write_text(build(spec), encoding="utf-8")
    n_uc = len(spec["use_cases"])
    n_steps = sum(len(u.get("steps", [])) for u in spec["use_cases"])
    n_obj = len(derive_objects(spec))
    print(f"Wrote {out}  ({n_uc} use case(s), {n_steps} step(s), {n_obj} object(s))")

    if not args.no_digest:
        digest = out.with_suffix(".md")
        digest.write_text(build_digest(spec), encoding="utf-8")
        print(f"Wrote {digest}  (markdown digest for agents)")


if __name__ == "__main__":
    main()
