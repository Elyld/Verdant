"""End-of-season yearbook: stats, AI story, and a printable PDF.

Everything here degrades gracefully — no yearbook feature should ever
raise out of the request. The PDF is built with reportlab in Verdant's
sage/navy/beige palette.
"""
from __future__ import annotations

import io
from datetime import date as Date
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app import llm as llm_mod
from app import season_recap as recap_mod
from app.database import UPLOAD_DIR
from app.models import AlbumImage, Harvest, ObservationImage, ObservationLog, PestLog, Plant
from app.routers.stats import season_scorecard

# Verdant palette
SAGE = (0x6B, 0x8F, 0x71)       # #6B8F71 sage green
NAVY = (0x1E, 0x3A, 0x5F)       # #1E3A5F navy blue
BEIGE = (0xF5, 0xF0, 0xE6)      # #F5F0E6 beige
DARK_TEXT = (0x33, 0x33, 0x33)

MAX_YEARBOOK_PHOTOS = 6


def build_yearbook_stats(session: Session, year: int | None = None) -> dict:
    """Assemble the year's stats: per-variety harvest totals, total costs,
    and the season scorecard summary. Never raises — returns {} on failure."""
    try:
        if year is None:
            year = Date.today().year
        scorecard = season_scorecard(year=year, session=session)
        varieties = []
        for row in scorecard.get("varieties", []):
            varieties.append(
                {
                    "variety": row.get("variety", "?"),
                    "harvest_events": row.get("harvest_events", 0),
                    "total_qty": row.get("total_qty", 0),
                    "total_oz": row.get("total_oz", 0.0),
                    "direct_cost": row.get("direct_cost", 0.0),
                }
            )
        # A null harvest weight means "never weighed", not "0 oz" — the
        # scorecard sums those as 0.0, so recover the distinction here
        # from the harvest rows themselves.
        try:
            plants_by_id = {p.id: p for p in session.exec(select(Plant)).all()}
            weighed_varieties = set()
            for h in session.exec(
                select(Harvest).where(Harvest.date.like(f"{year}-%"))
            ).all():
                if h.weight is not None:
                    plant = plants_by_id.get(h.plant_id)
                    weighed_varieties.add(
                        plant.variety_name if plant else f"Plant {h.plant_id}"
                    )
            for v in varieties:
                v["has_weight"] = v["variety"] in weighed_varieties
        except Exception:
            for v in varieties:
                v["has_weight"] = v["total_oz"] > 0
        return {
            "year": year,
            "varieties": varieties,
            "total_spent": scorecard.get("total_spent", 0.0),
            "unassigned_spent": scorecard.get("unassigned_spent", 0.0),
            "total_oz": scorecard.get("total_oz", 0.0),
            "total_qty": sum(v.get("total_qty", 0) for v in varieties),
            "has_weight_any": any(v.get("has_weight") for v in varieties),
            "scorecard": scorecard,
            "has_data": bool(varieties or scorecard.get("total_spent", 0)),
        }
    except Exception:
        return {}


def yearbook_photos(session: Session, year: int, n: int = MAX_YEARBOOK_PHOTOS) -> list[dict]:
    """Up to ``n`` photos from the year, spread across the season.

    Pulls observation photos and Immich album photos dated to the year,
    then reuses season_recap.pick_spread. Each entry: {path: Path, date}.
    Never raises."""
    try:
        prefix = f"{year}-"
        candidates: list[dict] = []
        obs_ids = select(ObservationLog.id).where(
            ObservationLog.date.like(f"{prefix}%")
        )
        for img in session.exec(
            select(ObservationImage).where(ObservationImage.observation_id.in_(obs_ids))
        ).all():
            path = recap_mod._real_path(img.file_path)
            if path:
                candidates.append({"file_path": img.file_path, "date": None, "path": path})
        for img in session.exec(
            select(AlbumImage).where(
                AlbumImage.taken_at.like(f"{prefix}%"),
                # AI-generated images are not garden records.
                AlbumImage.is_generated.is_(False),
            )
        ).all():
            path = recap_mod._real_path(img.file_path)
            if path:
                candidates.append(
                    {
                        "file_path": img.file_path,
                        "date": recap_mod._parse_day(img.taken_at),
                        "path": path,
                    }
                )
        # Observation photos carry the observation's date for spreading.
        obs_day = {}
        for obs in session.exec(
            select(ObservationLog).where(ObservationLog.date.like(f"{prefix}%"))
        ).all():
            for img in obs.images or []:
                path = recap_mod._real_path(img.file_path)
                if path:
                    obs_day[path] = recap_mod._parse_day(obs.date)
        for c in candidates:
            if c["date"] is None and c["path"] in obs_day:
                c["date"] = obs_day[c["path"]]
        candidates.sort(key=lambda c: (c["date"] is None, c["date"] or Date.min,
                                       c["file_path"]))
        picked = recap_mod.pick_spread(candidates, n=n)
        return [{"path": c["path"], "date": c["date"]} for c in picked]
    except Exception:
        return []


MAX_CONTEXT_OBSERVATIONS = 80
MAX_CONTEXT_PLANTS = 100


def _weight_cell(variety: dict) -> str:
    """One variety's Weight cell: never render a missing weight as 0 oz."""
    if not variety.get("harvest_events"):
        return "—"
    if variety.get("has_weight"):
        return f"{variety.get('total_oz', 0)} oz"
    return "no weights recorded"


def _summary_line(stats: dict) -> str:
    """Title-page summary: counts only varieties with harvest entries,
    and never prints a 0 oz total for unweighed harvests."""
    varieties = stats.get("varieties", [])
    with_harvests = [v for v in varieties if v.get("harvest_events")]
    total_events = sum(v.get("harvest_events", 0) for v in varieties)
    if not total_events:
        weight_text = "no harvests logged"
    elif stats.get("has_weight_any"):
        weight_text = f"{stats.get('total_oz', 0):.1f} oz harvested"
    else:
        weight_text = "no weights recorded"
    total_qty = stats.get(
        "total_qty", sum(v.get("total_qty", 0) for v in varieties)
    )
    return (
        f"{len(with_harvests)} varieties with harvest entries · "
        f"{total_qty} items picked · {weight_text} · "
        f"${stats.get('total_spent', 0):.2f} spent"
    )


def build_story_context(session: Session, year: int, stats: dict) -> str:
    """Structured season records for the story prompt. Never raises —
    returns "" when the records can't be gathered."""
    try:
        prefix = f"{year}-"
        plants = session.exec(select(Plant)).all()
        by_id = {p.id: p for p in plants}
        sections: list[str] = []

        # Plant status + notes carry the only honest death causes.
        plant_lines = []
        for p in plants[:MAX_CONTEXT_PLANTS]:
            note = (p.notes or "").strip()
            plant_lines.append(
                f"- {p.variety_name} ({p.status})" + (f": {note}" if note else "")
            )
        if plant_lines:
            sections.append("Plants:\n" + "\n".join(plant_lines))
            if len(plants) > MAX_CONTEXT_PLANTS:
                sections.append(
                    f"(+{len(plants) - MAX_CONTEXT_PLANTS} more plants not listed)"
                )

        obs = session.exec(
            select(ObservationLog).where(ObservationLog.date.like(f"{prefix}%"))
        ).all()
        obs.sort(key=lambda o: (o.date or "", o.id or 0))
        obs_lines = []
        for o in obs[:MAX_CONTEXT_OBSERVATIONS]:
            if o.plant_id in by_id:
                who = by_id[o.plant_id].variety_name
            else:
                who = o.plant_name or "unknown plant"
            bits = [o.date, who]
            if (o.notes or "").strip():
                bits.append(o.notes.strip())
            if (o.pest_sightings or "").strip():
                bits.append(f"pests seen: {o.pest_sightings.strip()}")
            if (o.weather_summary or "").strip():
                bits.append(f"weather: {o.weather_summary.strip()}")
            obs_lines.append("- " + " — ".join(bits))
        if obs_lines:
            sections.append("Observations:\n" + "\n".join(obs_lines))
            if len(obs) > MAX_CONTEXT_OBSERVATIONS:
                sections.append(
                    f"(+{len(obs) - MAX_CONTEXT_OBSERVATIONS} more observations not listed)"
                )

        pests = session.exec(
            select(PestLog).where(PestLog.date.like(f"{prefix}%"))
        ).all()
        pests.sort(key=lambda p: (p.date or "", p.id or 0))
        pest_lines = []
        for p in pests:
            if p.plant_id in by_id:
                who = by_id[p.plant_id].variety_name
            elif p.plant_id:
                who = f"plant {p.plant_id}"
            else:
                who = "garden-wide"
            line = f"- {p.date} {p.pest_name} on {who}"
            if (p.treatment or "").strip():
                line += f" (treated: {p.treatment.strip()})"
            pest_lines.append(line)
        if pest_lines:
            sections.append("Pest log:\n" + "\n".join(pest_lines))

        harvest_lines = []
        for v in stats.get("varieties", []):
            if not v.get("harvest_events"):
                continue
            if v.get("has_weight"):
                harvest_lines.append(
                    f"- {v['variety']}: {v['harvest_events']} harvests, "
                    f"{v['total_qty']} items picked, {v['total_oz']} oz weighed"
                )
            else:
                harvest_lines.append(
                    f"- {v['variety']}: {v['harvest_events']} harvests, "
                    f"{v['total_qty']} items picked, no weights recorded"
                )
        if harvest_lines:
            sections.append("Harvests:\n" + "\n".join(harvest_lines))
        sections.append(
            f"Spending: ${stats.get('total_spent', 0):.2f} total, "
            f"${stats.get('unassigned_spent', 0):.2f} unassigned to any plant."
        )
        return "\n\n".join(sections)
    except Exception:
        return ""


def write_story(session: Session, stats: dict) -> Optional[str]:
    """Ask the configured LLM for a warm 3-5 paragraph season story.

    The prompt is built from the season's actual records — plants (with
    their status and notes), observations, pest log, harvests, spending —
    plus an explicit grounding rule, so the story summarises the journal
    instead of inventing pests, weather, or causes of death. Returns the
    story text, or None on any failure (AI off, call failed, empty
    answer). Never raises."""
    try:
        year = stats.get("year", Date.today().year)
        context = build_story_context(session, year, stats) or (
            "No season records were available."
        )
        prompt = (
            f"You are Verdant, the warm gardening-neighbor assistant inside a gardener's "
            f"personal garden journal. Write the story of their {year} garden season as "
            f"3-5 short, warm paragraphs — a yearbook entry.\n\n"
            f"Season records:\n{context}\n\n"
            f"Grounding rules — these outrank warmth: state only what the records above "
            f"support. Where a value is absent (for example, a harvest with no recorded "
            f"weight), say so plainly — never present a missing value as zero. Never "
            f"invent a pest, a weather event, or a cause of death. A plant's cause of "
            f"death comes only from that plant's own notes; if the notes are empty, say "
            f"the cause is unknown. Celebrate what grew, be honest and kind about what "
            f"didn't, and end with encouragement for next season. Plain paragraphs, no "
            f"markdown tables."
        )
        text = llm_mod.chat(session, [{"role": "user", "content": prompt}], timeout=120)
        text = (text or "").strip()
        return text or None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# PDF rendering (reportlab)
# --------------------------------------------------------------------------- #
def _rgb(triple) -> "colors.Color":
    from reportlab.lib import colors

    r, g, b = triple
    return colors.Color(r / 255.0, g / 255.0, b / 255.0)


def render_pdf(stats: dict, story: Optional[str], photos: list[dict]) -> bytes:
    """Render the yearbook as PDF bytes. Graceful on empty years ('quiet year'
    copy). Never raises — returns a minimal error PDF on failure."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    year = stats.get("year", Date.today().year)
    buf = io.BytesIO()

    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(_rgb(BEIGE))
        canvas.rect(0, 0, letter[0], 28, fill=1, stroke=0)
        canvas.setFillColor(_rgb(NAVY))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(inch, 12, f"Verdant Garden Journal — {year} Yearbook")
        canvas.drawRightString(letter[0] - inch, 12, f"page {doc.page}")
        canvas.restoreState()

    def cover_footer(canvas, doc):
        pass

    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=inch, rightMargin=inch, topMargin=0.9 * inch, bottomMargin=0.7 * inch,
        title=f"Verdant Yearbook {year}",
    )

    navy = _rgb(NAVY)
    sage = _rgb(SAGE)
    beige = _rgb(BEIGE)
    ink = _rgb(DARK_TEXT)

    title_style = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=30,
                                 textColor=navy, alignment=1, spaceAfter=12)
    sub_style = ParagraphStyle("sub", fontName="Helvetica", fontSize=13,
                               textColor=ink, alignment=1, spaceAfter=6)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=18,
                        textColor=navy, spaceBefore=18, spaceAfter=10)
    h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=14,
                        textColor=colors.Color(sage.red * 0.7, sage.green * 0.7, sage.blue * 0.7),
                        spaceBefore=12, spaceAfter=8)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=11,
                          textColor=ink, leading=16, spaceAfter=10)
    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=9,
                          textColor=ink, leading=12)
    cell_b = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold",
                            textColor=colors.white)

    story_flow: list = []

    # ---- Title page ----
    story_flow.append(Spacer(1, 2.2 * inch))
    story_flow.append(Paragraph("📕", ParagraphStyle("emoji", fontSize=48, alignment=1)))
    story_flow.append(Paragraph(f"The {year} Garden Yearbook", title_style))
    story_flow.append(Paragraph("Verdant Garden Journal", sub_style))
    varieties = stats.get("varieties", [])
    story_flow.append(Paragraph(_summary_line(stats), sub_style))
    story_flow.append(PageBreak())

    # ---- Stats ----
    story_flow.append(Paragraph(f"{year} by the numbers", h1))
    if varieties:
        data = [
            [Paragraph("<b>Variety</b>", cell_b),
             Paragraph("<b>Harvests</b>", cell_b),
             Paragraph("<b>Picked</b>", cell_b),
             Paragraph("<b>Weight</b>", cell_b),
             Paragraph("<b>Cost</b>", cell_b)]
        ]
        for v in varieties:
            data.append([
                Paragraph(v["variety"], cell),
                Paragraph(str(v["harvest_events"]), cell),
                Paragraph(str(v.get("total_qty", 0)), cell),
                Paragraph(_weight_cell(v), cell),
                Paragraph(f"${v['direct_cost']:.2f}", cell),
            ])
        total_events = sum(v.get("harvest_events", 0) for v in varieties)
        if not total_events:
            total_weight = "—"
        elif stats.get("has_weight_any"):
            total_weight = f"{stats.get('total_oz', 0):.1f} oz"
        else:
            total_weight = "no weights recorded"
        data.append([
            Paragraph("<b>Total</b>", cell),
            Paragraph("", cell),
            Paragraph(f"<b>{stats.get('total_qty', sum(v.get('total_qty', 0) for v in varieties))}</b>", cell),
            Paragraph(f"<b>{total_weight}</b>", cell),
            Paragraph(f"<b>${stats.get('total_spent', 0):.2f}</b>", cell),
        ])
        tbl = Table(data, colWidths=[2.2 * inch, 0.9 * inch, 0.9 * inch, 1.3 * inch, 1.2 * inch])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), beige),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, beige]),
            ("GRID", (0, 0), (-1, -1), 0.5, sage),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story_flow.append(tbl)
        footnote = (
            "Weight in ounces · costs include per-variety expenses; "
            f"unassigned spending: ${stats.get('unassigned_spent', 0):.2f}."
        )
        if any(v.get("harvest_events") and not v.get("has_weight") for v in varieties):
            footnote += (
                " 'No weights recorded' means the harvest was logged without a "
                "weight, not that nothing was picked."
            )
        story_flow.append(Paragraph(footnote, body))
    else:
        story_flow.append(Paragraph(
            "A quiet year. No harvests or costs were logged for this season — "
            "the garden journal was resting, and that's allowed. "
            "Next season's yearbook will have stories to tell. 🌱", body))
    story_flow.append(PageBreak())

    # ---- Story ----
    story_flow.append(Paragraph("The season's story", h1))
    if story:
        for para in story.split("\n"):
            para = para.strip()
            if para:
                story_flow.append(Paragraph(para, body))
    else:
        story_flow.append(Paragraph(
            "The AI storyteller wasn't available when this yearbook was made "
            "(AI is off or unreachable — check Settings → AI). "
            "Your numbers are all here; the story is yours to remember. 💚", body))

    # ---- Photos ----
    if photos:
        story_flow.append(PageBreak())
        story_flow.append(Paragraph("Season photos", h1))
        for p in photos:
            path = p.get("path")
            if not path or not isinstance(path, Path) or not path.is_file():
                continue
            try:
                from PIL import Image as PilImage

                with PilImage.open(path) as pim:
                    w, h = pim.convert("RGB").size
                scale = min((6.0 * inch) / w, (4.5 * inch) / h, 1.0)
                img = Image(str(path), width=w * scale, height=h * scale)
                story_flow.append(img)
                day = p.get("date")
                story_flow.append(Paragraph(
                    day.isoformat() if isinstance(day, Date) else "from the season",
                    ParagraphStyle("cap", parent=body, alignment=1, fontSize=9,
                                   textColor=sage)))
                story_flow.append(Spacer(1, 0.25 * inch))
            except Exception:
                continue

    try:
        doc.build(story_flow, onFirstPage=cover_footer, onLaterPages=header_footer)
    except Exception:
        # Last-resort minimal PDF so the request never 500s.
        fallback = io.BytesIO()
        fdoc = SimpleDocTemplate(fallback, pagesize=letter)
        fdoc.build([Paragraph(f"Verdant {year} yearbook — the full yearbook "
                              "couldn't be rendered.", body)])
        return fallback.getvalue()
    return buf.getvalue()
