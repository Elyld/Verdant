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
from app.models import AlbumImage, ObservationImage, ObservationLog
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
        return {
            "year": year,
            "varieties": varieties,
            "total_spent": scorecard.get("total_spent", 0.0),
            "unassigned_spent": scorecard.get("unassigned_spent", 0.0),
            "total_oz": scorecard.get("total_oz", 0.0),
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
            select(AlbumImage).where(AlbumImage.taken_at.like(f"{prefix}%"))
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


def write_story(session: Session, stats: dict) -> Optional[str]:
    """Ask the configured LLM for a warm 3-5 paragraph season story.

    Returns the story text, or None on any failure (AI off, call failed,
    empty answer). Never raises."""
    try:
        year = stats.get("year", Date.today().year)
        varieties = stats.get("varieties", [])
        if varieties:
            lines = ", ".join(
                f"{v['variety']} ({v['total_oz']} oz over {v['harvest_events']} harvests)"
                for v in varieties[:12]
            )
            harvest_note = f"Harvests this year: {lines}."
        else:
            harvest_note = "No harvests were logged this year — a quiet year in the garden."
        prompt = (
            f"You are Verdant, the warm gardening-neighbor assistant inside a gardener's "
            f"personal garden journal. Write the story of their {year} garden season as "
            f"3-5 short, warm paragraphs — a yearbook entry. Facts: {harvest_note} "
            f"Total garden spending: ${stats.get('total_spent', 0):.2f}. "
            f"Total harvest weight: {stats.get('total_oz', 0):.1f} oz. "
            f"Celebrate what grew, be honest and kind about what didn't, and end with "
            f"encouragement for next season. Plain paragraphs, no markdown tables."
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
    summary_line = (
        f"{len(varieties)} varieties · {stats.get('total_oz', 0):.1f} oz harvested · "
        f"${stats.get('total_spent', 0):.2f} spent"
    )
    story_flow.append(Paragraph(summary_line, sub_style))
    story_flow.append(PageBreak())

    # ---- Stats ----
    story_flow.append(Paragraph(f"{year} by the numbers", h1))
    if varieties:
        data = [
            [Paragraph("<b>Variety</b>", cell_b),
             Paragraph("<b>Harvests</b>", cell_b),
             Paragraph("<b>Weight</b>", cell_b),
             Paragraph("<b>Cost</b>", cell_b)]
        ]
        for v in varieties:
            data.append([
                Paragraph(v["variety"], cell),
                Paragraph(str(v["harvest_events"]), cell),
                Paragraph(f"{v['total_oz']} oz", cell),
                Paragraph(f"${v['direct_cost']:.2f}", cell),
            ])
        data.append([
            Paragraph("<b>Total</b>", cell),
            Paragraph("", cell),
            Paragraph(f"<b>{stats.get('total_oz', 0):.1f} oz</b>", cell),
            Paragraph(f"<b>${stats.get('total_spent', 0):.2f}</b>", cell),
        ])
        tbl = Table(data, colWidths=[3.0 * inch, 1.2 * inch, 1.4 * inch, 1.4 * inch])
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
        story_flow.append(Paragraph(
            "Weight in ounces · costs include per-variety expenses; "
            f"unassigned spending: ${stats.get('unassigned_spent', 0):.2f}.", body))
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
