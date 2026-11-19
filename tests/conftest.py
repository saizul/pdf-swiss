"""PDFs and images generated on the fly with pypdf and Pillow (no reportlab, no fixtures on disk)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from pdf_swiss import draw


def make_pdf(
    path: Path,
    pages: int = 3,
    *,
    label: str = "Page",
    size: tuple[float, float] = (612, 792),
    text: bool = True,
    metadata: dict | None = None,
) -> Path:
    """Write a PDF whose page k (1-based) shows the text "<label> k"."""
    writer = PdfWriter()
    for k in range(1, pages + 1):
        page = writer.add_blank_page(width=size[0], height=size[1])
        if text:
            stamp = draw.Stamp.blank(*size)
            stamp.text(f"{label} {k}", 72, size[1] - 100, 24)
            draw.apply_stamp(page, stamp)
    if metadata:
        writer.add_metadata(metadata)
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


def page_texts(path: Path, password: str | None = None) -> list[str]:
    reader = PdfReader(str(path))
    if password is not None:
        reader.decrypt(password)
    return [p.extract_text().strip() for p in reader.pages]


@pytest.fixture
def pdf3(tmp_path) -> Path:
    return make_pdf(tmp_path / "three.pdf", 3)


@pytest.fixture
def pdf10(tmp_path) -> Path:
    return make_pdf(tmp_path / "ten.pdf", 10)


@pytest.fixture
def png_rgba(tmp_path) -> Path:
    img = Image.new("RGBA", (200, 100), (255, 0, 0, 0))
    for x in range(50, 150):
        for y in range(25, 75):
            img.putpixel((x, y), (0, 0, 255, 200))
    path = tmp_path / "logo.png"
    img.save(path)
    return path


@pytest.fixture
def jpeg(tmp_path) -> Path:
    img = Image.new("RGB", (300, 200), (10, 120, 200))
    path = tmp_path / "photo.jpg"
    img.save(path, quality=90, dpi=(150, 150))
    return path
