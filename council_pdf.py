#!/usr/bin/env python3
"""
council_pdf.py — Renders LLM Council JSON output as a styled PDF report.

Usage:
  # Pipe from council.py
  python3 council.py "Your question" | python3 council_pdf.py

  # Or from a saved JSON file
  python3 council_pdf.py council_output.json

  # Specify output path
  python3 council_pdf.py council_output.json --output my_report.pdf
"""

import argparse
import json
import re
import sys
import xml.sax.saxutils
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── XML Escaping ──────────────────────────────────────────────────────────────

def xml_escape(text: str) -> str:
    """Escape XML special characters for ReportLab Paragraph rendering."""
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    return xml.sax.saxutils.escape(text, {"'": "&apos;", '"': "&quot;"})


# ── Input Validation ──────────────────────────────────────────────────────────

def validate_input(data: dict) -> dict:
    """Validate and coerce council JSON input. Returns cleaned data."""
    if not isinstance(data, dict):
        print("Error: Input must be a JSON object.", file=sys.stderr)
        sys.exit(1)

    cleaned = {}

    # String fields: coerce to str with defaults
    _STR_FIELDS = {
        "question":        "Unknown question",
        "final_answer":    "No answer provided.",
        "confidence":      "unknown",
        "confidence_note": "",
        "chairman":        "Unknown",
    }
    for key, default in _STR_FIELDS.items():
        cleaned[key] = str(data.get(key, default))

    # List fields: pass through if list, otherwise default to []
    for key in ("consensus_points", "disagreements", "council", "individual_answers"):
        val = data.get(key, [])
        cleaned[key] = val if isinstance(val, list) else []

    # Pass through metadata fields
    cleaned["stage2_skipped"] = data.get("stage2_skipped", False)
    cleaned["run_started_at"] = data.get("run_started_at", "")
    cleaned["run_duration_seconds"] = data.get("run_duration_seconds", "")
    cleaned["errors"] = data.get("errors", [])

    return cleaned


# ── Filename Slug ─────────────────────────────────────────────────────────────

def slugify(text: str, max_len: int = 40) -> str:
    """Convert text to a filename-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    if len(slug) > max_len:
        slug = slug[:max_len].rstrip("_")
    return slug or "council"


# ── Color Palette ──────────────────────────────────────────────────────────────

NAVY       = colors.HexColor("#0F1F3D")
GOLD       = colors.HexColor("#C9962A")
SLATE      = colors.HexColor("#4A5568")
LIGHT_GRAY = colors.HexColor("#F7F8FA")
MID_GRAY   = colors.HexColor("#E2E8F0")
RED_SOFT   = colors.HexColor("#C53030")
GREEN_SOFT = colors.HexColor("#276749")
WHITE      = colors.white

CONFIDENCE_COLORS = {
    "high":    GREEN_SOFT,
    "medium":  colors.HexColor("#B7791F"),
    "low":     RED_SOFT,
    "unknown": SLATE,
}

# ── Styles ─────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()

    styles = {
        "cover_title": ParagraphStyle(
            "cover_title",
            fontName="Helvetica-Bold",
            fontSize=26,
            textColor=WHITE,
            leading=32,
            spaceAfter=8,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            fontName="Helvetica",
            fontSize=13,
            textColor=colors.HexColor("#CBD5E0"),
            leading=18,
            spaceAfter=4,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            fontName="Helvetica-Bold",
            fontSize=14,
            textColor=NAVY,
            spaceBefore=18,
            spaceAfter=6,
            leading=18,
        ),
        "sub_heading": ParagraphStyle(
            "sub_heading",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=SLATE,
            spaceBefore=10,
            spaceAfter=4,
            leading=15,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            textColor=colors.HexColor("#2D3748"),
            leading=15,
            spaceAfter=6,
        ),
        "body_small": ParagraphStyle(
            "body_small",
            fontName="Helvetica",
            fontSize=9,
            textColor=SLATE,
            leading=13,
            spaceAfter=4,
        ),
        "label": ParagraphStyle(
            "label",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=SLATE,
            leading=12,
        ),
        "question_text": ParagraphStyle(
            "question_text",
            fontName="Helvetica-Oblique",
            fontSize=12,
            textColor=NAVY,
            leading=17,
            spaceAfter=4,
            leftIndent=12,
        ),
        "consensus_item": ParagraphStyle(
            "consensus_item",
            fontName="Helvetica",
            fontSize=10,
            textColor=GREEN_SOFT,
            leading=14,
            spaceAfter=3,
            leftIndent=14,
        ),
        "verdict": ParagraphStyle(
            "verdict",
            fontName="Helvetica-Oblique",
            fontSize=10,
            textColor=NAVY,
            leading=14,
            leftIndent=10,
            rightIndent=10,
            spaceAfter=4,
        ),
        "badge": ParagraphStyle(
            "badge",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=WHITE,
            leading=12,
        ),
        "dhead": ParagraphStyle(
            "dhead",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=WHITE,
            leading=14,
        ),
        "ch_label": ParagraphStyle(
            "ch_label",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=GOLD,
            leading=12,
        ),
        "ch_val": ParagraphStyle(
            "ch_val",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=NAVY,
            leading=13,
        ),
    }
    return styles


# ── Page template with header/footer ──────────────────────────────────────────

def make_page_decorator(title: str, generated_at: str):
    def decorator(canvas, doc):
        canvas.saveState()
        w, h = letter

        # Header bar
        canvas.setFillColor(NAVY)
        canvas.rect(0, h - 36, w, 36, fill=1, stroke=0)
        canvas.setFillColor(GOLD)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(0.5 * inch, h - 23, "LLM COUNCIL REPORT")
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica", 9)
        short = title[:50] + ("..." if len(title) > 50 else "")
        canvas.drawRightString(w - 0.5 * inch, h - 23, short)

        # Footer
        canvas.setFillColor(MID_GRAY)
        canvas.rect(0, 0, w, 28, fill=1, stroke=0)
        canvas.setFillColor(SLATE)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.5 * inch, 10, f"Generated {generated_at}")
        canvas.drawCentredString(w / 2, 10, "Powered by OpenRouter")
        canvas.drawRightString(w - 0.5 * inch, 10, f"Page {doc.page}")

        canvas.restoreState()

    return decorator


# ── Section builders ───────────────────────────────────────────────────────────

def section_divider(story, styles, label: str):
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.5, color=GOLD, spaceAfter=4))
    story.append(Paragraph(label.upper(), styles["section_heading"]))


def render_paragraphs(story, text: str, style, spacing: int = 4):
    """Split text on double-newlines and render each as a Paragraph + Spacer."""
    for para in text.split("\n\n"):
        para = para.strip()
        if para:
            story.append(Paragraph(para, style))
            story.append(Spacer(1, spacing))


def confidence_badge(confidence: str, note: str, styles) -> Table:
    color = CONFIDENCE_COLORS.get(confidence.lower(), SLATE)
    badge_text = f"<font color='white'><b> {xml_escape(confidence.upper())} CONFIDENCE </b></font>"
    badge = Paragraph(badge_text, styles["badge"])
    note_para = Paragraph(xml_escape(note), styles["body_small"])

    tbl = Table([[badge, note_para]], colWidths=[1.5 * inch, 5.2 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), color),
        ("BACKGROUND", (1, 0), (1, 0), LIGHT_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return tbl


def disagreement_card(idx: int, item: dict, styles) -> Table:
    topic     = xml_escape(str(item.get("topic", f"Disagreement {idx}")))
    summary   = xml_escape(str(item.get("summary", "")))
    verdict   = xml_escape(str(item.get("chairman_verdict", "")))

    header = Paragraph(f"<b>{idx}. {topic}</b>", styles["dhead"])
    summary_para = Paragraph(summary, styles["body"])
    verdict_label = Paragraph("<b>Chairman's Verdict:</b>", styles["label"])
    verdict_para  = Paragraph(verdict, styles["verdict"])

    inner = Table(
        [[summary_para], [verdict_label], [verdict_para]],
        colWidths=[6.5 * inch],
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, 2), (-1, 2), 0.5, MID_GRAY),
    ]))

    outer = Table([[header], [inner]], colWidths=[6.5 * inch])
    outer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("LEFTPADDING", (0, 0), (-1, 0), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("LEFTPADDING", (0, 1), (-1, -1), 0),
        ("RIGHTPADDING", (0, 1), (-1, -1), 0),
        ("TOPPADDING", (0, 1), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 0),
        ("BOX", (0, 0), (-1, -1), 1, MID_GRAY),
    ]))
    return outer


def council_table(council: list, chairman: str, styles) -> Table:
    rows = [
        [
            Paragraph("<b>Role</b>", styles["label"]),
            Paragraph("<b>Model</b>", styles["label"]),
        ]
    ]
    for name in council:
        rows.append([
            Paragraph("Councilor", styles["body_small"]),
            Paragraph(xml_escape(str(name)), styles["body"]),
        ])
    rows.append([
        Paragraph("<b>Chairman</b>", styles["ch_label"]),
        Paragraph(xml_escape(str(chairman)), styles["ch_val"]),
    ])

    tbl = Table(rows, colWidths=[1.5 * inch, 5.2 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("BACKGROUND", (0, 1), (-1, -2), LIGHT_GRAY),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#FFFBEB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [WHITE, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


# ── Main builder ───────────────────────────────────────────────────────────────

def build_pdf(data: dict, output_path: str):
    data = validate_input(data)
    styles = build_styles()
    now    = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    question = data["question"]

    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.65 * inch,
    )

    story = []

    # ── Cover block ────────────────────────────────────────────────────────────
    cover = Table(
        [[Paragraph("LLM COUNCIL", styles["cover_title"])],
         [Paragraph("Deliberation Report", styles["cover_sub"])],
         [Spacer(1, 6)],
         [Paragraph(f"Generated: {now}", styles["cover_sub"])]],
        colWidths=[6.7 * inch],
    )
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 20),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 20),
    ]))
    story.append(cover)
    story.append(Spacer(1, 14))

    # ── Question ───────────────────────────────────────────────────────────────
    section_divider(story, styles, "Question")
    q_box = Table(
        [[Paragraph(xml_escape(question), styles["question_text"])]],
        colWidths=[6.7 * inch],
    )
    q_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EBF4FF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (0, 0), (-1, -1), 3, GOLD),
    ]))
    story.append(q_box)
    story.append(Spacer(1, 10))

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence = data["confidence"]
    conf_note  = data["confidence_note"]
    story.append(confidence_badge(confidence, conf_note, styles))
    story.append(Spacer(1, 14))

    # ── Final Answer ───────────────────────────────────────────────────────────
    section_divider(story, styles, "Chairman's Final Answer")
    render_paragraphs(story, xml_escape(data["final_answer"]), styles["body"])

    story.append(Spacer(1, 10))

    # ── Consensus Points ──────────────────────────────────────────────────────
    consensus = data["consensus_points"]
    if consensus:
        section_divider(story, styles, "Where All Models Agreed")
        for point in consensus:
            story.append(Paragraph(f"- {xml_escape(str(point))}", styles["consensus_item"]))
        story.append(Spacer(1, 10))

    # ── Disagreements ─────────────────────────────────────────────────────────
    disagreements = data["disagreements"]
    if disagreements:
        section_divider(story, styles, "Where They Disagreed")
        story.append(Paragraph(
            "These are the significant points of divergence across the council, with the Chairman's verdict on each.",
            styles["body_small"],
        ))
        story.append(Spacer(1, 8))
        for i, item in enumerate(disagreements, 1):
            if isinstance(item, dict):
                story.append(disagreement_card(i, item, styles))
                story.append(Spacer(1, 8))

    # ── Council Composition ───────────────────────────────────────────────────
    section_divider(story, styles, "Council Composition")
    council   = data["council"]
    chairman  = data["chairman"]
    story.append(council_table(council, chairman, styles))
    story.append(Spacer(1, 10))

    # ── Individual Answers (appendix) ─────────────────────────────────────────
    individual = data["individual_answers"]
    if individual:
        story.append(PageBreak())
        section_divider(story, styles, "Appendix — Individual Model Answers")
        story.append(Paragraph(
            "Raw answers from each councilor before cross-review and synthesis.",
            styles["body_small"],
        ))
        story.append(Spacer(1, 10))
        for entry in individual:
            if not isinstance(entry, dict):
                continue
            model  = xml_escape(str(entry.get("model", "Unknown")))
            answer = xml_escape(str(entry.get("answer", "")))
            story.append(Paragraph(model, styles["sub_heading"]))
            story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY, spaceAfter=6))
            render_paragraphs(story, answer, styles["body"], spacing=3)
            story.append(Spacer(1, 12))

    # ── Build ──────────────────────────────────────────────────────────────────
    short_q = question[:50] + ("..." if len(question) > 50 else "")
    doc.build(
        story,
        onFirstPage=make_page_decorator(short_q, now),
        onLaterPages=make_page_decorator(short_q, now),
    )
    print(f"PDF saved: {output_path}", file=sys.stderr)
    return output_path


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Render LLM Council JSON as a PDF report")
    parser.add_argument("input", nargs="?", help="Path to council JSON file (or pipe via stdin)")
    parser.add_argument("--output", "-o", default=None, help="Output PDF path")
    args = parser.parse_args()

    # Load JSON
    try:
        if args.input:
            with open(args.input) as f:
                data = json.load(f)
        else:
            raw = sys.stdin.read()
            if not raw.strip():
                print("Error: No input provided. Pipe JSON or pass a file path.", file=sys.stderr)
                sys.exit(1)
            data = json.loads(raw)
    except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
        print(f"Error loading input: {e}", file=sys.stderr)
        sys.exit(1)

    # Output path
    if args.output:
        out = args.output
    else:
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = slugify(data.get("question", ""))
        out  = f"council_{ts}_{slug}.pdf"

    build_pdf(data, out)
    print(out)  # Print path to stdout so callers can capture it


if __name__ == "__main__":
    main()
