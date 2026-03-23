# archimate-engine

**Architecture by Code** — version-controlled ArchiMate modelling with three authoring paths and a read-only HTML view for stakeholders.

---

## Overview

```
model-input.xlsx          ← architect input form (Business / Application / Technology)
      │
      ▼  scripts/generate_model.py
model.archimate           ← Archi-compatible model (editable in Archi or by Claude)
      │
      ▼  scripts/generate_html.py
docs/index.html           ← interactive HTML view (published to GitHub Pages)
```

All three artefacts are kept in sync by a GitHub Actions pipeline that runs on every push to `main`.

---

## Three authoring paths

| Path | How |
|------|-----|
| **Excel form** | Edit `model-input.xlsx`, fill in the Business / Application / Technology sheets, push to GitHub. The pipeline auto-generates `model.archimate` + the HTML view. |
| **Archi tool** | Open `model.archimate` in [Archi](https://www.archimatetool.com/) (free, open-source). Edit visually, then push the file to GitHub. The pipeline auto-generates the HTML view. |
| **Claude prompt** | Ask Claude to add/change elements in the chat. Claude updates `model-input.xlsx` or `model.archimate` directly, then commits and pushes. |

---

## Quick start

### 1. Enable GitHub Pages

In your repository go to **Settings → Pages** and set the source to **GitHub Actions**.

### 2. Fill in the Excel form

Open `model-input.xlsx` and populate the four layer sheets:

| Sheet | What to fill in |
|-------|-----------------|
| **Business** | Business actors, roles, processes, services, objects |
| **Application** | Application components, interfaces, services, data objects |
| **Technology** | Nodes, devices, system software, networks |
| **Relationships** | Copy element IDs into Source ID / Target ID; choose relationship type |
| **Views** | Name your views; enter `ALL` or comma-separated element IDs |

**IDs are auto-assigned** — leave the ID column blank for new rows.

### 3. Push to GitHub

```bash
git add model-input.xlsx
git commit -m "feat: update architecture model"
git push
```

The pipeline will regenerate `model.archimate` and `docs/index.html`, then publish to GitHub Pages.

### 4. View the result

```
https://aruijter72.github.io/archimate-engine/
```

---

## Running scripts locally

```bash
pip install openpyxl

# (Re-)create the Excel template
python scripts/create_template.py model-input.xlsx

# Excel → model.archimate
python scripts/generate_model.py

# model.archimate → docs/index.html
python scripts/generate_html.py
```

---

## File reference

| File | Description |
|------|-------------|
| `model-input.xlsx` | Architect input form |
| `model.archimate` | ArchiMate 3 model — open in Archi for visual editing |
| `docs/index.html` | Self-contained interactive HTML viewer |
| `scripts/create_template.py` | Recreates the Excel template |
| `scripts/generate_model.py` | Excel → `model.archimate` |
| `scripts/generate_html.py` | `model.archimate` → `docs/index.html` |
| `.github/workflows/deploy.yml` | CI/CD pipeline |

---

## HTML viewer features

- View selector — switch between named ArchiMate views
- Layer filter — show/hide Business, Application, Technology layers
- Element list sidebar with clickable elements
- Details panel — type, description, status, tags, relationships
- Zoom controls
- Read-only — stakeholders can only view, not edit
