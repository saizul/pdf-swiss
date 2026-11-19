import json

import pytest
from pypdf import PdfReader

from pdf_swiss import __version__
from pdf_swiss.cli import main

from .conftest import make_pdf, page_texts


def run(capsys, *args):
    code = main([str(a) for a in args])
    out = capsys.readouterr()
    return code, out.out, out.err


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_help_without_command(capsys):
    assert main([]) == 2


def test_merge_split_extract(tmp_path, capsys, pdf3):
    b = make_pdf(tmp_path / "b.pdf", 2, label="B")
    out = tmp_path / "m.pdf"
    code, _, err = run(capsys, "merge", pdf3, f"{b}:2", "-o", out, "--bookmarks")
    assert code == 0 and "4 pages" in err
    assert page_texts(out) == ["Page 1", "Page 2", "Page 3", "B 2"]

    code, _, err = run(capsys, "split", out, "--ranges", "1-2,3-end", "-d", tmp_path / "parts")
    assert code == 0
    assert page_texts(tmp_path / "parts" / "m-1.pdf") == ["Page 1", "Page 2"]
    assert page_texts(tmp_path / "parts" / "m-2.pdf") == ["Page 3", "B 2"]

    code, _, _ = run(capsys, "split", out, "-d", tmp_path / "each", "--pattern", "p{start}.pdf")
    assert sorted(p.name for p in (tmp_path / "each").iterdir()) == ["p1.pdf", "p2.pdf", "p3.pdf", "p4.pdf"]

    code, _, _ = run(capsys, "extract", out, "-p", "end,1", "-o", tmp_path / "e.pdf")
    assert page_texts(tmp_path / "e.pdf") == ["B 2", "Page 1"]


def test_delete_reorder_rotate(tmp_path, capsys, pdf3):
    run(capsys, "delete", pdf3, "-p", "2", "-o", tmp_path / "d.pdf")
    assert page_texts(tmp_path / "d.pdf") == ["Page 1", "Page 3"]
    run(capsys, "reorder", pdf3, "--order", "3,1,2", "-o", tmp_path / "r.pdf")
    assert page_texts(tmp_path / "r.pdf") == ["Page 3", "Page 1", "Page 2"]
    run(capsys, "reorder", pdf3, "--reverse", "-o", tmp_path / "rv.pdf")
    assert page_texts(tmp_path / "rv.pdf") == ["Page 3", "Page 2", "Page 1"]
    run(capsys, "rotate", pdf3, "-a", "180", "-p", "odd", "-o", tmp_path / "rot.pdf")
    assert [p.rotation for p in PdfReader(str(tmp_path / "rot.pdf")).pages] == [180, 0, 180]


def test_watermark_and_number(tmp_path, capsys, pdf3, png_rgba):
    code, _, _ = run(capsys, "watermark", pdf3, "--text", "DRAFT", "-o", tmp_path / "w.pdf")
    assert code == 0 and all("DRAFT" in t for t in page_texts(tmp_path / "w.pdf"))
    code, _, _ = run(capsys, "watermark", pdf3, "--image", png_rgba, "--opacity", "0.5", "-o", tmp_path / "wi.pdf")
    assert code == 0 and len(PdfReader(str(tmp_path / "wi.pdf")).pages[2].images) == 1
    code, _, err = run(capsys, "watermark", pdf3, "-o", tmp_path / "x.pdf")
    assert code == 1 and "exactly one" in err
    code, _, _ = run(capsys, "number", pdf3, "--format", "{n}/{total}", "--start", "5", "-o", tmp_path / "n.pdf")
    assert "7/7" in page_texts(tmp_path / "n.pdf")[2]


def test_encrypt_decrypt(tmp_path, capsys, pdf3, monkeypatch):
    monkeypatch.setenv("PDF_PW", "hunter2")
    code, _, _ = run(capsys, "encrypt", pdf3, "--user-password-env", "PDF_PW", "--no-print", "-o", tmp_path / "e.pdf")
    assert code == 0 and PdfReader(str(tmp_path / "e.pdf")).is_encrypted
    code, _, err = run(capsys, "text", tmp_path / "e.pdf")
    assert code == 1 and "--password" in err
    code, out, _ = run(capsys, "text", tmp_path / "e.pdf", "--password-env", "PDF_PW")
    assert "Page 2" in out
    code, _, err = run(capsys, "decrypt", tmp_path / "e.pdf", "--password", "wrong", "-o", tmp_path / "d.pdf")
    assert code == 1 and "wrong password" in err
    code, _, _ = run(capsys, "decrypt", tmp_path / "e.pdf", "--password", "hunter2", "-o", tmp_path / "d.pdf")
    assert code == 0 and not PdfReader(str(tmp_path / "d.pdf")).is_encrypted
    code, _, err = run(capsys, "decrypt", pdf3, "--password", "x", "-o", tmp_path / "d2.pdf")
    assert code == 1 and "not encrypted" in err
    code, _, err = run(capsys, "encrypt", pdf3, "-o", tmp_path / "e2.pdf")
    assert code == 1


def test_password_prompt(tmp_path, capsys, pdf3, monkeypatch):
    run(capsys, "encrypt", pdf3, "--user-password", "pw", "-o", tmp_path / "e.pdf")
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "pw")
    code, out, _ = run(capsys, "text", tmp_path / "e.pdf", "--password", "-")
    assert code == 0 and "Page 1" in out


def test_meta(tmp_path, capsys):
    src = make_pdf(tmp_path / "m.pdf", 1, metadata={"/Title": "T", "/Author": "A"})
    code, out, _ = run(capsys, "meta", "show", src, "--json")
    assert json.loads(out)["Title"] == "T"
    code, _, _ = run(
        capsys, "meta", "set", src, "--title", "New", "--set", "Department=QA", "--unset", "Author", "-o", src
    )
    assert code == 0
    _, out, _ = run(capsys, "meta", "show", src)
    assert "New" in out and "Department" in out and "Author" not in out
    code, _, err = run(capsys, "meta", "set", src, "-o", src)
    assert code == 1 and "nothing to change" in err
    code, _, err = run(capsys, "meta", "set", src, "--set", "novalue", "-o", src)
    assert code == 1
    run(capsys, "meta", "strip", src, "-o", tmp_path / "s.pdf")
    _, out, _ = run(capsys, "meta", "show", tmp_path / "s.pdf")
    assert "no document metadata" in out


def test_text_output(tmp_path, capsys, pdf3):
    _, out, _ = run(capsys, "text", pdf3, "-p", "1-2")
    assert out == "Page 1\fPage 2\n"
    run(capsys, "-q", "text", pdf3, "--page-markers", "-o", tmp_path / "t.txt")
    assert (tmp_path / "t.txt").read_text().startswith("--- page 1 ---\nPage 1")


def test_img2pdf_and_compress(tmp_path, capsys, jpeg, png_rgba):
    code, _, _ = run(capsys, "img2pdf", jpeg, png_rgba, "--page-size", "a4", "-o", tmp_path / "i.pdf")
    assert code == 0 and len(PdfReader(str(tmp_path / "i.pdf")).pages) == 2
    code, _, err = run(capsys, "compress", tmp_path / "i.pdf", "--engine", "pypdf", "-o", tmp_path / "c.pdf")
    assert code == 0 and "compress (pypdf)" in err
    code, _, err = run(capsys, "img2pdf", tmp_path / "missing.png", "-o", tmp_path / "x.pdf")
    assert code == 1 and "not found" in err


def test_info(capsys, pdf3):
    code, out, _ = run(capsys, "info", pdf3)
    assert code == 0 and "Pages:       3" in out and "Letter" in out
    _, out, _ = run(capsys, "info", pdf3, "--json")
    assert json.loads(out)["pages"] == 3


def test_errors_exit_1(tmp_path, capsys, pdf3):
    code, _, err = run(capsys, "extract", pdf3, "-p", "9", "-o", tmp_path / "x.pdf")
    assert code == 1 and "out of range" in err
    code, _, err = run(capsys, "rotate", pdf3, "-a", "45", "-o", tmp_path / "x.pdf")
    assert code == 1
    code, _, err = run(capsys, "merge", tmp_path / "nope.pdf", "-o", tmp_path / "x.pdf")
    assert code == 1 and "not found" in err
    assert not (tmp_path / "x.pdf").exists()


def test_quiet(tmp_path, capsys, pdf3):
    code, _, err = run(capsys, "-q", "rotate", pdf3, "-o", tmp_path / "r.pdf")
    assert code == 0 and err == ""
