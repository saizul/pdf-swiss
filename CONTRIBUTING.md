# Contributing to pdf-swiss

Thank you for helping! New commands, fixes for odd PDFs, documentation and bug reports are
all welcome.

- [Ways to contribute](#ways-to-contribute)
- [Good first issues](#good-first-issues)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [Add a command](#add-a-command)
- [Guidelines](#guidelines)
- [Pull request process](#pull-request-process)

## Ways to contribute

| Size | Idea |
| --- | --- |
| 10 minutes | Fix a typo, add a recipe to `examples/recipes.sh`, add a FAQ entry |
| 30 minutes | Improve an error message, add a missing test case |
| 1-2 hours | One of the good first issues below |
| Larger | OCR, form filling, digital signatures (open an issue first) |

Comment on an issue before you start so nobody else picks the same one.

## Good first issues

Each of these is self-contained and touches `ops.py`, `cli.py` and the tests.

1. **`crop`**: set the crop box from margins in points or millimetres
   (`--margins 20` or `--margins 10mm,15mm`), for selected pages.
2. **`images` (extract)**: save every embedded image to a folder with `page.images`
   (`{stem}-p{page}-{n}.{ext}`).
3. **`bookmarks`**: list the outline as an indented tree, and `--json`.
4. **`nup`**: put 2 or 4 pages on one sheet with `merge_transformed_page` (scale + translate).
5. **Font choice for stamps**: add Times-Roman and Courier (their AFM widths) to
   `draw.FONTS` and a `--font` option for `watermark` and `number`.
6. **`--dry-run` for `split`**: print the file names and page ranges without writing.
7. **`attach`**: embed files into a PDF with `writer.add_attachment` and list them in `info`.
8. **Roman numerals** for `number`: a `{n:roman}` style placeholder for front matter.

## Development setup

```bash
git clone https://github.com/saizul/pdf-swiss
cd pdf-swiss
python -m venv .venv
. .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev,compress]"    # leave out compress to test without pikepdf
pytest
ruff check . && ruff format --check .
```

Python 3.11+ is needed. Tests never use binary fixtures or the network: `tests/conftest.py`
builds PDFs with pypdf (each page shows "Page N" so text extraction can verify page order) and
images with Pillow. CI runs the suite with and without pikepdf.

## Project layout

| Path | Responsibility |
| --- | --- |
| `src/pdf_swiss/pages.py` | Page selection syntax (`1-3,7`, `end-1`, `odd`, ...) |
| `src/pdf_swiss/draw.py` | Helvetica text, image XObjects and stamping without reportlab |
| `src/pdf_swiss/ops.py` | Every operation as a library function; opening, decrypting and atomic saving |
| `src/pdf_swiss/cli.py` | Argument parsing, password handling and messages |
| `tests/` | pytest suite; `conftest.py` generates PDFs and images |

## Add a command

1. Write the operation in `ops.py`. Take a `PdfReader` (or paths) and return a `PdfWriter`;
   use `_pages(reader, spec)` for page selections and raise `PdfSwissError` with a message a
   user can act on.
2. Test it in `tests/test_ops.py`: generate the input with `make_pdf()`, check the result
   with `extract_text()`, page counts, rotations or boxes.
3. Add a subcommand in `cli.build_parser()` and a small `cmd_*` function. Use `_add_output`
   and `_add_password` so options look the same everywhere.
4. Add a CLI test in `tests/test_cli.py`, a row in the README command table, a recipe if it
   is useful, and a line under "Unreleased" in `CHANGELOG.md`.

## Guidelines

- Runtime dependencies are pypdf and Pillow; pikepdf stays optional. Discuss new ones first.
- No reportlab: draw with `draw.Stamp`.
- Never print or log passwords. Accept them from `--password-env` and prompts as well.
- Keep the page syntax and option names consistent across commands (`-p/--pages`, `-o`).
- Type hints everywhere; `ruff check` and `ruff format` clean.

## Pull request process

1. Fork and create a branch (`feat/crop`, `fix/rotated-watermark`).
2. Keep pull requests focused; fill in the checklist in the template.
3. Add an entry to `CHANGELOG.md` under "Unreleased".
4. A maintainer reviews within a few days.

By contributing you agree that your work is released under the MIT License and
that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
