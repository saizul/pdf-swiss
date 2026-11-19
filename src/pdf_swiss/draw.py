"""Low-level drawing without reportlab: Helvetica text, images and stamping onto pages."""

from __future__ import annotations

import io
import math
import zlib
from dataclasses import dataclass

from pypdf import PageObject, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)

# Advance widths (1/1000 em) of Helvetica for WinAnsi codes 32..126, from the standard AFM.
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]  # fmt: skip
_BOLD = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
]  # fmt: skip

FONTS = {"helvetica": ("Helvetica", _HELVETICA), "helvetica-bold": ("Helvetica-Bold", _BOLD)}

NAMED_COLORS = {
    "black": (0, 0, 0),
    "white": (1, 1, 1),
    "gray": (0.5, 0.5, 0.5),
    "grey": (0.5, 0.5, 0.5),
    "red": (0.85, 0.1, 0.1),
    "green": (0.1, 0.6, 0.2),
    "blue": (0.1, 0.3, 0.85),
}


def parse_color(value: str) -> tuple[float, float, float]:
    """``#rrggbb``, ``#rgb`` or a basic colour name to an RGB triple in 0..1."""
    v = value.strip().lower()
    if v in NAMED_COLORS:
        return NAMED_COLORS[v]
    if v.startswith("#"):
        v = v[1:]
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6 or any(c not in "0123456789abcdef" for c in v):
        raise ValueError(f"invalid colour {value!r}; use #rrggbb or one of {', '.join(sorted(NAMED_COLORS))}")
    return tuple(int(v[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def encode_text(text: str) -> bytes:
    """Encode for a WinAnsi Type 1 font; characters outside cp1252 become ``?``."""
    return text.encode("cp1252", "replace")


def text_width(text: str, size: float, font: str = "helvetica") -> float:
    widths = FONTS[font][1]
    total = 0
    for b in encode_text(text):
        total += widths[b - 32] if 32 <= b <= 126 else 556
    return total * size / 1000


def pdf_string(data: bytes) -> bytes:
    out = bytearray(b"(")
    for b in data:
        if b in (0x28, 0x29, 0x5C):  # ( ) \
            out += b"\\" + bytes([b])
        elif b < 32 or b > 126:
            out += f"\\{b:03o}".encode()
        else:
            out.append(b)
    out += b")"
    return bytes(out)


def _n(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


@dataclass
class Stamp:
    """Content and resources to draw on a page of a given size."""

    width: float
    height: float
    ops: list[bytes]
    resources: DictionaryObject

    @classmethod
    def blank(cls, width: float, height: float) -> Stamp:
        return cls(width, height, [], DictionaryObject())

    def _subdict(self, key: str) -> DictionaryObject:
        name = NameObject(key)
        if name not in self.resources:
            self.resources[name] = DictionaryObject()
        return self.resources[name]  # type: ignore[return-value]

    def _font(self, font: str) -> str:
        fonts = self._subdict("/Font")
        key = "/PSF" + ("B" if font.endswith("bold") else "R")
        if NameObject(key) not in fonts:
            fonts[NameObject(key)] = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/" + FONTS[font][0]),
                    NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
                }
            )
        return key

    def _alpha(self, opacity: float) -> str:
        states = self._subdict("/ExtGState")
        key = f"/PSA{round(opacity * 100)}"
        if NameObject(key) not in states:
            states[NameObject(key)] = DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/ExtGState"),
                    NameObject("/ca"): FloatObject(opacity),
                    NameObject("/CA"): FloatObject(opacity),
                }
            )
        return key

    def text(
        self,
        text: str,
        x: float,
        y: float,
        size: float,
        *,
        font: str = "helvetica",
        color: tuple[float, float, float] = (0, 0, 0),
        opacity: float = 1.0,
        angle: float = 0.0,
        anchor: str = "left",
    ) -> None:
        """Draw one line of text. ``(x, y)`` is the anchor point on the baseline
        (``anchor`` left/center/right); with ``center`` the text is also centred vertically."""
        fkey = self._font(font)
        w = text_width(text, size, font)
        dx = {"left": 0.0, "center": -w / 2, "right": -w}[anchor]
        dy = -size * 0.35 if anchor == "center" else 0.0
        rad = math.radians(angle)
        cos, sin = math.cos(rad), math.sin(rad)
        tx = x + dx * cos - dy * sin
        ty = y + dx * sin + dy * cos
        ops = [b"q"]
        if opacity < 1:
            ops.append(f"{self._alpha(opacity)} gs".encode())
        r, g, b = color
        ops.append(f"{_n(r)} {_n(g)} {_n(b)} rg".encode())
        ops.append(b"BT")
        ops.append(f"{fkey} {_n(size)} Tf".encode())
        ops.append(f"{_n(cos)} {_n(sin)} {_n(-sin)} {_n(cos)} {_n(tx)} {_n(ty)} Tm".encode())
        ops.append(pdf_string(encode_text(text)) + b" Tj")
        ops.append(b"ET")
        ops.append(b"Q")
        self.ops.append(b"\n".join(ops))

    def image(self, xobject_ref, x: float, y: float, w: float, h: float, opacity: float = 1.0) -> None:
        """Draw an image XObject (an indirect reference) into the box ``x, y, w, h``."""
        objs = self._subdict("/XObject")
        key = f"/PSI{len(objs)}"
        objs[NameObject(key)] = xobject_ref
        ops = [b"q"]
        if opacity < 1:
            ops.append(f"{self._alpha(opacity)} gs".encode())
        ops.append(f"{_n(w)} 0 0 {_n(h)} {_n(x)} {_n(y)} cm".encode())
        ops.append(f"{key} Do".encode())
        ops.append(b"Q")
        self.ops.append(b"\n".join(ops))

    def page(self) -> PageObject:
        page = PageObject.create_blank_page(width=self.width, height=self.height)
        page[NameObject("/Resources")] = self.resources
        content = DecodedStreamObject()
        content.set_data(b"\n".join(self.ops))
        page[NameObject("/Contents")] = content
        return page


def visible_box(page: PageObject) -> tuple[float, float, float, float]:
    """``(left, bottom, width, height)`` of the crop box (what viewers show)."""
    box = page.cropbox
    return float(box.left), float(box.bottom), float(box.width), float(box.height)


def apply_stamp(page: PageObject, stamp: Stamp, left: float = 0, bottom: float = 0, over: bool = True) -> None:
    """Merge a stamp onto ``page`` with its origin at ``(left, bottom)``."""
    from pypdf import Transformation

    stamp_page = stamp.page()
    if left or bottom:
        page.merge_transformed_page(stamp_page, Transformation().translate(left, bottom), over=over)
    else:
        page.merge_page(stamp_page, over=over)


def normalise_rotation(page: PageObject) -> None:
    """Bake ``/Rotate`` into the content so stamps line up with what the reader sees."""
    if page.rotation % 360:
        page.transfer_rotation_to_content()


# --------------------------------------------------------------------------- images


def image_xobject(writer: PdfWriter, image, *, jpeg_bytes: bytes | None = None):
    """Add a Pillow image to ``writer`` as an image XObject; return the indirect reference.

    Alpha channels become a soft mask. If ``jpeg_bytes`` is given for an RGB/L/CMYK JPEG it
    is embedded unchanged (DCTDecode), which keeps the file small and lossless.
    """
    from PIL import Image

    width, height = image.size
    if jpeg_bytes is not None and image.mode in ("RGB", "L", "CMYK"):
        stream = DecodedStreamObject()
        stream.set_data(jpeg_bytes)
        colorspace = {"RGB": "/DeviceRGB", "L": "/DeviceGray", "CMYK": "/DeviceCMYK"}[image.mode]
        stream.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(width),
                NameObject("/Height"): NumberObject(height),
                NameObject("/ColorSpace"): NameObject(colorspace),
                NameObject("/BitsPerComponent"): NumberObject(8),
                NameObject("/Filter"): NameObject("/DCTDecode"),
            }
        )
        if image.mode == "CMYK" and "adobe" in image.info:
            # Adobe CMYK JPEGs are stored inverted.
            stream[NameObject("/Decode")] = ArrayObject([FloatObject(v) for v in (1, 0, 1, 0, 1, 0, 1, 0)])
        return writer._add_object(stream)

    has_alpha = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
    alpha = None
    if has_alpha:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        if alpha.getextrema() == (255, 255):
            alpha = None
        base = rgba.convert("RGB")
    elif image.mode in ("1", "L", "I", "I;16", "F"):
        base = image.convert("L")
    else:
        base = image.convert("RGB")

    def flate(img: Image.Image, colorspace: str) -> DictionaryObject:
        stream = DecodedStreamObject()
        stream.set_data(zlib.compress(img.tobytes(), 6))
        stream.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Image"),
                NameObject("/Width"): NumberObject(width),
                NameObject("/Height"): NumberObject(height),
                NameObject("/ColorSpace"): NameObject(colorspace),
                NameObject("/BitsPerComponent"): NumberObject(8),
                NameObject("/Filter"): NameObject("/FlateDecode"),
            }
        )
        return stream

    stream = flate(base, "/DeviceGray" if base.mode == "L" else "/DeviceRGB")
    if alpha is not None:
        stream[NameObject("/SMask")] = writer._add_object(flate(alpha, "/DeviceGray"))
    return writer._add_object(stream)


def load_image(path: str):
    """Open an image, apply its EXIF orientation and return ``(image, jpeg_bytes_or_None)``."""
    from PIL import Image, ImageOps

    with open(path, "rb") as fh:
        raw = fh.read()
    img = Image.open(io.BytesIO(raw))
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)
    orientation = img.getexif().get(0x0112, 1)
    if img.format == "JPEG" and orientation in (1, None) and img.mode in ("RGB", "L", "CMYK"):
        img.load()
        return img, raw
    img = ImageOps.exif_transpose(img)
    img.load()
    return img, None


def fit_box(img_w: float, img_h: float, box_w: float, box_h: float) -> tuple[float, float]:
    """Largest ``(w, h)`` with the image's aspect ratio inside the box."""
    scale = min(box_w / img_w, box_h / img_h)
    return img_w * scale, img_h * scale
