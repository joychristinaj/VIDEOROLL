"""
Generate test fixture PDFs programmatically in pure Python (no dependencies required).
Creates fixtures/sample.pdf and fixtures/multipage.pdf.
"""
from __future__ import annotations

import sys
from pathlib import Path

FIXTURES = Path(__file__).parent


def _build_simple_pdf(pages_text: list[str]) -> bytes:
    """Build a compliant, valid multi-page or single-page PDF binary in pure Python."""
    objects = []
    
    # obj 1: Catalog
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    
    # obj 2: Pages (filled later once page object ids are known)
    # obj 3: Font
    font_id = 3
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    
    page_ids = []
    next_id = 4
    for _ in pages_text:
        page_ids.append(next_id)
        next_id += 2 # page object and content object
        
    kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_obj = f"<< /Type /Pages /Kids [ {kids_str} ] /Count {len(page_ids)} >>".encode("ascii")
    # Replace placeholder for obj 2 (index 1)
    objects.insert(1, pages_obj)
    
    # Now build Page and Content objects
    current_id = 4
    for text in pages_text:
        content_id = current_id + 1
        page_obj = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")
        objects.append(page_obj)
        
        # Build content stream with BT / ET and Tf / Td / Tj
        # Split text into lines
        lines = text.split("\n")
        stream_cmds = ["BT", "/F1 12 Tf", "50 720 Td", "16 TL"]
        for i, line in enumerate(lines):
            safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if i == 0:
                stream_cmds.append(f"({safe_line}) Tj")
            else:
                stream_cmds.append(f"T* ({safe_line}) Tj")
        stream_cmds.append("ET")
        stream_data = "\n".join(stream_cmds).encode("utf-8")
        
        content_obj = (
            f"<< /Length {len(stream_data)} >>\nstream\n".encode("ascii")
            + stream_data
            + b"\nendstream"
        )
        objects.append(content_obj)
        current_id += 2

    # Now write the full PDF with xref table
    out = bytearray()
    out.extend(b"%PDF-1.4\n")
    
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
        
    xref_offset = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
        
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def make_sample_pdf() -> None:
    text = (
        "Introduction to Artificial Intelligence\n"
        "Artificial intelligence AI is the simulation of human intelligence processes by machines.\n"
        "Machine learning is a core component that enables systems to learn from experience.\n"
        "Supervised learning trains algorithms on labeled data to classify or predict outcomes."
    )
    pdf_bytes = _build_simple_pdf([text])
    (FIXTURES / "sample.pdf").write_bytes(pdf_bytes)
    print(f"Created {FIXTURES / 'sample.pdf'}")


def make_multipage_pdf() -> None:
    page1 = (
        "Chapter 1: Machine Learning Basics\n"
        "Machine learning is a method of data analysis that automates analytical model building.\n"
        "Based on the idea that systems can learn from data, identify patterns and make decisions."
    )
    page2 = (
        "Chapter 2: Neural Networks\n"
        "Neural networks are a series of algorithms that mimic the operations of a human brain.\n"
        "They recognize underlying relationships in sets of data through a process of learning."
    )
    page3 = (
        "Chapter 3: Future of AI\n"
        "The future of artificial intelligence holds enormous promise across multiple domains.\n"
        "Ethical considerations around AI include fairness, transparency, privacy, and accountability."
    )
    pdf_bytes = _build_simple_pdf([page1, page2, page3])
    (FIXTURES / "multipage.pdf").write_bytes(pdf_bytes)
    print(f"Created {FIXTURES / 'multipage.pdf'}")


if __name__ == "__main__":
    make_sample_pdf()
    make_multipage_pdf()
    print("Fixture generation complete.")
