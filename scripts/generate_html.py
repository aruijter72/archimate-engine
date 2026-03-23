#!/usr/bin/env python3
"""Generate interactive HTML viewer from model.archimate.

Usage:
    python scripts/generate_html.py [--model PATH] [--output PATH]
"""

import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

XSI = 'http://www.w3.org/2001/XMLSchema-instance'
ARCH = 'http://www.archimatetool.com/archimate'


def _layer(etype):
    t = etype.split(':')[-1].lower() if ':' in etype else etype.lower()
    if t.startswith('business'):
        return 'business'
    if t.startswith('application') or t == 'dataobject':
        return 'application'
    if t in ('node', 'device', 'systemsoftware', 'artifact', 'path',
             'communicationnetwork') or t.startswith('technology'):
        return 'technology'
    return 'other'


def parse_model(path):
    tree = ET.parse(path)
    root = tree.getroot()

    elements = {}
    relationships = {}
    views = []

    for folder in root.findall('.//folder'):
        ftype = folder.get('type', '')
        for el in folder.findall('element'):
            eid = el.get('id', '')
            etype = el.get(f'{{{XSI}}}type', '')
            ename = el.get('name', 'Unnamed')
            if not eid:
                continue

            doc_el = el.find('documentation')
            doc = doc_el.text.strip() if (doc_el is not None and doc_el.text) else ''

            props = {p.get('key', ''): p.get('value', '') for p in el.findall('property')}

            if ftype in ('business', 'application', 'technology', 'strategy',
                         'motivation', 'implementation_migration', 'other'):
                elements[eid] = {
                    'id': eid,
                    'name': ename,
                    'type': etype.split(':')[-1] if ':' in etype else etype,
                    'layer': _layer(etype),
                    'description': doc,
                    'tags': props.get('Tags', ''),
                    'status': props.get('Status', ''),
                }

            elif ftype == 'relations':
                rtype = etype.split(':')[-1] if ':' in etype else etype
                relationships[eid] = {
                    'id': eid,
                    'type': rtype,
                    'source': el.get('source', ''),
                    'target': el.get('target', ''),
                    'name': el.get('name', ''),
                    'accessType': el.get('accessType', ''),
                }

    for folder in root.findall('.//folder[@type="diagrams"]'):
        for diag in folder.findall('element'):
            etype = diag.get(f'{{{XSI}}}type', '')
            if 'DiagramModel' not in etype:
                continue
            vid = diag.get('id', '')
            vname = diag.get('name', 'Unnamed View')
            doc_el = diag.find('documentation')
            vdesc = doc_el.text.strip() if (doc_el is not None and doc_el.text) else ''

            nodes = []
            edges = []
            diag_obj_map = {}

            for child in diag.findall('child'):
                ctype = child.get(f'{{{XSI}}}type', '')
                cid = child.get('id', '')

                if 'DiagramObject' in ctype:
                    elem_id = child.get('archimateElement', '')
                    diag_obj_map[cid] = elem_id
                    bounds = child.find('bounds')
                    if bounds is not None:
                        x = int(float(bounds.get('x', 0)))
                        y = int(float(bounds.get('y', 0)))
                        w = int(float(bounds.get('width', 130)))
                        h = int(float(bounds.get('height', 55)))
                    else:
                        x, y, w, h = 0, 0, 130, 55

                    if elem_id in elements:
                        e = elements[elem_id]
                        nodes.append({
                            'id': cid,
                            'elementId': elem_id,
                            'label': e['name'],
                            'type': e['type'],
                            'layer': e['layer'],
                            'x': x, 'y': y, 'width': w, 'height': h,
                            'description': e['description'],
                            'tags': e['tags'],
                            'status': e['status'],
                        })

                elif 'Connection' in ctype:
                    rid = child.get('archimateRelationship', '')
                    rel = relationships.get(rid, {})
                    edges.append({
                        'id': cid,
                        'from': child.get('source', ''),
                        'to': child.get('target', ''),
                        'relationshipId': rid,
                        'type': rel.get('type', 'AssociationRelationship'),
                        'label': rel.get('name', ''),
                    })

            views.append({'id': vid, 'name': vname, 'description': vdesc,
                          'nodes': nodes, 'edges': edges})

    return {
        'elements': list(elements.values()),
        'relationships': list(relationships.values()),
        'views': views,
        'generatedAt': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ArchiMate Model Viewer</title>
  <link rel="stylesheet"
    href="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/styles/vis-network.min.css"
    crossorigin="anonymous"/>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #eef0f4; color: #222; }

    /* ── Header ── */
    #hdr {
      background: linear-gradient(90deg, #1F3864 0%, #2F5496 100%);
      color: #fff; padding: 0 20px;
      height: 52px; display: flex; align-items: center; justify-content: space-between;
      box-shadow: 0 2px 6px rgba(0,0,0,.35); z-index: 10; position: relative;
    }
    #hdr h1 { font-size: 17px; font-weight: 600; letter-spacing: .3px; }
    #hdr .meta { font-size: 11px; opacity: .75; }

    /* ── Layout ── */
    #main { display: flex; height: calc(100vh - 52px); overflow: hidden; }

    /* ── Sidebar ── */
    #sidebar {
      width: 250px; min-width: 250px; background: #fff;
      border-right: 1px solid #dde; display: flex; flex-direction: column;
    }
    .sb-section { padding: 10px 12px; border-bottom: 1px solid #eee; }
    .sb-title {
      font-size: 11px; font-weight: 700; color: #888;
      text-transform: uppercase; letter-spacing: .6px; margin-bottom: 6px;
    }
    #view-sel {
      width: 100%; padding: 5px 8px; border: 1px solid #ccc; border-radius: 4px;
      font-size: 13px; background: #fff; cursor: pointer;
    }
    .layer-row { display: flex; align-items: center; gap: 7px; margin-bottom: 4px; font-size: 12px; cursor: pointer; }
    .ldot { width: 11px; height: 11px; border-radius: 2px; flex-shrink: 0; }
    .ldot-business   { background: #F5A623; }
    .ldot-application{ background: #4472C4; }
    .ldot-technology { background: #70AD47; }
    .ldot-other      { background: #9E9E9E; }

    #elem-list { flex: 1; overflow-y: auto; }
    .el-group-hdr {
      padding: 4px 12px; font-size: 10px; font-weight: 700; color: #888;
      text-transform: uppercase; background: #f7f7f7;
      border-bottom: 1px solid #eee; border-top: 1px solid #eee; margin-top: 2px;
      letter-spacing: .5px;
    }
    .el-row {
      padding: 5px 12px; cursor: pointer; font-size: 12px;
      border-left: 3px solid transparent; display: flex; align-items: center; gap: 7px;
    }
    .el-row:hover { background: #f0f4ff; }
    .el-row.active { background: #e6eeff; border-left-color: #2F5496; }
    .el-row .el-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .el-badge {
      font-size: 9px; padding: 1px 5px; border-radius: 3px;
      background: #eee; color: #666; white-space: nowrap;
    }

    /* ── Canvas ── */
    #canvas { flex: 1; background: #f3f5f8; position: relative; overflow: hidden; }
    #network { width: 100%; height: 100%; }
    #zoom-btns {
      position: absolute; bottom: 14px; right: 14px;
      display: flex; flex-direction: column; gap: 4px;
    }
    #layout-toggle {
      position: absolute; top: 10px; right: 14px;
      display: flex; gap: 0; border-radius: 5px; overflow: hidden;
      box-shadow: 0 1px 4px rgba(0,0,0,.2);
    }
    .lt-btn {
      padding: 5px 12px; font-size: 11px; font-weight: 600;
      cursor: pointer; border: none; background: #fff; color: #555;
      border-right: 1px solid #ddd;
    }
    .lt-btn:last-child { border-right: none; }
    .lt-btn.active { background: #2F5496; color: #fff; }
    .zoom-btn {
      width: 30px; height: 30px; background: #fff; border: 1px solid #ccc;
      border-radius: 4px; cursor: pointer; font-size: 16px; line-height: 28px;
      text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.15);
    }
    .zoom-btn:hover { background: #f0f4ff; }

    /* ── Details Panel ── */
    #details {
      width: 265px; min-width: 265px; background: #fff;
      border-left: 1px solid #dde; display: flex; flex-direction: column;
    }
    #det-hdr {
      background: #2F5496; color: #fff; padding: 10px 12px;
      font-size: 13px; font-weight: 600; flex-shrink: 0;
    }
    #det-body { flex: 1; overflow-y: auto; padding: 12px; }
    .d-row { margin-bottom: 12px; }
    .d-lbl { font-size: 10px; font-weight: 700; color: #999; text-transform: uppercase; margin-bottom: 3px; }
    .d-val { font-size: 13px; color: #222; word-break: break-word; }
    .d-badge { display: inline-block; padding: 2px 9px; border-radius: 10px; font-size: 11px; color: #fff; font-weight: 500; }
    .d-tag  { display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 11px; background: #eee; color: #555; margin: 2px 2px 0 0; }
    .d-rel  { font-size: 11px; padding: 2px 0; color: #555; }
    .no-sel { color: #bbb; font-size: 13px; padding: 24px 0; text-align: center; }

    /* ── Legend ── */
    #legend { padding: 10px 12px; border-top: 1px solid #eee; flex-shrink: 0; }
    .lg-title { font-size: 10px; font-weight: 700; color: #999; text-transform: uppercase; margin-bottom: 6px; }
    .lg-row { display: flex; align-items: center; gap: 7px; margin-bottom: 3px; font-size: 11px; color: #555; }
    .lg-line { width: 26px; height: 0; border-top: 2px solid #999; }
    .lg-dash { border-top-style: dashed; }
    .lg-red  { border-top-color: #e44; }
    .lg-blue { border-top-color: #44a; }
  </style>
</head>
<body>

<div id="hdr">
  <div>
    <h1>&#128736; ArchiMate Model Viewer</h1>
    <div class="meta">
      github.com/aruijter72/archimate-engine &nbsp;&bull;&nbsp; Read-only view
    </div>
  </div>
  <div class="meta" id="gen-ts"></div>
</div>

<div id="main">

  <!-- Sidebar -->
  <div id="sidebar">
    <div class="sb-section">
      <div class="sb-title">View</div>
      <select id="view-sel"></select>
      <div id="view-desc" style="font-size:11px;color:#888;margin-top:5px;"></div>
    </div>
    <div class="sb-section">
      <div class="sb-title">Layers</div>
      <label class="layer-row"><input type="checkbox" checked data-layer="business">
        <span class="ldot ldot-business"></span>Business</label>
      <label class="layer-row"><input type="checkbox" checked data-layer="application">
        <span class="ldot ldot-application"></span>Application</label>
      <label class="layer-row"><input type="checkbox" checked data-layer="technology">
        <span class="ldot ldot-technology"></span>Technology</label>
      <label class="layer-row"><input type="checkbox" checked data-layer="other">
        <span class="ldot ldot-other"></span>Other</label>
    </div>
    <div id="elem-list"></div>
  </div>

  <!-- Network Canvas -->
  <div id="canvas">
    <div id="network"></div>
    <div id="layout-toggle">
      <div class="lt-btn active" id="lt-grid" title="Fixed grid layout from model">Grid</div>
      <div class="lt-btn" id="lt-flow" title="Hierarchical flow layout following relationships">Flow &#8594;</div>
      <div class="lt-btn" id="lt-force" title="Force-directed auto layout">Auto</div>
    </div>
    <div id="zoom-btns">
      <div class="zoom-btn" id="btn-fit" title="Fit view">&#8596;</div>
      <div class="zoom-btn" id="btn-zin" title="Zoom in">+</div>
      <div class="zoom-btn" id="btn-zout" title="Zoom out">&#8722;</div>
    </div>
  </div>

  <!-- Details Panel -->
  <div id="details">
    <div id="det-hdr">Element Details</div>
    <div id="det-body"><div class="no-sel">Select an element to view details</div></div>
    <div id="legend">
      <div class="lg-title">Relationships</div>
      <div class="lg-row"><div class="lg-line"></div> Association</div>
      <div class="lg-row"><div class="lg-line lg-dash"></div> Serving / Access</div>
      <div class="lg-row"><div class="lg-line lg-red"></div> Triggering / Flow</div>
      <div class="lg-row"><div class="lg-line lg-blue"></div> Realization / Assignment</div>
    </div>
  </div>

</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.9/standalone/umd/vis-network.min.js"
  crossorigin="anonymous"></script>
<script>
/* ── Embedded model data ── */
const MODEL = __MODEL_JSON__;

/* ── Constants ── */
const LAYER_STYLE = {
  business:    { bg: '#FFF2CC', border: '#E6A800', font: '#6B4000' },
  application: { bg: '#DAE8FC', border: '#4472C4', font: '#1A3670' },
  technology:  { bg: '#D5E8D4', border: '#5B9B47', font: '#2A5020' },
  other:       { bg: '#f5f5f5', border: '#999',    font: '#444'    },
};
const REL_COLOR = {
  ServingRelationship:      '#888',
  AccessRelationship:       '#888',
  TriggeringRelationship:   '#e44',
  FlowRelationship:         '#e44',
  RealizationRelationship:  '#44a',
  AssignmentRelationship:   '#44a',
  CompositionRelationship:  '#555',
  AggregationRelationship:  '#555',
  AssociationRelationship:  '#aaa',
  InfluenceRelationship:    '#a64',
  SpecializationRelationship:'#a44',
};
const REL_DASH = {
  ServingRelationship:  [5, 5],
  AccessRelationship:   [5, 5],
  InfluenceRelationship:[8, 4],
  AssociationRelationship: [3, 3],
};

/* ── State ── */
let network = null;
let currentView = null;
const activeLayers = new Set(['business','application','technology','other']);

/* ── Init ── */
document.getElementById('gen-ts').textContent = 'Generated: ' + (MODEL.generatedAt || '');

function initViewSelector() {
  const sel = document.getElementById('view-sel');
  MODEL.views.forEach((v, i) => {
    const o = document.createElement('option');
    o.value = i; o.textContent = v.name; sel.appendChild(o);
  });
  sel.addEventListener('change', () => loadView(+sel.value));
  if (MODEL.views.length > 0) loadView(0);
}

function loadView(idx) {
  if (idx < 0 || idx >= MODEL.views.length) return;
  currentView = MODEL.views[idx];
  document.getElementById('view-desc').textContent = currentView.description || '';
  renderNetwork(currentView);
  renderSidebar(currentView);
  clearDetails();
}

/* ── Network ── */
function renderNetwork(view) {
  const visNodes = [];
  const visEdges = [];
  const nodeIds = new Set();

  view.nodes
    .filter(n => activeLayers.has(n.layer || 'other'))
    .forEach(n => {
      const s = LAYER_STYLE[n.layer] || LAYER_STYLE.other;
      nodeIds.add(n.id);
      visNodes.push({
        id: n.id,
        label: n.label,
        title: n.description || n.label,
        x: n.x + (n.width || 130) / 2,
        y: n.y + (n.height || 55) / 2,
        shape: 'box',
        color: { background: s.bg, border: s.border,
                 highlight: { background: s.bg, border: '#1F3864' } },
        font: { color: s.font, size: 12, face: 'Segoe UI, Arial' },
        widthConstraint:  { minimum: n.width || 130, maximum: n.width || 130 },
        heightConstraint: { minimum: n.height || 55 },
        borderWidth: 1.5,
        margin: 8,
        _data: n,
      });
    });

  view.edges
    .filter(e => nodeIds.has(e.from) && nodeIds.has(e.to))
    .forEach(e => {
      const col  = REL_COLOR[e.type] || '#aaa';
      const dash = REL_DASH[e.type] || false;
      visEdges.push({
        id: e.id, from: e.from, to: e.to,
        label: e.label || '',
        color: { color: col, highlight: col },
        dashes: dash,
        arrows: { to: { enabled: true, scaleFactor: 0.65 } },
        font: { size: 10, align: 'middle', color: '#666' },
        smooth: { type: 'curvedCW', roundness: 0.15 },
        title: (e.type || '').replace('Relationship', ''),
      });
    });

  const container = document.getElementById('network');
  const data = {
    nodes: new vis.DataSet(visNodes),
    edges: new vis.DataSet(visEdges),
  };
  const opts = buildOpts('grid');

function buildOpts(mode) {
  if (mode === 'flow') {
    return {
      physics: { enabled: false },
      interaction: { hover: true, tooltipDelay: 250, selectConnectedEdges: false },
      layout: {
        hierarchical: {
          enabled: true,
          direction: 'LR',
          sortMethod: 'directed',
          nodeSpacing: 140,
          levelSeparation: 220,
          treeSpacing: 160,
          blockShifting: true,
          edgeMinimization: true,
          parentCentralization: true,
        }
      },
      nodes: { fixed: false },
      edges: { selectionWidth: 2, smooth: { type: 'cubicBezier', forceDirection: 'horizontal', roundness: 0.4 } },
    };
  }
  if (mode === 'force') {
    return {
      physics: {
        enabled: true,
        solver: 'forceAtlas2Based',
        forceAtlas2Based: { gravitationalConstant: -80, centralGravity: 0.01, springLength: 180, springConstant: 0.06 },
        stabilization: { iterations: 200 },
      },
      interaction: { hover: true, tooltipDelay: 250, selectConnectedEdges: false },
      layout: { improvedLayout: true },
      nodes: { fixed: false },
      edges: { selectionWidth: 2 },
    };
  }
  // grid (default) — fixed positions from model
  return {
    physics: { enabled: false },
    interaction: { hover: true, tooltipDelay: 250, selectConnectedEdges: false },
    layout: { improvedLayout: false },
    nodes: { fixed: true },
    edges: { selectionWidth: 2 },
  };
}

  if (network) network.destroy();
  network = new vis.Network(container, data, buildOpts(currentLayout));

  network.on('selectNode', params => {
    if (!params.nodes.length) return;
    const nodeId = params.nodes[0];
    const n = visNodes.find(x => x.id === nodeId);
    if (n) { showDetails(n._data); highlightListItem(n.id); }
  });
  network.on('deselectNode', () => { clearDetails(); clearListHighlight(); });

  network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } });
}

/* ── Sidebar element list ── */
function renderSidebar(view) {
  const list = document.getElementById('elem-list');
  list.innerHTML = '';
  const layerOrder = ['business','application','technology','other'];
  const filtered = view.nodes.filter(n => activeLayers.has(n.layer || 'other'));

  if (!filtered.length) {
    list.innerHTML = '<div style="padding:16px;font-size:12px;color:#aaa">No elements visible</div>';
    return;
  }

  layerOrder.forEach(layer => {
    const items = filtered.filter(n => (n.layer || 'other') === layer);
    if (!items.length) return;

    const grp = document.createElement('div');
    grp.className = 'el-group-hdr';
    grp.textContent = layer.charAt(0).toUpperCase() + layer.slice(1) + ' (' + items.length + ')';
    list.appendChild(grp);

    items.forEach(n => {
      const row = document.createElement('div');
      row.className = 'el-row';
      row.dataset.nodeId = n.id;

      const dot = document.createElement('span');
      dot.className = 'ldot ldot-' + (n.layer || 'other');

      const nm = document.createElement('span');
      nm.className = 'el-name';
      nm.textContent = n.label;

      const badge = document.createElement('span');
      badge.className = 'el-badge';
      badge.textContent = shortType(n.type);

      row.append(dot, nm, badge);
      row.addEventListener('click', () => {
        clearListHighlight();
        row.classList.add('active');
        showDetails(n);
        if (network) {
          network.selectNodes([n.id]);
          network.focus(n.id, { scale: 1.0, animation: true });
        }
      });
      list.appendChild(row);
    });
  });
}

/* ── Details ── */
function showDetails(n) {
  const s = LAYER_STYLE[n.layer] || LAYER_STYLE.other;
  const typeLabel = (n.type || '').replace(/([A-Z])/g, ' $1').trim();
  let html = `
    <div class="d-row"><div class="d-lbl">Name</div>
      <div class="d-val"><strong>${esc(n.label)}</strong></div></div>
    <div class="d-row"><div class="d-lbl">Type</div>
      <div class="d-val"><span class="d-badge" style="background:${s.border}">${esc(typeLabel)}</span></div></div>
    <div class="d-row"><div class="d-lbl">Layer</div>
      <div class="d-val" style="text-transform:capitalize">${esc(n.layer || 'Unknown')}</div></div>`;

  if (n.status) html += `<div class="d-row"><div class="d-lbl">Status</div>
    <div class="d-val">${esc(n.status)}</div></div>`;

  if (n.description) html += `<div class="d-row"><div class="d-lbl">Description</div>
    <div class="d-val">${esc(n.description)}</div></div>`;

  if (n.tags) {
    const tags = n.tags.split(',').map(t => `<span class="d-tag">${esc(t.trim())}</span>`).join('');
    html += `<div class="d-row"><div class="d-lbl">Tags</div><div class="d-val">${tags}</div></div>`;
  }

  if (currentView) {
    const rels = currentView.edges.filter(e => e.from === n.id || e.to === n.id);
    if (rels.length) {
      const relHtml = rels.map(e => {
        const otherId = e.from === n.id ? e.to : e.from;
        const other = currentView.nodes.find(x => x.id === otherId);
        const dir = e.from === n.id ? '&rarr;' : '&larr;';
        const relType = (e.type || '').replace('Relationship', '');
        return `<div class="d-rel">${dir} <strong>${esc(relType)}</strong> ${esc(other ? other.label : otherId)}</div>`;
      }).join('');
      html += `<div class="d-row"><div class="d-lbl">Relationships (${rels.length})</div>
        <div class="d-val">${relHtml}</div></div>`;
    }
  }

  document.getElementById('det-body').innerHTML = html;
}

function clearDetails() {
  document.getElementById('det-body').innerHTML = '<div class="no-sel">Select an element to view details</div>';
}

/* ── Helpers ── */
function highlightListItem(nodeId) {
  clearListHighlight();
  document.querySelectorAll(`.el-row[data-node-id="${nodeId}"]`).forEach(r => r.classList.add('active'));
}
function clearListHighlight() {
  document.querySelectorAll('.el-row.active').forEach(r => r.classList.remove('active'));
}
function shortType(type) {
  if (!type) return '';
  const words = type.replace(/([A-Z])/g, ' $1').trim().split(' ');
  return words[words.length - 1];
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ── Layer filter ── */
document.querySelectorAll('[data-layer]').forEach(cb => {
  cb.addEventListener('change', () => {
    cb.checked ? activeLayers.add(cb.dataset.layer) : activeLayers.delete(cb.dataset.layer);
    if (currentView) {
      const idx = +document.getElementById('view-sel').value;
      loadView(idx);
    }
  });
});

/* ── Zoom buttons ── */
document.getElementById('btn-fit').addEventListener('click', () => network && network.fit({ animation: true }));
document.getElementById('btn-zin').addEventListener('click',  () => network && network.moveTo({ scale: network.getScale() * 1.25 }));
document.getElementById('btn-zout').addEventListener('click', () => network && network.moveTo({ scale: network.getScale() * 0.8 }));

/* ── Layout toggle ── */
let currentLayout = 'grid';
function setLayout(mode) {
  currentLayout = mode;
  document.querySelectorAll('.lt-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('lt-' + mode).classList.add('active');
  if (currentView) {
    const idx = +document.getElementById('view-sel').value;
    loadView(idx);
  }
}
document.getElementById('lt-grid').addEventListener('click',  () => setLayout('grid'));
document.getElementById('lt-flow').addEventListener('click',  () => setLayout('flow'));
document.getElementById('lt-force').addEventListener('click', () => setLayout('force'));

/* ── Start ── */
initViewSelector();
</script>
</body>
</html>
"""


def generate_html(model_data, output_path):
    json_str = json.dumps(model_data, indent=2, ensure_ascii=False)
    html = HTML_TEMPLATE.replace('__MODEL_JSON__', json_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    print(f'Saved: {output_path}')


def main():
    parser = argparse.ArgumentParser(description='Generate HTML viewer from model.archimate.')
    parser.add_argument('--model', default=str(BASE_DIR / 'model.archimate'))
    parser.add_argument('--output', default=str(BASE_DIR / 'docs' / 'index.html'))
    args = parser.parse_args()

    model_path = Path(args.model)
    output_path = Path(args.output)

    if not model_path.exists():
        print(f'Error: {model_path} not found. Run scripts/generate_model.py first.')
        raise SystemExit(1)

    print(f'Parsing {model_path} ...')
    data = parse_model(model_path)
    print(f'  Elements: {len(data["elements"])}  Relationships: {len(data["relationships"])}  '
          f'Views: {len(data["views"])}')

    print('Generating HTML viewer ...')
    generate_html(data, output_path)


if __name__ == '__main__':
    main()
