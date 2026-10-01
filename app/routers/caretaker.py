"""🏖️ Vacation caretaker sheet — print-friendly page for the garden-sitter.

GET /api/caretaker-sheet -> a self-contained HTML page (inline CSS, no JS)
with sage/navy/beige palette and @media print rules. Never raises: an empty
garden still gets a friendly sheet.
"""
from __future__ import annotations

import html
from datetime import date as Date

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app.database import get_session

router = APIRouter()

# Sage green / navy / beige — Verdant palette.
CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: Georgia, 'Times New Roman', serif; background: #f8f2e6;
       color: #1b3049; margin: 0; padding: 2rem 1rem; }
.page { max-width: 720px; margin: 0 auto; background: #fffdf7;
        border: 2px solid #688d61; border-radius: 14px; padding: 2rem 2.25rem;
        box-shadow: 0 6px 24px rgba(27,48,73,.12); }
h1 { margin: 0 0 .25rem; font-size: 1.9rem; color: #1b3049; }
.subtitle { color: #41593d; margin: 0 0 1.5rem; }
h2 { font-size: 1.25rem; color: #1b3049; border-bottom: 2px solid #a4c09d;
     padding-bottom: .25rem; margin: 1.75rem 0 .75rem; }
ul { margin: .25rem 0; padding-left: 1.4rem; }
li { margin: .35rem 0; }
.tag { display: inline-block; font-size: .72rem; font-weight: bold;
       text-transform: uppercase; letter-spacing: .04em; border-radius: 999px;
       padding: .1rem .6rem; margin-right: .5rem; }
.tag.overdue { background: #e2574c; color: #fff; }
.tag.due { background: #e09f3e; color: #1b3049; }
.tag.soon { background: #c6d8c1; color: #41593d; }
.note { color: #41593d; font-size: .9rem; }
.blank { border-bottom: 1px solid #688d61; height: 2rem; }
.blank-line { margin: .9rem 0; }
.empty { color: #688d61; font-style: italic; }
.footer { margin-top: 2rem; font-size: .8rem; color: #688d61; text-align: center; }
@media print {
  body { background: #fff; padding: 0; }
  .page { border: none; border-radius: 0; box-shadow: none; max-width: none;
          padding: 0; }
  h1, h2 { break-after: avoid; }
  section { break-inside: avoid; }
}
"""


def _esc(text) -> str:
    return html.escape(str(text or ""))


def _status_tag(status: str) -> str:
    if status == "overdue":
        return '<span class="tag overdue">overdue</span>'
    if status == "due":
        return '<span class="tag due">due today</span>'
    if status == "soon":
        return '<span class="tag soon">coming up</span>'
    return ""


def build_caretaker_html(data: dict) -> str:
    """Render the sheet from caretaker_data(). Pure — never raises."""
    try:
        today = Date.today().strftime("%A, %B %d, %Y")
        water = data.get("watering_due") or []
        harvest = data.get("harvest_ready") or []
        pests = data.get("pest_watches") or []
        notes = data.get("general_notes") or []

        if water:
            water_items = "".join(
                f"<li>{_status_tag(w.get('status', ''))}"
                f"<strong>{_esc(w.get('plant_name'))}</strong>"
                + (f" <span class='note'>— due { _esc(w.get('due_date'))}</span>"
                   if w.get("due_date") else "")
                + "</li>"
                for w in water)
        else:
            water_items = "<li class='empty'>Nothing due — water as needed.</li>"

        if harvest:
            harvest_items = "".join(
                f"<li><strong>{_esc(h.get('plant_name'))}</strong>"
                + (f" <span class='note'>(ready since {_esc(h.get('ready_date'))})</span>"
                   if h.get("ready_date") else "")
                + "</li>"
                for h in harvest)
        else:
            harvest_items = "<li class='empty'>Nothing ripe right now.</li>"

        if pests:
            pest_items = "".join(
                f"<li><strong>{_esc(p.get('pest_name'))}</strong>"
                f" on {_esc(p.get('plant_name'))}"
                + (f" — <span class='note'>{_esc(p.get('treatment'))}</span>"
                   if p.get("treatment") else "")
                + (f" <span class='note'>({_esc(p.get('notes'))})</span>"
                   if p.get("notes") else "")
                + "</li>"
                for p in pests)
        else:
            pest_items = "<li class='empty'>No pest issues on record.</li>"

        if notes:
            note_items = "".join(f"<li>{_esc(n)}</li>" for n in notes)
        else:
            note_items = "<li class='empty'>No notes.</li>"

        contact_lines = "".join(
            f"<p class='blank-line'><strong>{_esc(label)}:</strong> "
            f"<span class='blank' style='display:inline-block;min-width:60%;'>"
            f"&nbsp;</span></p>"
            for label in ("Vet / garden helpline", "Neighbor", "My number"))

        return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Garden Caretaker Sheet</title>
<style>{CSS}</style></head>
<body>
<div class="page">
  <h1>🏖️ Garden Caretaker Sheet</h1>
  <p class="subtitle">Everything you need while the gardener is away — { _esc(today)}.</p>

  <section><h2>💧 Water these</h2><ul>{water_items}</ul>
  <p class="note">When in doubt: containers dry out faster than raised beds.</p></section>

  <section><h2>🧺 Ready to pick</h2><ul>{harvest_items}</ul></section>

  <section><h2>🐛 Keep an eye on</h2><ul>{pest_items}</ul>
  <p class="note">Untreated pests get worse fast in July–August heat.</p></section>

  <section><h2>📝 Notes</h2><ul>{note_items}</ul></section>

  <section><h2>🆘 Emergency contacts</h2>{contact_lines}</section>

  <p class="footer">Generated by Verdant · { _esc(today)} · print this page before you leave</p>
</div>
</body></html>"""
    except Exception:
        return ("<!DOCTYPE html><html><body><h1>Garden Caretaker Sheet</h1>"
                "<p>Couldn't build the sheet — the garden will have to fend "
                "for itself this time.</p></body></html>")


@router.get("/api/caretaker-sheet")
def caretaker_sheet(session: Session = Depends(get_session)) -> HTMLResponse:
    """Print-friendly HTML page for the garden-sitter."""
    # Local import avoids any router-import cycles at app startup.
    from app.caretaker import caretaker_data

    return HTMLResponse(build_caretaker_html(caretaker_data(session)))
