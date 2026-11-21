"""PDF operations. Every function takes paths or readers and returns or saves a writer.

The CLI is a thin layer over this module, so everything here is usable as a library::

    from pdf_swiss import ops
    ops.save(ops.merge(["a.pdf", "b.pdf"]), "out.pdf")
"""

from __future__ import annotations

import io
import math
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject, NumberObject

from pdf_swiss import draw
from pdf_swiss.pages import PageSpecError, chunks, parse_groups, parse_pages

PAPER = {
    "a3": (841.89, 1190.55),
    "a4": (595.28, 841.89),
    "a5": (419.53, 595.28),
    "letter": (612.0, 792.0),
    "legal": (612.0, 1008.0),
    "tabloid": (792.0, 1224.0),
}

POSITIONS = (
    "top-left",
    "top-center",
    "top-right",
    "center",
    "bottom-left",
    "bottom-center",
    "bottom-right",
)

METADATA_FIELDS = {
    "title": "/Title",
    "author": "/Author",
    "subject": "/Subject",
    "keywords": "/Keywords",
    "creator": "/Creator",
    "producer": "/Producer",
}


class PdfSwissError(Exception):
    """A user-facing error (bad input file, wrong password, invalid option)."""


# --------------------------------------------------------------------------- input / output


def open_pdf(path: str | os.PathLike, password: str | None = None) -> PdfReader:
    """Open a PDF, decrypting it with ``password`` (or an empty user password)."""
    try:
        reader = PdfReader(str(path))
    except FileNotFoundError as exc:
        raise PdfSwissError(f"{path}: file not found") from exc
    except (PdfReadError, ValueError, OSError) as exc:
        raise PdfSwissError(f"{path}: not a readable PDF ({exc})") from exc
    if reader.is_encrypted:
        try:
            ok = reader.decrypt(password or "")
        except Exception as exc:  # cryptography missing or unsupported handler
            raise PdfSwissError(f"{path}: cannot decrypt ({exc})") from exc
        if not ok:
            hint = "wrong password" if password else "the file is encrypted; pass --password"
            raise PdfSwissError(f"{path}: {hint}")
    return reader


def save(writer: PdfWriter, output: str | os.PathLike) -> Path:
    """Write atomically (temp file + rename), so ``-o`` may point at an input file."""
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pdf-swiss-", suffix=".pdf", dir=out.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            writer.write(fh)
        os.replace(tmp, out)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return out


def _clone(reader: PdfReader) -> PdfWriter:
    return PdfWriter(clone_from=reader)


def _pages(reader: PdfReader, spec: str | None) -> list[int]:
    try:
        return parse_pages(spec, len(reader.pages))
    except PageSpecError as exc:
        raise PdfSwissError(str(exc)) from exc


def _subset(reader: PdfReader, indexes: Sequence[int]) -> PdfWriter:
    writer = PdfWriter()
    for i in indexes:
        writer.add_page(reader.pages[i])
    _copy_info(reader, writer)
    return writer


def _copy_info(reader: PdfReader, writer: PdfWriter) -> None:
    meta = reader.metadata
    if meta:
        writer.add_metadata({k: v for k, v in meta.items() if isinstance(k, str)})


# --------------------------------------------------------------------------- merge / split / select

_SPEC_SUFFIX = re.compile(r"^(?P<path>.+?):(?P<spec>[0-9a-z,\- ]+)$", re.IGNORECASE)


def split_input(arg: str) -> tuple[str, str | None]:
    """``file.pdf:1-3`` -> ``("file.pdf", "1-3")`` unless ``arg`` itself is an existing file."""
    if os.path.exists(arg):
        return arg, None
    m = _SPEC_SUFFIX.match(arg)
    if m and os.path.exists(m["path"]):
        return m["path"], m["spec"]
    return arg, None


def merge(inputs: Sequence[str], password: str | None = None, bookmarks: bool = False) -> PdfWriter:
    """Concatenate PDFs. Each input may carry a page spec: ``part.pdf:2-5``."""
    if not inputs:
        raise PdfSwissError("nothing to merge")
    writer = PdfWriter()
    for arg in inputs:
        path, spec = split_input(arg)
        reader = open_pdf(path, password)
        indexes = _pages(reader, spec)
        first = len(writer.pages)
        for i in indexes:
            writer.add_page(reader.pages[i])
        if bookmarks:
            writer.add_outline_item(title=Path(path).stem, page_number=first)
    return writer


def select(reader: PdfReader, spec: str) -> PdfWriter:
    """Keep the given pages in the given order (extract, reorder, duplicate)."""
    return _subset(reader, _pages(reader, spec))


def delete(reader: PdfReader, spec: str) -> PdfWriter:
    drop = set(_pages(reader, spec))
    keep = [i for i in range(len(reader.pages)) if i not in drop]
    if not keep:
        raise PdfSwissError("refusing to delete every page")
    return _subset(reader, keep)


def reverse(reader: PdfReader) -> PdfWriter:
    return _subset(reader, list(range(len(reader.pages) - 1, -1, -1)))


def split(
    reader: PdfReader,
    *,
    ranges: str | None = None,
    every: int | None = None,
) -> list[tuple[list[int], PdfWriter]]:
    """Split into parts: by explicit ranges (``1-3,4-9,10-``) or every N pages (default 1)."""
    total = len(reader.pages)
    try:
        groups = parse_groups(ranges, total) if ranges else chunks(total, every or 1)
    except PageSpecError as exc:
        raise PdfSwissError(str(exc)) from exc
    return [(g, _subset(reader, g)) for g in groups]


def split_names(stem: str, groups: Sequence[Sequence[int]], pattern: str) -> list[str]:
    """File names for split parts. Placeholders: {stem} {n} {start} {end} {count}."""
    width = len(str(len(groups)))
    names = []
    for n, g in enumerate(groups, 1):
        try:
            names.append(pattern.format(stem=stem, n=str(n).zfill(width), start=g[0] + 1, end=g[-1] + 1, count=len(g)))
        except (KeyError, IndexError, ValueError) as exc:
            raise PdfSwissError(f"invalid --pattern {pattern!r}: {exc}") from exc
    for name in names:
        if "/" in name or "\\" in name or name in ("", ".", ".."):
            raise PdfSwissError(f"--pattern must produce plain file names, got {name!r}; use --output-dir for folders")
    if len(set(names)) != len(names):
        raise PdfSwissError("--pattern produces duplicate file names; include {n} or {start}")
    return names


# --------------------------------------------------------------------------- blank pages


def insert_blank(
    reader: PdfReader,
    *,
    after: str | None = None,
    before: str | None = None,
    every: int | None = None,
    pad_to: int | None = None,
    count: int = 1,
) -> PdfWriter:
    """Insert blank pages: after or before the pages of a spec, after every N pages (not after
    the last page), and/or at the end until the page count is a multiple of ``pad_to``.

    Each blank page gets ``count`` copies and the size and rotation of its neighbour: the
    page before it, or the first page when it is inserted at the very start.
    """
    if after is None and before is None and every is None and pad_to is None:
        raise PdfSwissError("give --after, --before, --every or --pad-to")
    if every is not None and (after is not None or before is not None):
        raise PdfSwissError("--every cannot be combined with --after or --before")
    for name, value in (("--every", every), ("--pad-to", pad_to), ("--count", count)):
        if value is not None and value < 1:
            raise PdfSwissError(f"{name} must be at least 1")
    total = len(reader.pages)
    blanks_after: Counter[int] = Counter()  # page index -> blanks after it; -1 means before the first page
    for i in _pages(reader, after) if after is not None else ():
        blanks_after[i] += count
    for i in _pages(reader, before) if before is not None else ():
        blanks_after[i - 1] += count
    if every is not None:
        for i in range(every - 1, total - 1, every):
            blanks_after[i] += count

    writer = PdfWriter()

    def add_blanks(n: int, like) -> None:
        width, height = float(like.mediabox.width), float(like.mediabox.height)
        for _ in range(n):
            blank = writer.add_blank_page(width=width, height=height)
            if like.rotation:
                blank[NameObject("/Rotate")] = NumberObject(like.rotation % 360)

    add_blanks(blanks_after[-1], reader.pages[0])
    for i, page in enumerate(reader.pages):
        writer.add_page(page)
        add_blanks(blanks_after[i], page)
    if pad_to is not None and len(writer.pages) % pad_to:
        add_blanks(pad_to - len(writer.pages) % pad_to, reader.pages[-1])
    _copy_info(reader, writer)
    return writer


# --------------------------------------------------------------------------- rotate


def rotate(reader: PdfReader, angle: int, spec: str | None = None) -> PdfWriter:
    if angle % 90:
        raise PdfSwissError("rotation must be a multiple of 90 degrees")
    writer = _clone(reader)
    for i in _pages(reader, spec):
        page = writer.pages[i]
        page[NameObject("/Rotate")] = NumberObject((page.rotation + angle) % 360)
    return writer


# --------------------------------------------------------------------------- stamping


def _anchor(position: str, left: float, bottom: float, w: float, h: float, margin: float) -> tuple[float, float, str]:
    if position not in POSITIONS:
        raise PdfSwissError(f"invalid position {position!r}; choose from {', '.join(POSITIONS)}")
    if position == "center":
        return left + w / 2, bottom + h / 2, "center"
    vert, horiz = position.split("-")
    y = bottom + h - margin if vert == "top" else bottom + margin
    x = {"left": left + margin, "center": left + w / 2, "right": left + w - margin}[horiz]
    return x, y, horiz


def watermark_text(
    reader: PdfReader,
    text: str,
    *,
    spec: str | None = None,
    size: float | None = None,
    angle: float | None = None,
    color: str = "#808080",
    opacity: float = 0.3,
    position: str = "center",
    font: str = "helvetica-bold",
    under: bool = False,
    margin: float = 36,
) -> PdfWriter:
    """Stamp text on pages. Default: big, diagonal, centred, 30% opaque grey.

    Without ``size`` the text is scaled to span about 70% of the page diagonal (centre) or
    set at 24 pt (other positions).
    """
    if not text:
        raise PdfSwissError("watermark text is empty")
    if not 0 < opacity <= 1:
        raise PdfSwissError("opacity must be between 0 and 1")
    rgb = _color(color)
    writer = _clone(reader)
    for i in _pages(reader, spec):
        page = writer.pages[i]
        draw.normalise_rotation(page)
        left, bottom, w, h = draw.visible_box(page)
        if angle is None:
            a = math.degrees(math.atan2(h, w)) if position == "center" else 0.0
        else:
            a = angle
        if size is None:
            if position == "center":
                span = math.hypot(w, h) * 0.7 if angle is None else min(w, h) * 0.8
                s = span / max(draw.text_width(text, 1, font), 0.01)
                s = min(s, h * 0.5)
            else:
                s = 24.0
        else:
            s = size
        x, y, anchor = _anchor(position, 0, 0, w, h, margin)
        if position.startswith("top"):
            y -= s * 0.75
        stamp = draw.Stamp.blank(w, h)
        stamp.text(text, x, y, s, font=font, color=rgb, opacity=opacity, angle=a, anchor=anchor)
        draw.apply_stamp(page, stamp, left, bottom, over=not under)
    return writer


def watermark_image(
    reader: PdfReader,
    image_path: str,
    *,
    spec: str | None = None,
    scale: float = 0.5,
    opacity: float = 0.3,
    position: str = "center",
    under: bool = False,
    margin: float = 36,
) -> PdfWriter:
    """Stamp an image (PNG with transparency works) at ``scale`` x the page width."""
    if not 0 < scale <= 1:
        raise PdfSwissError("scale must be between 0 and 1")
    if not 0 < opacity <= 1:
        raise PdfSwissError("opacity must be between 0 and 1")
    img, jpeg = _image(image_path)
    writer = _clone(reader)
    ref = draw.image_xobject(writer, img, jpeg_bytes=jpeg)
    for i in _pages(reader, spec):
        page = writer.pages[i]
        draw.normalise_rotation(page)
        left, bottom, w, h = draw.visible_box(page)
        iw, ih = draw.fit_box(img.width, img.height, w * scale, h * scale)
        x, y, anchor = _anchor(position, 0, 0, w, h, margin)
        x -= {"left": 0, "center": iw / 2, "right": iw}[anchor]
        if position == "center":
            y -= ih / 2
        elif position.startswith("top"):
            y -= ih
        stamp = draw.Stamp.blank(w, h)
        stamp.image(ref, x, y, iw, ih, opacity=opacity)
        draw.apply_stamp(page, stamp, left, bottom, over=not under)
    return writer


def number_pages(
    reader: PdfReader,
    *,
    spec: str | None = None,
    fmt: str = "{n}",
    start: int = 1,
    position: str = "bottom-center",
    size: float = 10,
    margin: float = 28,
    color: str = "black",
    font: str = "helvetica",
) -> PdfWriter:
    """Add page numbers. ``fmt`` placeholders: ``{n}`` number, ``{total}`` count, ``{page}``
    physical page, ``{pages}`` physical page count."""
    rgb = _color(color)
    indexes = _pages(reader, spec)
    total_numbered = len(indexes)
    writer = _clone(reader)
    for k, i in enumerate(indexes):
        try:
            label = fmt.format(n=start + k, total=start + total_numbered - 1, page=i + 1, pages=len(reader.pages))
        except (KeyError, IndexError, ValueError) as exc:
            raise PdfSwissError(f"invalid --format {fmt!r}: {exc}") from exc
        page = writer.pages[i]
        draw.normalise_rotation(page)
        left, bottom, w, h = draw.visible_box(page)
        x, y, anchor = _anchor(position, 0, 0, w, h, margin)
        if position.startswith("top"):
            y -= size * 0.75
        stamp = draw.Stamp.blank(w, h)
        stamp.text(label, x, y, size, font=font, color=rgb, anchor=anchor)
        draw.apply_stamp(page, stamp, left, bottom)
    return writer


def _color(value: str) -> tuple[float, float, float]:
    try:
        return draw.parse_color(value)
    except ValueError as exc:
        raise PdfSwissError(str(exc)) from exc


def _image(path: str):
    try:
        return draw.load_image(path)
    except FileNotFoundError as exc:
        raise PdfSwissError(f"{path}: file not found") from exc
    except OSError as exc:  # PIL.UnidentifiedImageError is an OSError
        raise PdfSwissError(f"{path}: not a supported image ({exc})") from exc


# --------------------------------------------------------------------------- security


def encrypt(
    reader: PdfReader,
    user_password: str,
    owner_password: str | None = None,
    *,
    algorithm: str = "AES-256",
    allow_print: bool = True,
    allow_copy: bool = True,
    allow_modify: bool = True,
) -> PdfWriter:
    if not user_password and not owner_password:
        raise PdfSwissError("give a user password, an owner password or both")
    if algorithm not in ("AES-256", "AES-128", "RC4-128"):
        raise PdfSwissError("algorithm must be AES-256, AES-128 or RC4-128")
    perms = UserAccessPermissions.all()
    if not allow_print:
        perms &= ~(UserAccessPermissions.PRINT | UserAccessPermissions.PRINT_TO_REPRESENTATION)
    if not allow_copy:
        perms &= ~(UserAccessPermissions.EXTRACT | UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS)
    if not allow_modify:
        perms &= ~(
            UserAccessPermissions.MODIFY | UserAccessPermissions.ADD_OR_MODIFY | UserAccessPermissions.ASSEMBLE_DOC
        )
    writer = _clone(reader)
    try:
        writer.encrypt(
            user_password=user_password or "",
            owner_password=owner_password or None,
            permissions_flag=perms,
            algorithm=algorithm,
        )
    except Exception as exc:  # e.g. cryptography not installed for AES
        raise PdfSwissError(f"cannot encrypt with {algorithm}: {exc}") from exc
    return writer


def decrypt(reader: PdfReader) -> PdfWriter:
    """Write an unencrypted copy of a reader that :func:`open_pdf` has already decrypted."""
    return _clone(reader)


# --------------------------------------------------------------------------- metadata


def metadata(reader: PdfReader) -> dict[str, str]:
    meta = reader.metadata or {}
    out = {}
    for k, v in meta.items():
        key = str(k).lstrip("/")
        out[key] = str(v)
    return dict(sorted(out.items()))


def set_metadata(reader: PdfReader, values: dict[str, str | None]) -> PdfWriter:
    """Set (or with ``None``/empty, remove) document info fields; keys like ``Title`` or ``/Title``."""
    writer = _clone(reader)
    current = {str(k): v for k, v in (reader.metadata or {}).items()}
    for key, value in values.items():
        name = key if key.startswith("/") else "/" + key[:1].upper() + key[1:]
        if not re.fullmatch(r"/[A-Za-z][A-Za-z0-9_.-]*", name):
            raise PdfSwissError(f"invalid metadata key {key!r}")
        if value in (None, ""):
            current.pop(name, None)
        else:
            current[name] = value
    writer.metadata = current
    return writer


def strip_metadata(reader: PdfReader) -> PdfWriter:
    """Remove the document information dictionary and XMP metadata."""
    writer = _clone(reader)
    writer.metadata = None
    root = writer.root_object
    if NameObject("/Metadata") in root:
        del root[NameObject("/Metadata")]
    for page in writer.pages:
        for key in ("/Metadata", "/PieceInfo"):
            if NameObject(key) in page:
                del page[NameObject(key)]
    return writer


# --------------------------------------------------------------------------- text


def extract_text(reader: PdfReader, spec: str | None = None, layout: bool = False) -> list[tuple[int, str]]:
    out = []
    for i in _pages(reader, spec):
        page = reader.pages[i]
        try:
            text = page.extract_text(extraction_mode="layout") if layout else page.extract_text()
        except Exception as exc:  # pragma: no cover - depends on malformed input
            raise PdfSwissError(f"page {i + 1}: cannot extract text ({exc})") from exc
        out.append((i + 1, text or ""))
    return out


# --------------------------------------------------------------------------- images to PDF


def images_to_pdf(
    paths: Sequence[str],
    *,
    page_size: str = "fit",
    orientation: str = "auto",
    margin: float = 0,
    dpi: float | None = None,
) -> PdfWriter:
    """One page per image. ``page_size`` is ``fit`` (page = image size) or a paper name."""
    if not paths:
        raise PdfSwissError("no images given")
    size_key = page_size.lower()
    if size_key != "fit" and size_key not in PAPER:
        raise PdfSwissError(f"unknown page size {page_size!r}; use fit or one of {', '.join(PAPER)}")
    if orientation not in ("auto", "portrait", "landscape"):
        raise PdfSwissError("orientation must be auto, portrait or landscape")
    writer = PdfWriter()
    for path in paths:
        img, jpeg = _image(path)
        if size_key == "fit":
            res = dpi or _image_dpi(img) or 96.0
            iw, ih = img.width * 72 / res, img.height * 72 / res
            pw, ph = iw + 2 * margin, ih + 2 * margin
        else:
            pw, ph = PAPER[size_key]
            landscape = orientation == "landscape" or (orientation == "auto" and img.width > img.height)
            if landscape:
                pw, ph = ph, pw
            if pw - 2 * margin <= 0 or ph - 2 * margin <= 0:
                raise PdfSwissError("margin is larger than the page")
            iw, ih = draw.fit_box(img.width, img.height, pw - 2 * margin, ph - 2 * margin)
        page = writer.add_blank_page(width=pw, height=ph)
        ref = draw.image_xobject(writer, img, jpeg_bytes=jpeg)
        stamp = draw.Stamp.blank(pw, ph)
        stamp.image(ref, (pw - iw) / 2, (ph - ih) / 2, iw, ih)
        draw.apply_stamp(page, stamp)
    return writer


def _image_dpi(img) -> float | None:
    dpi = img.info.get("dpi")
    if not dpi:
        return None
    try:
        value = float(dpi[0])
    except (TypeError, ValueError, IndexError):
        return None
    return value if 10 <= value <= 4800 else None


# --------------------------------------------------------------------------- compression


def pikepdf_available() -> bool:
    try:
        import pikepdf  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass
class CompressResult:
    engine: str
    before: int
    after: int
    images_recompressed: int = 0
    kept_original: bool = False

    @property
    def saved(self) -> int:
        return self.before - self.after


def compress(
    input_path: str,
    output_path: str,
    *,
    password: str | None = None,
    engine: str = "auto",
    image_quality: int | None = None,
    max_image_dpi: float | None = None,
) -> CompressResult:
    """Lossless stream compression and duplicate removal, plus optional JPEG recompression.

    ``engine``: ``pypdf``, ``pikepdf`` (object streams, recompressed Flate) or ``auto``
    (pikepdf if installed). If the result is not smaller the input is copied unchanged.
    """
    if engine not in ("auto", "pypdf", "pikepdf"):
        raise PdfSwissError("engine must be auto, pypdf or pikepdf")
    has_pike = pikepdf_available()
    if engine == "pikepdf" and not has_pike:
        raise PdfSwissError("pikepdf is not installed; pip install 'pdf-swiss[compress]' or use --engine pypdf")
    if image_quality is not None and not 1 <= image_quality <= 95:
        raise PdfSwissError("image quality must be between 1 and 95")
    use_pike = engine == "pikepdf" or (engine == "auto" and has_pike)

    before = os.path.getsize(input_path)
    reader = open_pdf(input_path, password)
    if reader.is_encrypted:
        raise PdfSwissError("compress does not re-encrypt; decrypt the file first and encrypt the result")
    writer = _clone(reader)
    recompressed = _recompress_images(writer, image_quality, max_image_dpi) if image_quality or max_image_dpi else 0
    for page in writer.pages:
        page.compress_content_streams(level=9)
    writer.compress_identical_objects()  # removes duplicates and orphans
    buf = io.BytesIO()
    writer.write(buf)
    data = buf.getvalue()

    if use_pike:
        import pikepdf

        with pikepdf.open(io.BytesIO(data)) as pdf:
            out = io.BytesIO()
            pdf.remove_unreferenced_resources()
            pdf.save(
                out,
                compress_streams=True,
                recompress_flate=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
            )
            data = out.getvalue()

    kept = False
    if len(data) >= before:
        with open(input_path, "rb") as fh:
            data = fh.read()
        kept = True
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".pdf-swiss-", suffix=".pdf", dir=out_path.parent)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, out_path)
    return CompressResult("pikepdf" if use_pike else "pypdf", before, len(data), recompressed, kept)


def _recompress_images(writer: PdfWriter, quality: int | None, max_dpi: float | None) -> int:
    from PIL import Image

    count = 0
    for page in writer.pages:
        width_pt = float(page.mediabox.width) or 612
        for img in page.images:
            try:
                pil = img.image
            except Exception:  # pragma: no cover - unsupported image encodings are skipped
                continue
            if pil is None or pil.mode not in ("RGB", "L"):
                continue
            changed = False
            if max_dpi:
                # Upper bound: assume the image may span the full page width.
                limit = int(width_pt / 72 * max_dpi)
                if pil.width > limit > 0:
                    pil = pil.resize((limit, max(1, round(pil.height * limit / pil.width))), Image.LANCZOS)
                    changed = True
            if quality or changed:
                try:
                    img.replace(pil, quality=quality or 85)
                    count += 1
                except Exception:  # pragma: no cover - leave images pypdf cannot rewrite alone
                    continue
    return count


# --------------------------------------------------------------------------- info


def _paper_name(w: float, h: float) -> str | None:
    for name, (pw, ph) in PAPER.items():
        if (abs(w - pw) < 2 and abs(h - ph) < 2) or (abs(w - ph) < 2 and abs(h - pw) < 2):
            return name.upper() if name.startswith("a") else name.capitalize()
    return None


def info(path: str, password: str | None = None) -> dict:
    reader = open_pdf(path, password)
    sizes: Counter = Counter()
    rotated = 0
    for page in reader.pages:
        box = page.mediabox
        w, h = round(float(box.width), 2), round(float(box.height), 2)
        if page.rotation % 180:
            w, h = h, w
        sizes[(w, h)] += 1
        rotated += 1 if page.rotation % 360 else 0
    try:
        fields = reader.get_fields() or {}
    except Exception:  # pragma: no cover - malformed AcroForm
        fields = {}
    return {
        "file": str(path),
        "bytes": os.path.getsize(path),
        "pdf_version": reader.pdf_header.replace("%PDF-", ""),
        "pages": len(reader.pages),
        "encrypted": reader.is_encrypted,
        "page_sizes": [
            {
                "width_pt": w,
                "height_pt": h,
                "width_mm": round(w * 25.4 / 72, 1),
                "height_mm": round(h * 25.4 / 72, 1),
                "paper": _paper_name(w, h),
                "pages": n,
            }
            for (w, h), n in sizes.most_common()
        ],
        "rotated_pages": rotated,
        "outline_items": _count_outline(reader.outline),
        "form_fields": len(fields),
        "metadata": metadata(reader),
    }


def _count_outline(items: Iterable) -> int:
    n = 0
    for item in items:
        n += _count_outline(item) if isinstance(item, list) else 1
    return n
