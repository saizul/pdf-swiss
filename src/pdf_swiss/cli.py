"""Command line interface: ``pdf-swiss <command> [options]``."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pdf_swiss import ops
from pdf_swiss._version import __version__
from pdf_swiss.pages import describe

PAGES_HELP = 'pages, e.g. "1-3,7,10-end", "odd", "even", "end-1" (default: all)'


class Fail(Exception):
    pass


# --------------------------------------------------------------------------- helpers


def _password(args: argparse.Namespace, attr: str = "password", env_attr: str = "password_env") -> str | None:
    value = getattr(args, attr, None)
    env = getattr(args, env_attr, None)
    if env:
        if env not in os.environ:
            raise Fail(f"environment variable {env} is not set")
        return os.environ[env]
    if value == "-":
        return getpass.getpass("Password: ")
    return value


def _add_password(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("encrypted input")
    g.add_argument("--password", metavar="PW", help='password of the input file ("-" to prompt)')
    g.add_argument("--password-env", metavar="VAR", help="read the input password from this environment variable")


def _add_output(p: argparse.ArgumentParser, required: bool = True) -> None:
    p.add_argument("-o", "--output", required=required, metavar="FILE", help="output PDF (may be the input file)")


def _open(args: argparse.Namespace):
    return ops.open_pdf(args.input, _password(args))


def _done(args: argparse.Namespace, writer, what: str) -> int:
    out = ops.save(writer, args.output)
    if not args.quiet:
        print(f"{what}: wrote {out} ({len(writer.pages)} page{'s' * (len(writer.pages) != 1)})", file=sys.stderr)
    return 0


def _size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"  # pragma: no cover


# --------------------------------------------------------------------------- commands


def cmd_merge(args):
    writer = ops.merge(args.inputs, _password(args), bookmarks=args.bookmarks)
    return _done(args, writer, f"merged {len(args.inputs)} files")


def cmd_split(args):
    reader = _open(args)
    parts = ops.split(reader, ranges=args.ranges, every=args.every)
    outdir = Path(args.output_dir or ".")
    names = ops.split_names(Path(args.input).stem, [g for g, _ in parts], args.pattern)
    for (group, writer), name in zip(parts, names, strict=True):
        path = ops.save(writer, outdir / name)
        if not args.quiet:
            print(f"{path}  pages {describe(group)}", file=sys.stderr)
    return 0


def cmd_extract(args):
    return _done(args, ops.select(_open(args), args.pages), "extracted")


def cmd_delete(args):
    return _done(args, ops.delete(_open(args), args.pages), "deleted pages")


def cmd_reorder(args):
    reader = _open(args)
    if args.reverse:
        writer = ops.reverse(reader)
    elif args.order:
        writer = ops.select(reader, args.order)
    else:
        raise Fail("give --order or --reverse")
    return _done(args, writer, "reordered")


def cmd_rotate(args):
    return _done(args, ops.rotate(_open(args), args.angle, args.pages), f"rotated by {args.angle}")


def cmd_watermark(args):
    reader = _open(args)
    if bool(args.text) == bool(args.image):
        raise Fail("give exactly one of --text or --image")
    if args.text:
        writer = ops.watermark_text(
            reader,
            args.text,
            spec=args.pages,
            size=args.size,
            angle=args.angle,
            color=args.color,
            opacity=args.opacity,
            position=args.position,
            under=args.under,
        )
    else:
        writer = ops.watermark_image(
            reader,
            args.image,
            spec=args.pages,
            scale=args.scale,
            opacity=args.opacity,
            position=args.position,
            under=args.under,
        )
    return _done(args, writer, "watermarked")


def cmd_number(args):
    writer = ops.number_pages(
        _open(args),
        spec=args.pages,
        fmt=args.format,
        start=args.start,
        position=args.position,
        size=args.size,
        margin=args.margin,
        color=args.color,
    )
    return _done(args, writer, "numbered")


def cmd_encrypt(args):
    user = _password(args, "user_password", "user_password_env")
    owner = _password(args, "owner_password", "owner_password_env")
    if user is None and owner is None:
        raise Fail("give --user-password and/or --owner-password (or the *-env variants)")
    reader = ops.open_pdf(args.input, _password(args))
    writer = ops.encrypt(
        reader,
        user or "",
        owner,
        algorithm=args.algorithm,
        allow_print=not args.no_print,
        allow_copy=not args.no_copy,
        allow_modify=not args.no_modify,
    )
    return _done(args, writer, f"encrypted ({args.algorithm})")


def cmd_decrypt(args):
    pw = _password(args)
    if pw is None:
        raise Fail("give --password (or --password-env) to decrypt")
    reader = ops.open_pdf(args.input, pw)
    if not reader.is_encrypted:
        raise Fail(f"{args.input} is not encrypted")
    return _done(args, ops.decrypt(reader), "decrypted")


def cmd_meta(args):
    reader = _open(args)
    if args.meta_cmd == "show":
        data = ops.metadata(reader)
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        elif not data:
            print("(no document metadata)")
        else:
            width = max(len(k) for k in data)
            for k, v in data.items():
                print(f"{k.ljust(width)}  {v}")
        return 0
    if args.meta_cmd == "strip":
        return _done(args, ops.strip_metadata(reader), "stripped metadata")
    values: dict[str, str | None] = {}
    for field in ops.METADATA_FIELDS:
        v = getattr(args, field)
        if v is not None:
            values[field.capitalize()] = v
    for item in args.set or []:
        if "=" not in item:
            raise Fail(f"--set expects KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        values[k.strip()] = v
    for k in args.unset or []:
        values[k] = None
    if not values:
        raise Fail("nothing to change; use --title, --author, ..., --set KEY=VALUE or --unset KEY")
    return _done(args, ops.set_metadata(reader, values), "updated metadata")


def cmd_text(args):
    pages = ops.extract_text(_open(args), args.pages, layout=args.layout)
    chunks = []
    for n, text in pages:
        chunks.append(f"--- page {n} ---\n{text}" if args.page_markers else text)
    content = ("\n" if args.page_markers else "\f").join(chunks)
    if not content.endswith("\n"):
        content += "\n"
    if args.output and args.output != "-":
        Path(args.output).write_text(content, encoding="utf-8")
        if not args.quiet:
            print(f"text: wrote {args.output} ({len(pages)} pages)", file=sys.stderr)
    else:
        sys.stdout.write(content)
    return 0


def cmd_img2pdf(args):
    writer = ops.images_to_pdf(
        args.images, page_size=args.page_size, orientation=args.orientation, margin=args.margin, dpi=args.dpi
    )
    return _done(args, writer, f"converted {len(args.images)} image{'s' * (len(args.images) != 1)}")


def cmd_compress(args):
    result = ops.compress(
        args.input,
        args.output,
        password=_password(args),
        engine=args.engine,
        image_quality=args.image_quality,
        max_image_dpi=args.max_image_dpi,
    )
    if not args.quiet:
        pct = result.saved / result.before * 100 if result.before else 0
        msg = f"compress ({result.engine}): {_size(result.before)} -> {_size(result.after)} ({pct:.1f}% smaller)"
        if result.images_recompressed:
            msg += f", {result.images_recompressed} images recompressed"
        if result.kept_original:
            msg = f"compress ({result.engine}): could not make {args.input} smaller; copied it unchanged"
        print(msg, file=sys.stderr)
    return 0


def cmd_info(args):
    data = ops.info(args.input, _password(args))
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    print(f"File:        {data['file']} ({_size(data['bytes'])})")
    print(f"PDF version: {data['pdf_version']}")
    print(f"Pages:       {data['pages']}")
    print(f"Encrypted:   {'yes' if data['encrypted'] else 'no'}")
    for s in data["page_sizes"]:
        paper = f" {s['paper']}" if s["paper"] else ""
        print(
            f"Page size:   {s['width_pt']:g} x {s['height_pt']:g} pt ({s['width_mm']:g} x {s['height_mm']:g} mm)"
            f"{paper}, {s['pages']} page{'s' * (s['pages'] != 1)}"
        )
    print(f"Rotated:     {data['rotated_pages']} pages")
    print(f"Bookmarks:   {data['outline_items']}")
    print(f"Form fields: {data['form_fields']}")
    for k, v in data["metadata"].items():
        print(f"{(k + ':').ljust(12)} {v}")
    return 0


# --------------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-swiss",
        description="Swiss-army knife for PDF files: merge, split, rotate, extract, reorder, watermark, "
        "number, encrypt, decrypt, metadata, text, images to PDF and compression.",
    )
    parser.add_argument("--version", action="version", version=f"pdf-swiss {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="no progress messages on standard error")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def add(name: str, func, help_text: str, input_arg: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(func=func)
        if input_arg:
            p.add_argument("input", help="input PDF")
        return p

    p = add("merge", cmd_merge, "Concatenate PDFs (append :PAGES to a file to take only some pages)", False)
    p.add_argument("inputs", nargs="+", metavar="INPUT", help="PDF files, optionally file.pdf:1-3")
    _add_output(p)
    p.add_argument("--bookmarks", action="store_true", help="add a bookmark at the start of each input")
    _add_password(p)

    p = add("split", cmd_split, "Split into several files: by ranges, every N pages, or one file per page")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--ranges", help='one output per comma-separated range, e.g. "1-3,4-10,11-end"')
    g.add_argument("--every", type=int, metavar="N", help="one output every N pages (default 1)")
    p.add_argument("-d", "--output-dir", metavar="DIR", help="directory for the parts (default: current)")
    p.add_argument(
        "--pattern",
        default="{stem}-{n}.pdf",
        help="file name pattern; placeholders {stem} {n} {start} {end} {count} (default {stem}-{n}.pdf)",
    )
    _add_password(p)

    p = add("extract", cmd_extract, "Keep only some pages, in the order given")
    p.add_argument("-p", "--pages", required=True, help=PAGES_HELP)
    _add_output(p)
    _add_password(p)

    p = add("delete", cmd_delete, "Remove pages")
    p.add_argument("-p", "--pages", required=True, help=PAGES_HELP)
    _add_output(p)
    _add_password(p)

    p = add("reorder", cmd_reorder, "Put pages in a new order (pages left out are dropped)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--order", help='new order, e.g. "3,1,2,4-end"')
    g.add_argument("--reverse", action="store_true", help="reverse the page order")
    _add_output(p)
    _add_password(p)

    p = add("rotate", cmd_rotate, "Rotate pages clockwise by a multiple of 90 degrees")
    p.add_argument("-a", "--angle", type=int, default=90, help="degrees clockwise: 90, 180, 270, -90 (default 90)")
    p.add_argument("-p", "--pages", help=PAGES_HELP)
    _add_output(p)
    _add_password(p)

    p = add("watermark", cmd_watermark, "Stamp text or an image on pages")
    p.add_argument("--text", help="watermark text")
    p.add_argument("--image", metavar="FILE", help="watermark image (PNG with transparency, JPEG, ...)")
    p.add_argument("-p", "--pages", help=PAGES_HELP)
    p.add_argument("--position", default="center", choices=ops.POSITIONS, help="where to put it (default center)")
    p.add_argument("--opacity", type=float, default=0.3, help="0..1 (default 0.3)")
    p.add_argument("--size", type=float, help="text size in points (default: fit the page diagonal)")
    p.add_argument("--angle", type=float, help="text angle in degrees (default: page diagonal when centred)")
    p.add_argument("--color", default="#808080", help="text colour, #rrggbb or a name (default #808080)")
    p.add_argument("--scale", type=float, default=0.5, help="image width as a share of the page (default 0.5)")
    p.add_argument("--under", action="store_true", help="draw beneath the page content instead of on top")
    _add_output(p)
    _add_password(p)

    p = add("number", cmd_number, "Add page numbers")
    p.add_argument("-p", "--pages", help="pages to number (default all), e.g. 2-end to skip a cover")
    p.add_argument(
        "--format",
        default="{n}",
        help='label; placeholders {n} {total} {page} {pages}, e.g. "Page {n} of {total}" (default {n})',
    )
    p.add_argument("--start", type=int, default=1, help="number of the first numbered page (default 1)")
    p.add_argument("--position", default="bottom-center", choices=ops.POSITIONS, help="default bottom-center")
    p.add_argument("--size", type=float, default=10, help="font size in points (default 10)")
    p.add_argument("--margin", type=float, default=28, help="distance from the page edge in points (default 28)")
    p.add_argument("--color", default="black", help="#rrggbb or a name (default black)")
    _add_output(p)
    _add_password(p)

    p = add("encrypt", cmd_encrypt, "Password-protect a PDF (AES-256 by default)")
    p.add_argument("--user-password", metavar="PW", help='password needed to open the file ("-" to prompt)')
    p.add_argument("--user-password-env", metavar="VAR", help="read the user password from an environment variable")
    p.add_argument("--owner-password", metavar="PW", help="password that lifts the restrictions")
    p.add_argument("--owner-password-env", metavar="VAR", help="read the owner password from an environment variable")
    p.add_argument("--algorithm", default="AES-256", choices=("AES-256", "AES-128", "RC4-128"), help="default AES-256")
    p.add_argument("--no-print", action="store_true", help="ask readers not to allow printing")
    p.add_argument("--no-copy", action="store_true", help="ask readers not to allow copying text and images")
    p.add_argument("--no-modify", action="store_true", help="ask readers not to allow changes")
    _add_output(p)
    _add_password(p)

    p = add("decrypt", cmd_decrypt, "Remove the password from a PDF you can open")
    _add_output(p)
    _add_password(p)

    p = add("meta", cmd_meta, "View, edit or strip document metadata", False)
    msub = p.add_subparsers(dest="meta_cmd", metavar="<show|set|strip>", required=True)
    m = msub.add_parser("show", help="print metadata")
    m.add_argument("input")
    m.add_argument("--json", action="store_true", help="JSON output")
    _add_password(m)
    m = msub.add_parser("set", help="change metadata fields")
    m.add_argument("input")
    for field in ops.METADATA_FIELDS:
        m.add_argument(f"--{field}", metavar="TEXT", help=f"set /{field.capitalize()}")
    m.add_argument("--set", action="append", metavar="KEY=VALUE", help="set any field (repeatable)")
    m.add_argument("--unset", action="append", metavar="KEY", help="remove a field (repeatable)")
    _add_output(m)
    _add_password(m)
    m = msub.add_parser("strip", help="remove all document info and XMP metadata")
    m.add_argument("input")
    _add_output(m)
    _add_password(m)

    p = add("text", cmd_text, "Extract text (pages separated by form feeds)")
    p.add_argument("-p", "--pages", help=PAGES_HELP)
    p.add_argument("--layout", action="store_true", help="keep the visual layout (columns, spacing)")
    p.add_argument("--page-markers", action="store_true", help='print "--- page N ---" instead of form feeds')
    p.add_argument("-o", "--output", metavar="FILE", help="write to FILE instead of standard output")
    _add_password(p)

    p = add("img2pdf", cmd_img2pdf, "Turn images into a PDF, one page per image", False)
    p.add_argument("images", nargs="+", metavar="IMAGE", help="PNG, JPEG, TIFF, WebP, GIF, BMP, ...")
    p.add_argument(
        "--page-size",
        default="fit",
        help=f"fit (page = image size) or {', '.join(ops.PAPER)} (default fit)",
    )
    p.add_argument("--orientation", default="auto", choices=("auto", "portrait", "landscape"))
    p.add_argument("--margin", type=float, default=0, help="margin in points (default 0)")
    p.add_argument("--dpi", type=float, help="resolution for --page-size fit (default: from the image, else 96)")
    _add_output(p)

    p = add("compress", cmd_compress, "Make a PDF smaller (lossless by default)")
    p.add_argument(
        "--engine", default="auto", choices=("auto", "pypdf", "pikepdf"), help="default: pikepdf if installed"
    )
    p.add_argument("--image-quality", type=int, metavar="1-95", help="recompress RGB/grey images as JPEG (lossy)")
    p.add_argument("--max-image-dpi", type=float, metavar="DPI", help="downscale images wider than the page at DPI")
    _add_output(p)
    _add_password(p)

    p = add("info", cmd_info, "Pages, sizes, version, encryption, bookmarks, form fields and metadata")
    p.add_argument("--json", action="store_true", help="JSON output")
    _add_password(p)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except (Fail, ops.PdfSwissError) as exc:
        print(f"pdf-swiss: error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
