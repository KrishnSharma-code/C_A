"""
PDF export using fpdf2.
"""
from fpdf import FPDF
from fpdf.enums import XPos, YPos
import re
from typing import Dict, Optional
from pathlib import Path
import tempfile
import os

class DocumentPDF(FPDF):
    def __init__(self, title: str = "Documentation", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.doc_title = title
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, self.doc_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

def clean_text(text: str) -> str:
    """Remove characters that can't be encoded in latin-1."""
    # Replace common unicode with ASCII equivalents
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "--", "\u2026": "...", "\u00b7": "*",
        "\u2022": "*", "\u2192": "->", "\u2190": "<-", "\u2194": "<->",
        "\u00a0": " ", "\u00ae": "(R)", "\u00a9": "(C)", "\u2122": "(TM)",
        "\u2713": "OK", "\u2714": "OK", "\u2715": "X", "\u2716": "X",
        "\u2717": "X", "\u2718": "X", "\u25cf": "*", "\u25a0": "*",
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)

    # Remove any remaining non-latin-1 characters
    return text.encode("latin-1", errors="replace").decode("latin-1")

def markdown_to_pdf(markdown_content: str, output_path: str, title: str = "Documentation",
                    project_name: str = "", persona: str = ""):
    """Convert markdown content to a styled PDF file."""

    pdf = DocumentPDF(title=f"{project_name} - {title}" if project_name else title)
    pdf.add_page()

    # Title page
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(30, 30, 80)
    pdf.ln(20)
    pdf.cell(0, 15, clean_text(project_name or "Codebase Analysis"), new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    if persona:
        pdf.set_font("Helvetica", "", 14)
        pdf.set_text_color(80, 80, 80)
        persona_label = "Software Engineer (SDE) Documentation" if persona == "sde" else "Product Manager (PM) Documentation"
        pdf.cell(0, 10, persona_label, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(120, 120, 120)
    from datetime import datetime
    pdf.cell(0, 8, f"Generated: {datetime.now().strftime('%B %d, %Y')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    pdf.add_page()

    # Process markdown line by line
    lines = markdown_content.split("\n")
    i = 0
    in_code_block = False
    code_buffer = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Code block
        if stripped.startswith("```"):
            if in_code_block:
                # End code block
                in_code_block = False
                if code_buffer:
                    _render_code_block(pdf, "\n".join(code_buffer))
                    code_buffer = []
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_buffer.append(line)
            i += 1
            continue

        # Headers
        if stripped.startswith("#### "):
            text = clean_text(stripped[5:])
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(60, 60, 60)
            pdf.ln(3)
            pdf.multi_cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif stripped.startswith("### "):
            text = clean_text(stripped[4:])
            pdf.set_font("Helvetica", "B", 13)
            pdf.set_text_color(40, 40, 100)
            pdf.ln(5)
            pdf.multi_cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(180, 180, 220)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(2)
        elif stripped.startswith("## "):
            text = clean_text(stripped[3:])
            pdf.set_font("Helvetica", "B", 15)
            pdf.set_text_color(30, 30, 80)
            pdf.ln(8)
            pdf.multi_cell(0, 10, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(100, 100, 180)
            pdf.set_line_width(0.5)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
        elif stripped.startswith("# "):
            text = clean_text(stripped[2:])
            pdf.set_font("Helvetica", "B", 18)
            pdf.set_text_color(20, 20, 70)
            pdf.ln(10)
            pdf.multi_cell(0, 12, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(4)
        # Bullet points
        elif stripped.startswith("- ") or stripped.startswith("* "):
            text = clean_text(stripped[2:])
            # Remove markdown bold/italic markers
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'\*(.+?)\*', r'\1', text)
            text = re.sub(r'`(.+?)`', r'[\1]', text)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 50)
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(0, 6, f"  * {text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # Numbered list
        elif re.match(r'^\d+\.\s', stripped):
            text = clean_text(re.sub(r'^\d+\.\s', '', stripped))
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'`(.+?)`', r'[\1]', text)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(50, 50, 50)
            num = re.match(r'^(\d+)\.\s', stripped).group(1)
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(0, 6, f"  {num}. {text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # Horizontal rule
        elif stripped in ("---", "***", "___"):
            pdf.ln(3)
            pdf.set_draw_color(180, 180, 180)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(3)
        # Mermaid blocks (include as code with note)
        elif stripped.startswith("```mermaid") or i > 0 and in_code_block:
            pass
        # Empty line
        elif stripped == "":
            pdf.ln(3)
        # Regular paragraph
        else:
            text = clean_text(stripped)
            # Remove markdown formatting
            text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
            text = re.sub(r'\*(.+?)\*', r'\1', text)
            text = re.sub(r'`(.+?)`', r'[\1]', text)
            text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # Links
            if text:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(50, 50, 50)
                pdf.multi_cell(0, 6, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        i += 1

    pdf.output(output_path)

def _render_code_block(pdf: FPDF, code: str):
    """Render a code block with grey background."""
    pdf.ln(2)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_draw_color(200, 200, 200)

    lines = code.split("\n")
    pdf.set_font("Courier", "", 8)
    pdf.set_text_color(40, 40, 40)

    x = pdf.l_margin
    y = pdf.get_y()
    w = pdf.w - pdf.l_margin - pdf.r_margin

    for line in lines[:30]:  # Max 30 lines per block
        clean = clean_text(line)[:120]  # Max 120 chars
        pdf.set_x(x + 2)
        pdf.cell(w - 4, 5, clean, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)

    pdf.ln(2)

def export_full_documentation(
    project_name: str,
    sde_content: Optional[str],
    pm_content: Optional[str],
    diagrams: list,
    output_path: str
) -> str:
    """Export full documentation (both personas + diagrams) to PDF."""

    full_content = f"# {project_name} - Complete Documentation\n\n"

    if sde_content:
        full_content += "# Software Engineer (SDE) Documentation\n\n"
        full_content += sde_content
        full_content += "\n\n---\n\n"

    if pm_content:
        full_content += "# Product Manager (PM) Documentation\n\n"
        full_content += pm_content
        full_content += "\n\n---\n\n"

    if diagrams:
        full_content += "# Visual Diagrams\n\n"
        for diagram in diagrams:
            full_content += f"## {diagram.get('title', 'Diagram')}\n\n"
            full_content += f"{diagram.get('description', '')}\n\n"
            full_content += f"```mermaid\n{diagram.get('mermaid_code', '')}\n```\n\n"

    markdown_to_pdf(full_content, output_path, title="Complete Documentation",
                    project_name=project_name)
    return output_path
