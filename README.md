# pdf-swiss

[![CI](https://github.com/saizul/pdf-swiss/actions/workflows/ci.yml/badge.svg)](https://github.com/saizul/pdf-swiss/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/saizul/pdf-swiss?sort=semver)](https://github.com/saizul/pdf-swiss/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Container image](https://img.shields.io/badge/ghcr.io-saizul%2Fpdf--swiss-2496ED?logo=docker&logoColor=white)](https://github.com/saizul/pdf-swiss/pkgs/container/pdf-swiss)
![Python](https://img.shields.io/badge/python-3.11%E2%80%933.13-blue)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**One small command for everyday PDF jobs.** Merge, split, rotate, extract, delete and reorder
pages, stamp text or image watermarks, add page numbers, encrypt and decrypt, view, edit or
strip metadata, extract text, turn images into a PDF and make files smaller. Pure Python on
[pypdf](https://github.com/py-pdf/pypdf) and Pillow: no Ghostscript, no Java, no upload to a
website.

```bash
pdf-swiss merge cover.pdf report.pdf:2-5 appendix.pdf -o handout.pdf
pdf-swiss watermark handout.pdf --text CONFIDENTIAL -o handout.pdf
pdf-swiss number handout.pdf -p 2-end --format "Page {n} of {total}" -o handout.pdf
pdf-swiss encrypt handout.pdf --user-password - -o handout-protected.pdf
```

## Contents

- [Quick start](#quick-start)
- [Selecting pages](#selecting-pages)
- [Commands](#commands)
- [Examples](#examples)
- [Use it from Python](#use-it-from-python)
- [FAQ](#faq)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Quick start

### pip

```bash
pip install "pdf-swiss[compress] @ git+https://github.com/saizul/pdf-swiss"
pdf-swiss info some.pdf
pdf-swiss --help
```

The `compress` extra installs [pikepdf](https://github.com/pikepdf/pikepdf) for better
compression. Everything else works without it; `pip install git+https://github.com/saizul/pdf-swiss`
is enough.

### Docker

```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/work" ghcr.io/saizul/pdf-swiss merge a.pdf b.pdf -o merged.pdf
```

The image includes pikepdf. Files are read and written relative to the mounted `/work` folder;
`--user` makes the output belong to you (the image otherwise runs as an unprivileged user).

## Selecting pages

Every `-p/--pages`, `--order`, `--ranges` and `file.pdf:PAGES` uses the same syntax. Pages
are numbered from 1.

| Spec | Pages |
| --- | --- |
| `5` | page 5 |
| `2-7` | pages 2 to 7 |
| `7-2` | pages 7 down to 2 (reversed) |
| `8-` or `8-end` | page 8 to the last page |
| `-3` | pages 1 to 3 |
| `end` / `last` | the last page |
| `end-1` | the second to last page |
| `odd`, `even`, `all` | what they say |
| `1,3,5-7,end` | combine items with commas; order and repeats are kept |

## Commands

| Command | What it does |
| --- | --- |
| `merge IN... -o OUT` | Concatenate PDFs; `part.pdf:2-5` takes only some pages; `--bookmarks` adds one per file |
| `split IN [--ranges R \| --every N] [-d DIR]` | One file per page (default), every N pages, or per range (`1-3,4-9,10-end`); `--pattern "{stem}-{n}.pdf"` with `{stem} {n} {start} {end} {count}` |
| `extract IN -p PAGES -o OUT` | Keep only these pages, in this order |
| `delete IN -p PAGES -o OUT` | Remove pages |
| `reorder IN (--order SPEC \| --reverse) -o OUT` | New page order |
| `rotate IN [-a 90] [-p PAGES] -o OUT` | Rotate clockwise by 90, 180, 270 or -90 degrees |
| `watermark IN (--text T \| --image IMG) -o OUT` | Stamp text or an image; `--position`, `--opacity`, `--size`, `--angle`, `--color`, `--scale`, `--under`, `-p` |
| `number IN -o OUT` | Page numbers; `--format "Page {n} of {total}"`, `--start`, `--position`, `--size`, `--margin`, `--color`, `-p 2-end` to skip a cover |
| `encrypt IN -o OUT` | AES-256 (default), AES-128 or RC4-128; `--user-password`, `--owner-password`, `--no-print`, `--no-copy`, `--no-modify` |
| `decrypt IN --password PW -o OUT` | Write an unprotected copy of a file you can open |
| `meta show IN [--json]` | Print document metadata |
| `meta set IN -o OUT` | `--title --author --subject --keywords --creator --producer`, `--set KEY=VALUE`, `--unset KEY` |
| `meta strip IN -o OUT` | Remove the document information and XMP metadata |
| `text IN [-p PAGES] [-o FILE]` | Extract text; pages separated by form feeds or `--page-markers`; `--layout` keeps columns |
| `img2pdf IMG... -o OUT` | One page per image; `--page-size fit\|a4\|letter\|...`, `--orientation`, `--margin`, `--dpi` |
| `compress IN -o OUT` | Lossless by default; `--image-quality 1-95` and `--max-image-dpi N` recompress images; `--engine auto\|pypdf\|pikepdf` |
| `info IN [--json]` | Pages, page sizes (pt, mm, paper name), PDF version, encryption, rotation, bookmarks, form fields, metadata |

Common to the commands that read a PDF:

- `--password PW`, `--password -` (prompt) or `--password-env VAR` to open encrypted input
- `-o FILE` may be the input file itself: output is written to a temporary file and renamed
- `pdf-swiss -q <command> ...` suppresses progress messages

Exit codes: `0` success, `1` error (bad file, wrong password, invalid pages), `2` usage error.

### Positions

`--position` for `watermark` and `number`: `top-left`, `top-center`, `top-right`, `center`,
`bottom-left`, `bottom-center`, `bottom-right`. Positions follow the page as it is displayed,
including rotated pages and pages whose crop box does not start at 0,0.

### Watermark defaults

A centred text watermark runs along the page diagonal, sized to about 70% of it, in 30% opaque
grey Helvetica Bold. Give `--angle 0` for horizontal text and `--size` for a fixed size. Text
uses the WinAnsi character set (Western European languages); other characters become `?`.

### Compression

`compress` always starts with lossless steps: content streams are recompressed and duplicate
objects removed (pypdf). If pikepdf is installed it then writes object streams and recompresses
Flate data, which typically saves another 5-30% on text-heavy files. Image recompression is
lossy and only happens when you ask for it:

```bash
pdf-swiss compress scan.pdf --image-quality 60 --max-image-dpi 150 -o scan-small.pdf
```

If the result would not be smaller, the input is copied unchanged and you are told so.

## Examples

```bash
# Split a 300-page scan into 10-page files: scan-01.pdf, scan-02.pdf, ...
pdf-swiss split scan.pdf --every 10 -d parts

# Pages 1-3 and the last page of a contract
pdf-swiss extract contract.pdf -p 1-3,end -o summary.pdf

# Fix a duplex scan where the back sides came out upside down
pdf-swiss rotate scan.pdf -a 180 -p even -o scan.pdf

# Logo watermark under the content, bottom right, 15% of the page width
pdf-swiss watermark slides.pdf --image logo.png --position bottom-right --scale 0.15 --opacity 1 --under -o slides.pdf

# Encrypt with a password from the environment and forbid printing
PDF_PASSWORD='change-me' pdf-swiss encrypt invoice.pdf --user-password-env PDF_PASSWORD --no-print -o invoice-locked.pdf

# Clean metadata before publishing, then set a title
pdf-swiss meta strip paper.pdf -o paper.pdf && pdf-swiss meta set paper.pdf --title "My paper" -o paper.pdf

# Photos to an A4 PDF with 1 cm margins
pdf-swiss img2pdf IMG_*.jpg --page-size a4 --margin 28 -o photos.pdf

# Text of pages 2-4 into a file
pdf-swiss text report.pdf -p 2-4 -o report.txt
```

More in [`examples/recipes.sh`](examples/recipes.sh) and
[`examples/library_usage.py`](examples/library_usage.py).

## Use it from Python

Every command is a function in `pdf_swiss.ops` that takes a `PdfReader` (or paths) and returns
a `pypdf.PdfWriter`:

```python
from pdf_swiss import ops

reader = ops.open_pdf("in.pdf", password=None)
writer = ops.watermark_text(reader, "DRAFT", opacity=0.2)
ops.save(writer, "out.pdf")

ops.save(ops.merge(["a.pdf", "b.pdf:1-3"]), "merged.pdf")
print(ops.info("merged.pdf")["pages"])
```

## FAQ

**Why another PDF tool?** pdftk is not maintained everywhere, qpdf and Ghostscript have
steep option lists, and online tools upload your documents. pdf-swiss covers the common jobs
with one consistent syntax, installs with pip on Windows, macOS and Linux, and doubles as a
Python library.

**Does `merge` keep bookmarks, links and forms?** `merge`, `split`, `extract`, `delete` and
`reorder` copy pages, so links between pages and the original outline are not carried over
(use `merge --bookmarks` for one bookmark per file). Commands that change a whole document
(`rotate`, `watermark`, `number`, `encrypt`, `decrypt`, `meta`, `compress`) keep everything.

**How secure is `encrypt`?** AES-256 with a strong user password is real protection. The
permission flags (`--no-print`, ...) are only honoured by cooperating readers. Prefer
`--user-password-env` or `--user-password -` to typing passwords on the command line.

**Can `decrypt` remove a password I do not know?** No. It writes an unprotected copy of a file
you can open with its password. (Files with only an owner password open without one.)

**Why does `text` return nothing for my file?** The file probably contains scanned images, not
text. pdf-swiss does not do OCR; try `ocrmypdf` first.

**Non-Latin text in watermarks?** The built-in Helvetica covers Western European characters
only. Using an embedded TrueType font is on the roadmap.

**Why is `compress` not shrinking my file?** Lossless compression cannot do much for files that
are already compressed or mostly images. Try `--image-quality 60` and `--max-image-dpi 150`.

## Roadmap

Ideas marked "good first issue" are described in [CONTRIBUTING.md](CONTRIBUTING.md#good-first-issues).

- [ ] `crop` by margins (good first issue)
- [ ] `blank` pages for duplex printing (good first issue)
- [ ] Extract embedded images (good first issue)
- [ ] List bookmarks (good first issue)
- [ ] `nup`: 2 or 4 pages per sheet (good first issue)
- [ ] Times and Courier for stamps (good first issue)
- [ ] Embedded TrueType fonts for watermarks in any script
- [ ] Keep the outline when merging and splitting
- [ ] Fill and flatten forms

## Contributing

Contributions of every size are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) for the setup,
the project layout, how to add a command and a list of good first issues. Please follow the
[Code of Conduct](CODE_OF_CONDUCT.md) and report security problems privately as described in
[SECURITY.md](SECURITY.md).

```bash
pip install -e ".[dev,compress]"
pytest
ruff check . && ruff format --check .
```

## License

[MIT](LICENSE) © Saizul Amin
