#!/usr/bin/env python3
"""
Generate model.archimate from Koppelregister_v1.xlsx.

ArchiMate mapping:
  Domein / Taakveld   -> BusinessFunction  (Business layer)
  Bronapplicatie /
  Doelapplicatie      -> ApplicationComponent (Application layer)
  Middleware          -> SystemSoftware       (Technology layer)
  Integration row     -> FlowRelationship between ApplicationComponents
  App <-> Middleware  -> ServingRelationship (deduped)
  Domain -> App       -> AssociationRelationship (deduped)

Views generated:
  1. Volledig Koppelregister  – all apps + all flows
  2–8. Per domein             – one view per business domain
  9. Middleware Overzicht     – apps grouped by ESB/middleware
"""

import re
import uuid
import argparse
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.dom import minidom

import pandas as pd

BASE_DIR  = Path(__file__).resolve().parent.parent
INPUT_XLS = BASE_DIR / "Koppelregister_v1.xlsx"
OUTPUT    = BASE_DIR / "model.archimate"

ARCH = "http://www.archimatetool.com/archimate"
XSI  = "http://www.w3.org/2001/XMLSchema-instance"

# ── helpers ───────────────────────────────────────────────────────────────────

def mid():
    return "id-" + uuid.uuid4().hex[:24]

def clean(val):
    if pd.isna(val):
        return ""
    return str(val).strip()

def mw_parts(raw: str):
    """Split a Middleware cell that may contain ' & ' or ','."""
    parts = []
    for part in re.split(r"\s*[&,]\s*", raw):
        p = part.strip()
        if p and p.lower() not in ("nee", ""):
            parts.append(p)
    return parts

def prettify(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="unicode")
    dom = minidom.parseString(raw)
    lines = dom.toprettyxml(indent="  ", encoding=None).split("\n")
    # Remove the extra XML declaration minidom adds
    lines = [l for l in lines if not l.startswith("<?xml")]
    return "\n".join(lines)

# ── view layout helpers ───────────────────────────────────────────────────────

BOX_W, BOX_H = 160, 50
GAP_X, GAP_Y = 20, 20
COLS = 7          # app columns per row

def grid_pos(idx, x0=50, y0=50, cols=COLS):
    row, col = divmod(idx, cols)
    x = x0 + col * (BOX_W + GAP_X)
    y = y0 + row * (BOX_H + GAP_Y)
    return x, y

def add_node(parent: ET.Element, elem_id: str, x: int, y: int,
             w: int = BOX_W, h: int = BOX_H) -> ET.Element:
    node = ET.SubElement(parent, "child")
    node.set("xsi:type", "archimate:DiagramObject")
    node.set("id", mid())
    node.set("archimateElement", elem_id)
    bounds = ET.SubElement(node, "bounds")
    bounds.set("x", str(x)); bounds.set("y", str(y))
    bounds.set("width", str(w)); bounds.set("height", str(h))
    return node

def add_conn(parent: ET.Element, rel_id: str,
             src_node: ET.Element, tgt_node: ET.Element) -> ET.Element:
    conn = ET.SubElement(parent, "connection")
    conn.set("xsi:type", "archimate:Connection")
    conn.set("id", mid())
    conn.set("archimateRelationship", rel_id)
    conn.set("source", src_node.get("id"))
    conn.set("target", tgt_node.get("id"))
    return conn

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default=str(INPUT_XLS))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()

    # ── 1. Read spreadsheet ─────────────────────────────────────────────────
    df = pd.read_excel(args.input, sheet_name="Koppelregister", header=1, skiprows=[2], engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    data = df.dropna(subset=["Bronapplicatie"]).copy()
    data = data[data["Bronapplicatie"].astype(str).str.strip() != ""].reset_index(drop=True)

    # ── 2. Collect unique entities ──────────────────────────────────────────

    # Applications (preserve insertion order = alphabetical after sort)
    app_names = sorted(
        set(clean(v) for v in data["Bronapplicatie"])
        | set(clean(v) for v in data["Doelapplicatie"] if clean(v))
    )
    app_id = {name: mid() for name in app_names}

    # Middleware (split compound cells)
    mw_names = sorted({
        p
        for raw in data["Middleware"].dropna()
        for p in mw_parts(clean(raw))
    })
    mw_id = {name: mid() for name in mw_names}

    # Business domains
    domain_names = sorted({clean(v) for v in data["Domein / Taakveld"].dropna() if clean(v)})
    dom_id = {name: mid() for name in domain_names}

    # ── 3. Collect relationships ────────────────────────────────────────────

    # Flow: app → app  (one per integration row; keep duplicates to capture every named flow)
    flows = []
    for _, row in data.iterrows():
        src = clean(row["Bronapplicatie"])
        tgt = clean(row.get("Doelapplicatie", ""))
        if src and tgt and src in app_id and tgt in app_id and src != tgt:
            flows.append({
                "id":      mid(),
                "src":     app_id[src],
                "tgt":     app_id[tgt],
                "name":    clean(row.get("Naam koppeling (data van naar)", "")),
                "ref":     clean(row.get("Koppelingsreferentie", "")),
                "desc":    clean(row.get("Interface beschrijving (doel)", "")),
                "pattern": clean(row.get("Integratie patroon", "")),
                "proto":   clean(row.get("Protocol", "")),
                "domain":  clean(row.get("Domein / Taakveld", "")),
                "gem":     clean(row.get("Gemeente / Organisatie", "")),
                "src_name": src,
                "tgt_name": tgt,
            })

    # Serving: middleware → app  (deduped)
    mw_rels = []
    mw_seen: set = set()
    for _, row in data.iterrows():
        raw_mw = clean(row.get("Middleware", ""))
        for part in mw_parts(raw_mw):
            if part not in mw_id:
                continue
            m_id = mw_id[part]
            for app_name in [clean(row["Bronapplicatie"]), clean(row.get("Doelapplicatie", ""))]:
                a_id = app_id.get(app_name)
                if a_id:
                    key = (m_id, a_id)
                    if key not in mw_seen:
                        mw_seen.add(key)
                        mw_rels.append({"id": mid(), "mw": m_id, "app": a_id,
                                        "mw_name": part, "app_name": app_name})

    # Association: domain → app  (deduped)
    dom_rels = []
    dom_seen: set = set()
    for _, row in data.iterrows():
        dom = clean(row.get("Domein / Taakveld", ""))
        d_id = dom_id.get(dom)
        if not d_id:
            continue
        for app_name in [clean(row["Bronapplicatie"]), clean(row.get("Doelapplicatie", ""))]:
            a_id = app_id.get(app_name)
            if a_id:
                key = (d_id, a_id)
                if key not in dom_seen:
                    dom_seen.add(key)
                    dom_rels.append({"id": mid(), "dom": d_id, "app": a_id})

    # ── 4. Build XML ────────────────────────────────────────────────────────
    ET.register_namespace("archimate", ARCH)
    ET.register_namespace("xsi",       XSI)

    model = ET.Element(f"{{{ARCH}}}model")
    model.set(f"{{{XSI}}}schemaLocation",
              "http://www.archimatetool.com/archimate "
              "http://www.archimatetool.com/archimate/model/archimate.xsd")
    model.set("name",    "Koppelregister IJsselgemeenten")
    model.set("id",      mid())
    model.set("version", "4.0")

    # Folders
    f_bus   = ET.SubElement(model, "folder"); f_bus.set("name",  "Business");     f_bus.set("id", mid()); f_bus.set("type", "business")
    f_app   = ET.SubElement(model, "folder"); f_app.set("name",  "Application");  f_app.set("id", mid()); f_app.set("type", "application")
    f_tech  = ET.SubElement(model, "folder"); f_tech.set("name", "Technology");   f_tech.set("id", mid()); f_tech.set("type", "technology")
    f_rel   = ET.SubElement(model, "folder"); f_rel.set("name",  "Relations");    f_rel.set("id", mid()); f_rel.set("type", "relations")
    f_views = ET.SubElement(model, "folder"); f_views.set("name","Views");        f_views.set("id", mid()); f_views.set("type", "diagrams")

    # Business: domains
    for name in domain_names:
        el = ET.SubElement(f_bus, "element")
        el.set(f"{{{XSI}}}type", "archimate:BusinessFunction")
        el.set("name", name); el.set("id", dom_id[name])

    # Application: components
    for name in app_names:
        el = ET.SubElement(f_app, "element")
        el.set(f"{{{XSI}}}type", "archimate:ApplicationComponent")
        el.set("name", name); el.set("id", app_id[name])

    # Technology: middleware
    for name in mw_names:
        el = ET.SubElement(f_tech, "element")
        el.set(f"{{{XSI}}}type", "archimate:SystemSoftware")
        el.set("name", name); el.set("id", mw_id[name])

    # Relations
    for f in flows:
        el = ET.SubElement(f_rel, "element")
        el.set(f"{{{XSI}}}type", "archimate:FlowRelationship")
        el.set("id",     f["id"])
        el.set("source", f["src"])
        el.set("target", f["tgt"])
        if f["name"]:
            el.set("name", f["name"])
        if f["desc"] or f["ref"] or f["pattern"] or f["proto"]:
            doc_parts = []
            if f["ref"]:     doc_parts.append(f"Ref: {f['ref']}")
            if f["desc"]:    doc_parts.append(f["desc"])
            if f["pattern"]: doc_parts.append(f"Pattern: {f['pattern']}")
            if f["proto"]:   doc_parts.append(f"Protocol: {f['proto']}")
            doc = ET.SubElement(el, "documentation")
            doc.text = "\n".join(doc_parts)
        if f["domain"]:
            prop = ET.SubElement(el, "property")
            prop.set("key", "Domein"); prop.set("value", f["domain"])
        if f["gem"]:
            prop = ET.SubElement(el, "property")
            prop.set("key", "Gemeente"); prop.set("value", f["gem"])

    for r in mw_rels:
        el = ET.SubElement(f_rel, "element")
        el.set(f"{{{XSI}}}type", "archimate:ServingRelationship")
        el.set("id",     r["id"])
        el.set("source", r["mw"])
        el.set("target", r["app"])

    for r in dom_rels:
        el = ET.SubElement(f_rel, "element")
        el.set(f"{{{XSI}}}type", "archimate:AssociationRelationship")
        el.set("id",     r["id"])
        el.set("source", r["dom"])
        el.set("target", r["app"])

    # ── 5. Views ────────────────────────────────────────────────────────────

    def make_view(parent_folder, view_name, incl_apps, incl_flows,
                  incl_mw=True, incl_doms=True):
        """Build a view diagram element with positioned nodes and connections."""
        view = ET.SubElement(parent_folder, "element")
        view.set(f"{{{XSI}}}type", "archimate:ArchimateDiagramModel")
        view.set("name", view_name)
        view.set("id",   mid())

        node_map: dict = {}  # elem_id -> DiagramObject element

        # --- Domain row at top ---
        if incl_doms:
            relevant_doms = sorted({
                f["domain"] for f in incl_flows if f["domain"] and f["domain"] in dom_id
            })
            for di, dname in enumerate(relevant_doms):
                d_id = dom_id[dname]
                x, y = grid_pos(di, x0=50, y0=20, cols=len(relevant_doms) or 1)
                node_map[d_id] = add_node(view, d_id, x, y, w=BOX_W + 40, h=BOX_H)

        # --- App grid in the middle ---
        y0_apps = 130
        for ai, aname in enumerate(incl_apps):
            a_id = app_id[aname]
            x, y = grid_pos(ai, x0=50, y0=y0_apps)
            node_map[a_id] = add_node(view, a_id, x, y)

        # --- Middleware row at the bottom ---
        if incl_mw:
            relevant_mw = sorted({
                r["mw_name"] for r in mw_rels
                if r["app_name"] in incl_apps and r["mw_name"] in mw_id
            })
            rows_used  = (len(incl_apps) + COLS - 1) // COLS
            y0_mw      = y0_apps + rows_used * (BOX_H + GAP_Y) + 60
            for mi, mname in enumerate(relevant_mw):
                m_id = mw_id[mname]
                x, y = grid_pos(mi, x0=50, y0=y0_mw, cols=4)
                node_map[m_id] = add_node(view, m_id, x, y, w=BOX_W + 60, h=BOX_H)

        # --- Connections ---
        for f in incl_flows:
            src_node = node_map.get(f["src"])
            tgt_node = node_map.get(f["tgt"])
            if src_node is not None and tgt_node is not None:
                add_conn(view, f["id"], src_node, tgt_node)

        for r in mw_rels:
            mw_node  = node_map.get(r["mw"])
            app_node = node_map.get(r["app"])
            if mw_node is not None and app_node is not None:
                add_conn(view, r["id"], mw_node, app_node)

        return view

    # View 1: Full overview
    make_view(f_views, "Volledig Koppelregister",
              incl_apps=app_names,
              incl_flows=flows,
              incl_mw=True, incl_doms=True)

    # Views 2–N: per domain
    domains_in_flows = sorted({f["domain"] for f in flows if f["domain"]})
    for dname in domains_in_flows:
        dom_flows = [f for f in flows if f["domain"] == dname]
        dom_apps  = sorted({
            name for f in dom_flows
            for name in (f["src_name"], f["tgt_name"])
        })
        make_view(f_views, f"Domein: {dname}",
                  incl_apps=dom_apps,
                  incl_flows=dom_flows,
                  incl_mw=True, incl_doms=False)

    # View: Middleware overview (apps grouped by primary middleware)
    mw_flows = [f for f in flows if any(
        r["mw_name"] for r in mw_rels
        if r["app_name"] in (f["src_name"], f["tgt_name"])
    )]
    make_view(f_views, "Middleware Overzicht",
              incl_apps=app_names,
              incl_flows=mw_flows,
              incl_mw=True, incl_doms=False)

    # ── 6. Write output ─────────────────────────────────────────────────────
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_str = header + prettify(model)
    Path(args.output).write_text(xml_str, encoding="utf-8")

    print(f"Written: {args.output}")
    print(f"  {len(app_names)} applications")
    print(f"  {len(mw_names)} middleware components")
    print(f"  {len(domain_names)} business domains")
    print(f"  {len(flows)} flow relationships")
    print(f"  {len(mw_rels)} app-middleware serving relationships")
    print(f"  {len(dom_rels)} domain-app associations")
    print(f"  {1 + len(domains_in_flows) + 1} views generated")


if __name__ == "__main__":
    main()
