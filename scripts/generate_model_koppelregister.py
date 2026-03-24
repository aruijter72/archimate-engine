#!/usr/bin/env python3
"""
Generate model.archimate from Koppelregister_v1.xlsx.

ArchiMate 3 mapping:
  Gemeente / Organisatie  -> Grouping  (Business layer, municipality container)
  Domein / Taakveld       -> BusinessFunction
  Bronapplicatie /
  Doelapplicatie          -> ApplicationComponent
  Middleware              -> SystemSoftware  (Technology layer, ESB/integration hub)
  Integration row         -> FlowRelationship (app -> app)
  Middleware -> app       -> ServingRelationship (deduped)

Views:
  1. Integratie Landschap  – municipality zone layout, all apps + flows
  2–N. Per domein          – one view per business domain
"""

import re
import uuid
import argparse
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom

import pandas as pd

BASE_DIR  = Path(__file__).resolve().parent.parent
INPUT_XLS = BASE_DIR / "Koppelregister_v1.xlsx"
OUTPUT    = BASE_DIR / "model.archimate"

ARCH = "http://www.archimatetool.com/archimate"
XSI  = "http://www.w3.org/2001/XMLSchema-instance"

# ── Archi fill colours per layer / zone ───────────────────────────────────────
ZONE_STYLE = {
    "Krimpen":         dict(fill="#dae8fc", line="#6a9fd8", font="#003087"),
    "Capelle":         dict(fill="#d5e8d4", line="#5a9e6a", font="#1a5e20"),
    "Capelle/Krimpen": dict(fill="#ead1dc", line="#a0547a", font="#5c0033"),
    "IJsselgemeenten": dict(fill="#fff2cc", line="#c9a227", font="#7d4e00"),
    "Zuidplas":        dict(fill="#ffe6cc", line="#d4836a", font="#7d2e00"),
    "_ESB":            dict(fill="#f0f0f0", line="#888888", font="#333333"),
    "_Domain":         dict(fill="#f8f8ff", line="#aaaacc", font="#333366"),
}
APP_FILL    = "#dae8fc"
APP_LINE    = "#6a9fd8"
MW_FILL     = "#f5f5f5"
MW_LINE     = "#888888"
DOM_FILL    = "#fff8e1"
DOM_LINE    = "#c9a227"

# Canvas layout (pixels) for the Integratie Landschap view
# Two columns: left (Krimpen, IJsselgemeenten, Zuidplas) and right (Capelle, Capelle/Krimpen)
# ESB strip on the far right
ZONE_LAYOUT = {
    "Krimpen":         dict(x=20,   y=100,  w=680, h=440),
    "Capelle":         dict(x=720,  y=100,  w=680, h=440),
    "Capelle/Krimpen": dict(x=20,   y=560,  w=680, h=280),
    "IJsselgemeenten": dict(x=720,  y=560,  w=680, h=280),
    "Zuidplas":        dict(x=20,   y=860,  w=680, h=280),
    "_ESB":            dict(x=1420, y=100,  w=480, h=1040),
}
BOX_W, BOX_H = 160, 50
INNER_PAD    = 15   # padding inside zone box before first app
INNER_GAP    = 12   # gap between app boxes inside zone
COLS_IN_ZONE = 3    # app columns per zone row

# ── helpers ───────────────────────────────────────────────────────────────────

def mid():
    return "id-" + uuid.uuid4().hex[:24]

def clean(val):
    if pd.isna(val):
        return ""
    return str(val).strip()

def mw_parts(raw: str):
    parts = []
    for part in re.split(r"\s*[&,]\s*", raw):
        p = part.strip()
        if p and p.lower() not in ("nee", ""):
            parts.append(p)
    return parts

def prettify(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="unicode")
    dom = minidom.parseString(raw)
    lines = dom.toprettyxml(indent="  ").split("\n")
    lines = [l for l in lines if not l.startswith("<?xml")]
    return "\n".join(lines)

def make_child_node(parent, elem_id, rx, ry, w=BOX_W, h=BOX_H,
                    fill=APP_FILL, line=APP_LINE) -> ET.Element:
    """Add a DiagramObject child with relative bounds."""
    node = ET.SubElement(parent, "child")
    node.set(f"{{{XSI}}}type", "archimate:DiagramObject")
    node.set("id", mid())
    node.set("archimateElement", elem_id)
    node.set("fillColor", fill)
    node.set("lineColor", line)
    node.set("fontColor", "#000000")
    b = ET.SubElement(node, "bounds")
    b.set("x", str(rx)); b.set("y", str(ry))
    b.set("width", str(w)); b.set("height", str(h))
    return node

def make_group_box(parent, label_elem_id, x, y, w, h, style) -> ET.Element:
    """Add a large zone/grouping DiagramObject with label."""
    node = ET.SubElement(parent, "child")
    node.set(f"{{{XSI}}}type", "archimate:DiagramObject")
    node.set("id", mid())
    node.set("archimateElement", label_elem_id)
    node.set("fillColor",  style["fill"])
    node.set("lineColor",  style["line"])
    node.set("fontColor",  style["font"])
    node.set("fontSize", "12")
    node.set("fontStyle", "1")   # bold
    node.set("textPosition", "0")  # top-left label
    b = ET.SubElement(node, "bounds")
    b.set("x", str(x)); b.set("y", str(y))
    b.set("width", str(w)); b.set("height", str(h))
    return node

def add_conn(view, rel_id, src_node_id, tgt_node_id) -> ET.Element:
    conn = ET.SubElement(view, "connection")
    conn.set(f"{{{XSI}}}type", "archimate:Connection")
    conn.set("id", mid())
    conn.set("archimateRelationship", rel_id)
    conn.set("source", src_node_id)
    conn.set("target", tgt_node_id)
    return conn

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=str(INPUT_XLS))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()

    # ── 1. Read spreadsheet ─────────────────────────────────────────────────
    df = pd.read_excel(args.input, sheet_name="Koppelregister",
                       header=1, skiprows=[2], engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    data = df.dropna(subset=["Bronapplicatie"]).copy()
    data = data[data["Bronapplicatie"].astype(str).str.strip() != ""].reset_index(drop=True)

    # ── 2. Unique entities ──────────────────────────────────────────────────

    app_names = sorted(
        set(clean(v) for v in data["Bronapplicatie"])
        | set(clean(v) for v in data["Doelapplicatie"] if clean(v))
    )
    app_id = {name: mid() for name in app_names}

    # Primary gemeente per app (most frequent)
    app_gem_count: dict = defaultdict(lambda: defaultdict(int))
    for _, row in data.iterrows():
        gem = clean(row.get("Gemeente / Organisatie", ""))
        for aname in [clean(row["Bronapplicatie"]), clean(row.get("Doelapplicatie", ""))]:
            if aname and gem:
                app_gem_count[aname][gem] += 1
    app_primary_gem = {
        name: max(counts, key=counts.get)
        for name, counts in app_gem_count.items()
    }
    app_all_gems = {
        name: ", ".join(sorted(counts.keys()))
        for name, counts in app_gem_count.items()
    }

    # Middleware
    mw_names = sorted({
        p for raw in data["Middleware"].dropna()
        for p in mw_parts(clean(raw))
    })
    mw_id = {name: mid() for name in mw_names}

    # Business domains
    domain_names = sorted({clean(v) for v in data["Domein / Taakveld"].dropna() if clean(v)})
    dom_id = {name: mid() for name in domain_names}

    # Municipality groupings (including _ESB pseudo-zone for middleware)
    gemeente_names = sorted({g for g in app_primary_gem.values() if g})
    gem_id = {name: mid() for name in gemeente_names}
    esb_group_id = mid()   # Grouping element for ESB/Middleware zone

    # ── 3. Relationships ────────────────────────────────────────────────────

    flows = []
    for _, row in data.iterrows():
        src = clean(row["Bronapplicatie"])
        tgt = clean(row.get("Doelapplicatie", ""))
        if not (src and tgt and src in app_id and tgt in app_id and src != tgt):
            continue
        proto   = clean(row.get("Protocol", ""))
        pattern = clean(row.get("Integratie patroon", ""))
        desc    = clean(row.get("Interface beschrijving (doel)", ""))
        ref     = clean(row.get("Koppelingsreferentie", ""))
        dom     = clean(row.get("Domein / Taakveld", ""))
        gem     = clean(row.get("Gemeente / Organisatie", ""))
        flows.append({
            "id": mid(), "src": app_id[src], "tgt": app_id[tgt],
            "name": clean(row.get("Naam koppeling (data van naar)", "")),
            "ref": ref, "desc": desc, "pattern": pattern, "proto": proto,
            "domain": dom, "gem": gem,
            "src_name": src, "tgt_name": tgt,
        })

    mw_rels, mw_seen = [], set()
    for _, row in data.iterrows():
        raw_mw = clean(row.get("Middleware", ""))
        for part in mw_parts(raw_mw):
            if part not in mw_id:
                continue
            m_id = mw_id[part]
            for aname in [clean(row["Bronapplicatie"]), clean(row.get("Doelapplicatie", ""))]:
                a_id2 = app_id.get(aname)
                if a_id2:
                    key = (m_id, a_id2)
                    if key not in mw_seen:
                        mw_seen.add(key)
                        mw_rels.append({"id": mid(), "mw": m_id, "app": a_id2,
                                        "mw_name": part, "app_name": aname})

    dom_rels, dom_seen = [], set()
    for _, row in data.iterrows():
        dom = clean(row.get("Domein / Taakveld", ""))
        d_id = dom_id.get(dom)
        if not d_id:
            continue
        for aname in [clean(row["Bronapplicatie"]), clean(row.get("Doelapplicatie", ""))]:
            a_id2 = app_id.get(aname)
            if a_id2:
                key = (d_id, a_id2)
                if key not in dom_seen:
                    dom_seen.add(key)
                    dom_rels.append({"id": mid(), "dom": d_id, "app": a_id2})

    # ── 4. Build XML ────────────────────────────────────────────────────────
    ET.register_namespace("archimate", ARCH)
    ET.register_namespace("xsi",       XSI)

    model = ET.Element(f"{{{ARCH}}}model")
    model.set(f"{{{XSI}}}schemaLocation",
              "http://www.archimatetool.com/archimate "
              "http://www.archimatetool.com/archimate/model/archimate.xsd")
    model.set("name", "Koppelregister IJsselgemeenten")
    model.set("id", mid()); model.set("version", "4.0")

    def folder(name, ftype):
        f = ET.SubElement(model, "folder")
        f.set("name", name); f.set("id", mid()); f.set("type", ftype)
        return f

    f_bus   = folder("Business",     "business")
    f_app   = folder("Application",  "application")
    f_tech  = folder("Technology",   "technology")
    f_rel   = folder("Relations",    "relations")
    f_views = folder("Views",        "diagrams")

    def el(parent, xsi_type, name, eid):
        e = ET.SubElement(parent, "element")
        e.set(f"{{{XSI}}}type", xsi_type)
        e.set("name", name); e.set("id", eid)
        return e

    def prop(parent, key, value):
        p = ET.SubElement(parent, "property")
        p.set("key", key); p.set("value", value)

    def doc(parent, text):
        d = ET.SubElement(parent, "documentation")
        d.text = text

    # Business: municipality groupings
    for name in gemeente_names:
        e = el(f_bus, "archimate:Grouping", name, gem_id[name])
        doc(e, f"Municipality / organisation: {name}")

    # Business: ESB grouping
    esb_el = el(f_bus, "archimate:Grouping", "ESB / Middleware", esb_group_id)
    doc(esb_el, "Integration platform and middleware components")

    # Business: domains
    for name in domain_names:
        el(f_bus, "archimate:BusinessFunction", name, dom_id[name])

    # Application: components
    for name in app_names:
        e = el(f_app, "archimate:ApplicationComponent", name, app_id[name])
        gem = app_primary_gem.get(name, "")
        all_g = app_all_gems.get(name, "")
        if gem:   prop(e, "Gemeente",   gem)
        if all_g: prop(e, "Gemeenten",  all_g)

    # Technology: middleware
    for name in mw_names:
        el(f_tech, "archimate:SystemSoftware", name, mw_id[name])

    # Relations
    for f in flows:
        e = ET.SubElement(f_rel, "element")
        e.set(f"{{{XSI}}}type", "archimate:FlowRelationship")
        e.set("id", f["id"]); e.set("source", f["src"]); e.set("target", f["tgt"])
        if f["name"]: e.set("name", f["name"])
        parts = []
        if f["ref"]:     parts.append(f"Ref: {f['ref']}")
        if f["desc"]:    parts.append(f["desc"])
        if f["pattern"]: parts.append(f"Pattern: {f['pattern']}")
        if f["proto"]:   parts.append(f"Protocol: {f['proto']}")
        if parts: doc(e, "\n".join(parts))
        if f["domain"]: prop(e, "Domein",   f["domain"])
        if f["gem"]:    prop(e, "Gemeente", f["gem"])

    for r in mw_rels:
        e = ET.SubElement(f_rel, "element")
        e.set(f"{{{XSI}}}type", "archimate:ServingRelationship")
        e.set("id", r["id"]); e.set("source", r["mw"]); e.set("target", r["app"])

    for r in dom_rels:
        e = ET.SubElement(f_rel, "element")
        e.set(f"{{{XSI}}}type", "archimate:AssociationRelationship")
        e.set("id", r["id"]); e.set("source", r["dom"]); e.set("target", r["app"])

    # ── 5. Views ────────────────────────────────────────────────────────────

    def landscape_view():
        """Main view: municipality zone boxes with apps inside, ESB on the right."""
        view = ET.SubElement(f_views, "element")
        view.set(f"{{{XSI}}}type", "archimate:ArchimateDiagramModel")
        view.set("name", "Integratie Landschap"); view.set("id", mid())

        # node_id_map: archimateElement id -> DiagramObject node id (for connections)
        node_id_map: dict = {}

        # Group apps by zone (municipality)
        zone_apps: dict = defaultdict(list)
        for aname in app_names:
            gem = app_primary_gem.get(aname, "IJsselgemeenten")
            zone = gem if gem in ZONE_LAYOUT else "IJsselgemeenten"
            zone_apps[zone].append(aname)

        # Draw municipality zone boxes + nested apps
        for zone_name, zlay in ZONE_LAYOUT.items():
            if zone_name == "_ESB":
                continue  # handled separately
            # Get style; fall back to IJsselgemeenten style
            style = ZONE_STYLE.get(zone_name, ZONE_STYLE["IJsselgemeenten"])
            group_elem_id = gem_id.get(zone_name, mid())
            group_node = make_group_box(view, group_elem_id,
                                        zlay["x"], zlay["y"],
                                        zlay["w"], zlay["h"], style)

            # Position app boxes inside the zone (relative coordinates)
            apps = zone_apps.get(zone_name, [])
            for ai, aname in enumerate(apps):
                col  = ai % COLS_IN_ZONE
                row  = ai // COLS_IN_ZONE
                rx   = INNER_PAD + col * (BOX_W + INNER_GAP)
                ry   = 35 + row * (BOX_H + INNER_GAP)
                app_node = make_child_node(group_node, app_id[aname],
                                           rx, ry, BOX_W, BOX_H,
                                           APP_FILL, APP_LINE)
                node_id_map[app_id[aname]] = app_node.get("id")

        # ESB / Middleware zone on the right
        esb_lay   = ZONE_LAYOUT["_ESB"]
        esb_style = ZONE_STYLE["_ESB"]
        esb_node  = make_group_box(view, esb_group_id,
                                   esb_lay["x"], esb_lay["y"],
                                   esb_lay["w"], esb_lay["h"], esb_style)
        for mi, mname in enumerate(mw_names):
            col = mi % 2
            row = mi // 2
            rx  = INNER_PAD + col * (190 + INNER_GAP)
            ry  = 35 + row * (BOX_H + INNER_GAP)
            mw_node = make_child_node(esb_node, mw_id[mname],
                                      rx, ry, 190, BOX_H, MW_FILL, MW_LINE)
            node_id_map[mw_id[mname]] = mw_node.get("id")

        # Connections (flow: app -> app) — added at view level
        seen_pairs: set = set()
        for f in flows:
            src_nid = node_id_map.get(f["src"])
            tgt_nid = node_id_map.get(f["tgt"])
            if src_nid and tgt_nid:
                pair = (f["src"], f["tgt"])
                if pair not in seen_pairs:   # deduplicate for readability
                    seen_pairs.add(pair)
                    add_conn(view, f["id"], src_nid, tgt_nid)

        # Middleware serving connections (deduped)
        for r in mw_rels:
            mw_nid  = node_id_map.get(r["mw"])
            app_nid = node_id_map.get(r["app"])
            if mw_nid and app_nid:
                add_conn(view, r["id"], mw_nid, app_nid)

        return view

    landscape_view()

    # Domain-specific views (one per domein)
    domains_present = sorted({f["domain"] for f in flows if f["domain"]})
    for dname in domains_present:
        dom_flows = [f for f in flows if f["domain"] == dname]
        dom_app_names = sorted({
            n for f in dom_flows for n in (f["src_name"], f["tgt_name"])
        })

        view = ET.SubElement(f_views, "element")
        view.set(f"{{{XSI}}}type", "archimate:ArchimateDiagramModel")
        view.set("name", f"Domein: {dname}"); view.set("id", mid())

        node_id_map: dict = {}

        # Group by gemeente within this domain view
        zone_apps2: dict = defaultdict(list)
        for aname in dom_app_names:
            gem = app_primary_gem.get(aname, "IJsselgemeenten")
            zone = gem if gem in ZONE_LAYOUT else "IJsselgemeenten"
            zone_apps2[zone].append(aname)

        y_offset = 20
        for zone_name in sorted(zone_apps2.keys()):
            apps = zone_apps2[zone_name]
            if not apps:
                continue
            style   = ZONE_STYLE.get(zone_name, ZONE_STYLE["IJsselgemeenten"])
            gem_eid = gem_id.get(zone_name, mid())
            zone_w  = COLS_IN_ZONE * (BOX_W + INNER_GAP) + INNER_PAD * 2
            rows    = (len(apps) + COLS_IN_ZONE - 1) // COLS_IN_ZONE
            zone_h  = 35 + rows * (BOX_H + INNER_GAP) + INNER_PAD

            gn = make_group_box(view, gem_eid, 20, y_offset, zone_w, zone_h, style)
            for ai, aname in enumerate(apps):
                col  = ai % COLS_IN_ZONE; row = ai // COLS_IN_ZONE
                rx   = INNER_PAD + col * (BOX_W + INNER_GAP)
                ry   = 35 + row * (BOX_H + INNER_GAP)
                an   = make_child_node(gn, app_id[aname], rx, ry,
                                       BOX_W, BOX_H, APP_FILL, APP_LINE)
                node_id_map[app_id[aname]] = an.get("id")
            y_offset += zone_h + 20

        # ESB middleware in this domain
        dom_mw_names = sorted({
            r["mw_name"] for r in mw_rels
            if r["app_name"] in dom_app_names
        })
        if dom_mw_names:
            esb_h = 35 + ((len(dom_mw_names) + 1) // 2) * (BOX_H + INNER_GAP) + INNER_PAD
            esb_x = COLS_IN_ZONE * (BOX_W + INNER_GAP) + INNER_PAD * 2 + 40
            en = make_group_box(view, esb_group_id, esb_x, 20,
                                420, max(esb_h, 120), ZONE_STYLE["_ESB"])
            for mi, mname in enumerate(dom_mw_names):
                col = mi % 2; row = mi // 2
                mn  = make_child_node(en, mw_id[mname],
                                      INNER_PAD + col * 200, 35 + row * (BOX_H + INNER_GAP),
                                      190, BOX_H, MW_FILL, MW_LINE)
                node_id_map[mw_id[mname]] = mn.get("id")

        seen_pairs2: set = set()
        for f in dom_flows:
            src_nid = node_id_map.get(f["src"])
            tgt_nid = node_id_map.get(f["tgt"])
            if src_nid and tgt_nid:
                pair = (f["src"], f["tgt"])
                if pair not in seen_pairs2:
                    seen_pairs2.add(pair)
                    add_conn(view, f["id"], src_nid, tgt_nid)
        for r in mw_rels:
            if r["app_name"] not in dom_app_names:
                continue
            mw_nid  = node_id_map.get(r["mw"])
            app_nid = node_id_map.get(r["app"])
            if mw_nid and app_nid:
                add_conn(view, r["id"], mw_nid, app_nid)

    # ── 6. Write output ─────────────────────────────────────────────────────
    header  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_str = header + prettify(model)
    Path(args.output).write_text(xml_str, encoding="utf-8")

    n_views = 1 + len(domains_present)
    print(f"Written: {args.output}")
    print(f"  {len(app_names)} application components")
    print(f"  {len(mw_names)} middleware / ESB components")
    print(f"  {len(domain_names)} business functions (domains)")
    print(f"  {len(gemeente_names)} municipality groupings")
    print(f"  {len(flows)} flow relationships")
    print(f"  {len(mw_rels)} serving relationships (app ↔ middleware)")
    print(f"  {n_views} views (1 landscape + {len(domains_present)} domain views)")


if __name__ == "__main__":
    main()
