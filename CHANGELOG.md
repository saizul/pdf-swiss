# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `blank` command and `ops.insert_blank()`: insert blank pages `--after` or `--before`
  selected pages, `--every N` pages (never after the last page), and/or `--pad-to N` to make
  the page count a multiple of N; `-n/--count` blanks per insertion. Blank pages copy the
  size and rotation of their neighbour, and document metadata is kept.

## [0.1.0] - 2026-11-19

### Added

- Commands: `merge`, `split`, `extract`, `delete`, `reorder`, `rotate`, `watermark`,
  `number`, `encrypt`, `decrypt`, `meta show|set|strip`, `text`, `img2pdf`, `compress`, `info`.
- One page syntax everywhere: `1-3,7`, `8-end`, `end-1`, `odd`, `even`, reversed ranges.
- `merge` takes per-file pages (`part.pdf:2-5`) and can add a bookmark per input.
- `split` by ranges, every N pages or one file per page, with a file name pattern.
- Text and image watermarks (transparency, position, angle, over or under the content) and
  page numbers with `{n}`, `{total}`, `{page}` and `{pages}`, drawn without reportlab;
  rotated pages and offset crop boxes are handled.
- AES-256 / AES-128 / RC4-128 encryption with permission flags; passwords from the command
  line, an environment variable or a prompt.
- `img2pdf` with fit-to-image or paper sizes, automatic orientation, EXIF rotation,
  transparency, and JPEG pass-through without recompression.
- `compress`: lossless stream compression and duplicate removal with pypdf, object streams with
  pikepdf when installed (`pip install 'pdf-swiss[compress]'`), optional JPEG recompression and
  downscaling; never writes a bigger file.
- Atomic writes, so `-o` can point at the input file.
- Container image on `ghcr.io/saizul/pdf-swiss` (includes pikepdf).

[Unreleased]: https://github.com/saizul/pdf-swiss/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saizul/pdf-swiss/releases/tag/v0.1.0
