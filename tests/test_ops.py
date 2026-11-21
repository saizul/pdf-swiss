import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from pdf_swiss import draw, ops

from .conftest import make_pdf, page_texts


def roundtrip(writer: PdfWriter) -> PdfReader:
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    return PdfReader(buf)


def texts(reader: PdfReader) -> list[str]:
    return [p.extract_text().strip() for p in reader.pages]


def test_generated_fixture_has_text(pdf3):
    assert page_texts(pdf3) == ["Page 1", "Page 2", "Page 3"]


def test_merge_with_page_specs(tmp_path, pdf3):
    other = make_pdf(tmp_path / "b.pdf", 2, label="B")
    r = roundtrip(ops.merge([str(pdf3), f"{other}:2", f"{pdf3}:end-1"], bookmarks=True))
    assert texts(r) == ["Page 1", "Page 2", "Page 3", "B 2", "Page 2"]
    assert [o.title for o in r.outline] == ["three", "b", "three"]


def test_merge_errors(tmp_path):
    with pytest.raises(ops.PdfSwissError, match="not found"):
        ops.merge([str(tmp_path / "missing.pdf")])
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf at all")
    with pytest.raises(ops.PdfSwissError, match="not a readable PDF"):
        ops.merge([str(bad)])
    with pytest.raises(ops.PdfSwissError):
        ops.merge([])


def test_split_input_prefers_existing_file(tmp_path):
    odd = make_pdf(tmp_path / "x.pdf:1", 1)
    assert ops.split_input(str(odd)) == (str(odd), None)
    assert ops.split_input(str(tmp_path / "x.pdf:1") + ":1") == (str(odd), "1")


def test_select_delete_reverse(pdf10):
    reader = ops.open_pdf(pdf10)
    assert texts(roundtrip(ops.select(reader, "10,1-2"))) == ["Page 10", "Page 1", "Page 2"]
    assert len(roundtrip(ops.delete(reader, "even")).pages) == 5
    assert texts(roundtrip(ops.reverse(ops.open_pdf(make_pdf(pdf10.parent / "r.pdf", 3)))))[0] == "Page 3"
    with pytest.raises(ops.PdfSwissError, match="every page"):
        ops.delete(reader, "all")
    with pytest.raises(ops.PdfSwissError, match="out of range"):
        ops.select(reader, "11")


def test_split_every_and_ranges(pdf10):
    reader = ops.open_pdf(pdf10)
    parts = ops.split(reader, every=4)
    assert [g for g, _ in parts] == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]]
    parts = ops.split(reader, ranges="1-2,3,4-end")
    assert [len(w.pages) for _, w in parts] == [2, 1, 7]
    assert len(ops.split(reader)) == 10
    names = ops.split_names("doc", [g for g, _ in ops.split(reader)], "{stem}-{n}.pdf")
    assert names[0] == "doc-01.pdf" and names[-1] == "doc-10.pdf"
    assert ops.split_names("d", [[0, 1], [2]], "{stem}_p{start}-{end}.pdf") == ["d_p1-2.pdf", "d_p3-3.pdf"]
    with pytest.raises(ops.PdfSwissError, match="duplicate"):
        ops.split_names("d", [[0], [1]], "same.pdf")
    with pytest.raises(ops.PdfSwissError):
        ops.split_names("d", [[0]], "{nope}.pdf")
    with pytest.raises(ops.PdfSwissError, match="plain file names"):
        ops.split_names("d", [[0]], "../{stem}.pdf")


def test_rotate(pdf3):
    r = roundtrip(ops.rotate(ops.open_pdf(pdf3), 90, "2-3"))
    assert [p.rotation for p in r.pages] == [0, 90, 90]
    r = roundtrip(ops.rotate(ops.open_pdf(pdf3), -90))
    assert {p.rotation for p in r.pages} == {270}
    r = roundtrip(ops.rotate(ops.open_pdf(ops.save(ops.rotate(ops.open_pdf(pdf3), 270), pdf3)), 180))
    assert {p.rotation for p in r.pages} == {90}
    with pytest.raises(ops.PdfSwissError):
        ops.rotate(ops.open_pdf(pdf3), 45)


def test_watermark_text(pdf3):
    r = roundtrip(ops.watermark_text(ops.open_pdf(pdf3), "CONFIDENTIAL", spec="1,3"))
    t = texts(r)
    assert "CONFIDENTIAL" in t[0] and "Page 1" in t[0]
    assert "CONFIDENTIAL" not in t[1]
    content = r.pages[0].get_contents().get_data()
    assert b"gs" in content  # transparency graphics state


def test_watermark_text_positions_and_options(pdf3):
    for pos in ops.POSITIONS:
        r = roundtrip(
            ops.watermark_text(ops.open_pdf(pdf3), "DRAFT (v2) \\ ü", position=pos, size=20, angle=0, under=True)
        )
        assert "DRAFT (v2)" in r.pages[0].extract_text()
    with pytest.raises(ops.PdfSwissError):
        ops.watermark_text(ops.open_pdf(pdf3), "x", color="nope")
    with pytest.raises(ops.PdfSwissError):
        ops.watermark_text(ops.open_pdf(pdf3), "x", opacity=0)
    with pytest.raises(ops.PdfSwissError):
        ops.watermark_text(ops.open_pdf(pdf3), "")


def test_watermark_on_rotated_and_offset_pages(tmp_path):
    w = PdfWriter()
    p = w.add_blank_page(width=600, height=400)
    p.mediabox.lower_left = (100, 50)
    w.add_blank_page(width=612, height=792).rotate(90)
    path = tmp_path / "odd.pdf"
    w.write(path)
    r = roundtrip(ops.watermark_text(ops.open_pdf(path), "STAMP"))
    assert all("STAMP" in pg.extract_text() for pg in r.pages)
    assert r.pages[1].rotation == 0  # rotation baked into the content


def test_watermark_image(pdf3, png_rgba, jpeg):
    r = roundtrip(ops.watermark_image(ops.open_pdf(pdf3), str(png_rgba), position="bottom-right", scale=0.3))
    imgs = r.pages[0].images
    assert len(imgs) == 1
    assert imgs[0].image.size == (200, 100)
    xobjs = r.pages[0]["/Resources"]["/XObject"]
    first = next(iter(xobjs.values())).get_object()
    assert "/SMask" in first
    r = roundtrip(ops.watermark_image(ops.open_pdf(pdf3), str(jpeg), spec="2"))
    assert len(r.pages[0].images) == 0 and len(r.pages[1].images) == 1
    with pytest.raises(ops.PdfSwissError):
        ops.watermark_image(ops.open_pdf(pdf3), str(png_rgba), scale=2)
    with pytest.raises(ops.PdfSwissError, match="not a supported image"):
        ops.watermark_image(ops.open_pdf(pdf3), str(pdf3))


def test_number_pages(pdf10):
    r = roundtrip(ops.number_pages(ops.open_pdf(pdf10), spec="2-end", fmt="Page {n} of {total}", start=1))
    t = texts(r)
    assert "of" not in t[0]
    assert "Page 1 of 9" in t[1]
    assert "Page 9 of 9" in t[9]
    r = roundtrip(ops.number_pages(ops.open_pdf(pdf10), fmt="{page}/{pages}", position="top-right"))
    assert "10/10" in texts(r)[9]
    with pytest.raises(ops.PdfSwissError):
        ops.number_pages(ops.open_pdf(pdf10), fmt="{bad}")
    with pytest.raises(ops.PdfSwissError):
        ops.number_pages(ops.open_pdf(pdf10), position="middle")


@pytest.mark.parametrize("algorithm", ["AES-256", "AES-128", "RC4-128"])
def test_encrypt_decrypt_roundtrip(tmp_path, pdf3, algorithm):
    enc = ops.save(ops.encrypt(ops.open_pdf(pdf3), "s3cret", "owner-pw", algorithm=algorithm), tmp_path / "e.pdf")
    assert PdfReader(str(enc)).is_encrypted
    with pytest.raises(ops.PdfSwissError, match="encrypted"):
        ops.open_pdf(enc)
    with pytest.raises(ops.PdfSwissError, match="wrong password"):
        ops.open_pdf(enc, "nope")
    reader = ops.open_pdf(enc, "s3cret")
    dec = ops.save(ops.decrypt(reader), tmp_path / "d.pdf")
    assert not PdfReader(str(dec)).is_encrypted
    assert page_texts(dec) == ["Page 1", "Page 2", "Page 3"]
    assert ops.open_pdf(enc, "owner-pw") is not None


def test_encrypt_owner_only_and_permissions(tmp_path, pdf3):
    enc = ops.save(
        ops.encrypt(ops.open_pdf(pdf3), "", "owner", allow_print=False, allow_copy=False), tmp_path / "o.pdf"
    )
    reader = ops.open_pdf(enc)  # opens with the empty user password
    assert reader.is_encrypted
    perms = reader.user_access_permissions
    from pypdf.constants import UserAccessPermissions as P

    assert not perms & P.PRINT and not perms & P.EXTRACT
    with pytest.raises(ops.PdfSwissError):
        ops.encrypt(ops.open_pdf(pdf3), "", None)


def test_metadata_set_show_strip(tmp_path):
    src = make_pdf(tmp_path / "m.pdf", 1, metadata={"/Title": "Old", "/Author": "Ann", "/Custom": "x"})
    reader = ops.open_pdf(src)
    assert ops.metadata(reader)["Title"] == "Old"
    out = ops.save(
        ops.set_metadata(reader, {"Title": "New title", "keywords": "a, b", "Custom": None}), tmp_path / "s.pdf"
    )
    meta = ops.metadata(ops.open_pdf(out))
    assert meta["Title"] == "New title"
    assert meta["Keywords"] == "a, b"
    assert meta["Author"] == "Ann"
    assert "Custom" not in meta
    with pytest.raises(ops.PdfSwissError):
        ops.set_metadata(reader, {"bad key": "x"})
    stripped = ops.save(ops.strip_metadata(ops.open_pdf(out)), tmp_path / "x.pdf")
    r = PdfReader(str(stripped))
    assert not r.metadata
    assert "/Metadata" not in r.trailer["/Root"]
    assert b"New title" not in stripped.read_bytes()


def test_extract_text(pdf3):
    pages = ops.extract_text(ops.open_pdf(pdf3), "2-3")
    assert pages == [(2, "Page 2"), (3, "Page 3")]
    layout = ops.extract_text(ops.open_pdf(pdf3), "1", layout=True)
    assert "Page 1" in layout[0][1]


def test_images_to_pdf_fit(png_rgba, jpeg):
    r = roundtrip(ops.images_to_pdf([str(png_rgba), str(jpeg)]))
    assert len(r.pages) == 2
    # PNG without dpi -> 96 dpi; JPEG carries 150 dpi
    assert float(r.pages[0].mediabox.width) == pytest.approx(200 * 72 / 96)
    assert float(r.pages[1].mediabox.width) == pytest.approx(300 * 72 / 150)
    jpeg_obj = next(iter(r.pages[1]["/Resources"]["/XObject"].values())).get_object()
    assert jpeg_obj["/Filter"] == "/DCTDecode"  # embedded unchanged
    assert jpeg_obj.get_data() == jpeg.read_bytes()


def test_images_to_pdf_paper(tmp_path, jpeg):
    r = roundtrip(ops.images_to_pdf([str(jpeg)], page_size="A4", margin=36))
    box = r.pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == (842, 595)  # landscape for a wide image
    r = roundtrip(ops.images_to_pdf([str(jpeg)], page_size="letter", orientation="portrait"))
    assert round(float(r.pages[0].mediabox.width)) == 612
    with pytest.raises(ops.PdfSwissError):
        ops.images_to_pdf([str(jpeg)], page_size="B9")
    with pytest.raises(ops.PdfSwissError):
        ops.images_to_pdf([str(jpeg)], page_size="a4", margin=1000)
    with pytest.raises(ops.PdfSwissError):
        ops.images_to_pdf([])


@pytest.mark.parametrize("mode", ["L", "1", "P", "CMYK", "LA", "I;16"])
def test_images_to_pdf_modes(tmp_path, mode):
    img = (
        Image.new("I;16", (40, 30), 300) if mode == "I;16" else Image.new("RGB", (40, 30), (200, 10, 10)).convert(mode)
    )
    path = tmp_path / f"img-{mode.replace(';', '')}.{'tif' if mode in ('CMYK', 'I;16') else 'png'}"
    img.save(path)
    r = roundtrip(ops.images_to_pdf([str(path)], dpi=72))
    assert float(r.pages[0].mediabox.width) == pytest.approx(40)
    assert r.pages[0].images[0].image.size == (40, 30)


def test_exif_orientation_is_applied(tmp_path):
    img = Image.new("RGB", (60, 20), (0, 0, 0))
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise when displayed
    path = tmp_path / "rot.jpg"
    img.save(path, exif=exif, dpi=(72, 72))
    r = roundtrip(ops.images_to_pdf([str(path)]))
    box = r.pages[0].mediabox
    assert (round(float(box.width)), round(float(box.height))) == (20, 60)


@pytest.mark.parametrize("engine", ["pypdf", "auto"])
def test_compress(tmp_path, engine):
    # Uncompressed, duplicated content makes an easy target.
    writer = PdfWriter()
    for _ in range(20):
        page = writer.add_blank_page(width=612, height=792)
        stamp = draw.Stamp.blank(612, 792)
        for i in range(60):
            stamp.text(f"line {i} " * 5, 20, 20 + i * 12, 9)
        stamp_page = stamp.page()
        page.merge_page(stamp_page)
    src = tmp_path / "big.pdf"
    writer.write(src)
    out = tmp_path / "small.pdf"
    res = ops.compress(str(src), str(out), engine=engine)
    assert res.after < res.before and not res.kept_original
    assert out.stat().st_size == res.after
    assert "line 3" in PdfReader(str(out)).pages[0].extract_text()


def test_compress_keeps_original_when_not_smaller(tmp_path, pdf3):
    out = tmp_path / "c.pdf"
    first = ops.compress(str(pdf3), str(out), engine="pypdf")
    again = ops.compress(str(out), str(tmp_path / "c2.pdf"), engine="pypdf")
    assert again.after <= first.after
    if again.kept_original:
        assert (tmp_path / "c2.pdf").read_bytes() == out.read_bytes()


def test_compress_images(tmp_path):
    big = Image.effect_noise((1200, 900), 60).convert("RGB")
    path = tmp_path / "noise.png"
    big.save(path)
    src = ops.save(ops.images_to_pdf([str(path)], page_size="a4"), tmp_path / "img.pdf")
    res = ops.compress(str(src), str(tmp_path / "out.pdf"), engine="pypdf", image_quality=40, max_image_dpi=72)
    assert res.images_recompressed == 1
    assert res.after < res.before
    img = PdfReader(str(tmp_path / "out.pdf")).pages[0].images[0].image
    assert img.width <= 842 / 72 * 72 + 1


def test_compress_validation(tmp_path, pdf3, monkeypatch):
    with pytest.raises(ops.PdfSwissError):
        ops.compress(str(pdf3), str(tmp_path / "x.pdf"), engine="zip")
    with pytest.raises(ops.PdfSwissError):
        ops.compress(str(pdf3), str(tmp_path / "x.pdf"), image_quality=0)
    monkeypatch.setattr(ops, "pikepdf_available", lambda: False)
    with pytest.raises(ops.PdfSwissError, match="pikepdf is not installed"):
        ops.compress(str(pdf3), str(tmp_path / "x.pdf"), engine="pikepdf")
    res = ops.compress(str(pdf3), str(tmp_path / "y.pdf"), engine="auto")
    assert res.engine == "pypdf"
    enc = ops.save(ops.encrypt(ops.open_pdf(pdf3), "pw"), tmp_path / "enc.pdf")
    with pytest.raises(ops.PdfSwissError, match="decrypt"):
        ops.compress(str(enc), str(tmp_path / "z.pdf"), password="pw")


def test_info(tmp_path):
    w = PdfWriter()
    w.add_blank_page(width=595.28, height=841.89)
    w.add_blank_page(width=612, height=792).rotate(90)
    w.add_outline_item(title="Start", page_number=0)
    w.add_metadata({"/Title": "Report"})
    path = tmp_path / "i.pdf"
    w.write(path)
    data = ops.info(str(path))
    assert data["pages"] == 2
    assert data["rotated_pages"] == 1
    assert data["outline_items"] == 1
    assert {s["paper"] for s in data["page_sizes"]} == {"A4", "Letter"}
    assert data["metadata"]["Title"] == "Report"
    assert data["pdf_version"].startswith("1.")


def test_save_in_place(pdf3):
    reader = ops.open_pdf(pdf3)
    ops.save(ops.select(reader, "1"), pdf3)
    assert page_texts(pdf3) == ["Page 1"]
    assert not [p for p in pdf3.parent.iterdir() if p.name.startswith(".pdf-swiss-")]


def test_color_parsing():
    assert draw.parse_color("#ff0000") == (1.0, 0.0, 0.0)
    assert draw.parse_color("#0f0") == (0.0, 1.0, 0.0)
    assert draw.parse_color("Gray") == (0.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        draw.parse_color("#12345")


def test_text_helpers():
    assert draw.text_width("", 12) == 0
    assert draw.text_width("i", 1000) == 222
    assert draw.pdf_string(b"a(b)\\c\n") == b"(a\\(b\\)\\\\c\\012)"
    assert draw.encode_text("café €") == b"caf\xe9 \x80"
    assert draw.encode_text("日本") == b"??"


def test_insert_blank_every_and_pad(pdf3):
    reader = PdfReader(str(pdf3))
    assert texts(roundtrip(ops.insert_blank(reader, every=1))) == ["Page 1", "", "Page 2", "", "Page 3"]
    assert texts(roundtrip(ops.insert_blank(reader, every=2))) == ["Page 1", "Page 2", "", "Page 3"]
    assert texts(roundtrip(ops.insert_blank(reader, pad_to=4))) == ["Page 1", "Page 2", "Page 3", ""]
    assert len(roundtrip(ops.insert_blank(reader, pad_to=3)).pages) == 3
    both = roundtrip(ops.insert_blank(reader, every=1, pad_to=2))
    assert texts(both) == ["Page 1", "", "Page 2", "", "Page 3", ""]


def test_insert_blank_after_before_and_count(pdf3):
    reader = PdfReader(str(pdf3))
    r = roundtrip(ops.insert_blank(reader, after="2", before="1", count=2))
    assert texts(r) == ["", "", "Page 1", "Page 2", "", "", "Page 3"]
    r = roundtrip(ops.insert_blank(reader, after="end", before="3"))
    assert texts(r) == ["Page 1", "Page 2", "", "Page 3", ""]
    r = roundtrip(ops.insert_blank(reader, after="odd"))
    assert texts(r) == ["Page 1", "", "Page 2", "Page 3", ""]


def test_insert_blank_copies_neighbour_size_and_rotation(tmp_path):
    a4 = make_pdf(tmp_path / "a4.pdf", 1, size=(595.28, 841.89))
    wide = make_pdf(tmp_path / "wide.pdf", 1, size=(800, 400))
    merged = tmp_path / "mixed.pdf"
    ops.save(ops.rotate(PdfReader(str(ops.save(ops.merge([str(a4), str(wide)]), merged))), 90, "2"), merged)
    r = roundtrip(ops.insert_blank(PdfReader(str(merged)), before="1", after="all"))
    sizes = [(round(float(p.mediabox.width)), round(float(p.mediabox.height)), p.rotation) for p in r.pages]
    assert sizes == [(595, 842, 0), (595, 842, 0), (595, 842, 0), (800, 400, 90), (800, 400, 90)]


def test_insert_blank_keeps_metadata_and_validates(tmp_path):
    src = make_pdf(tmp_path / "m.pdf", 2, metadata={"/Title": "Report"})
    reader = PdfReader(str(src))
    assert roundtrip(ops.insert_blank(reader, every=1)).metadata["/Title"] == "Report"
    with pytest.raises(ops.PdfSwissError, match="give --after"):
        ops.insert_blank(reader)
    with pytest.raises(ops.PdfSwissError, match="cannot be combined"):
        ops.insert_blank(reader, every=1, after="1")
    for kwargs in ({"every": 0}, {"pad_to": 0}, {"every": 1, "count": 0}):
        with pytest.raises(ops.PdfSwissError, match="at least 1"):
            ops.insert_blank(reader, **kwargs)
    with pytest.raises(ops.PdfSwissError, match="out of range"):
        ops.insert_blank(reader, after="5")
