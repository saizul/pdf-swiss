"""Use pdf-swiss as a library: every command is a function in ``pdf_swiss.ops``.

Run from a folder that contains a.pdf and b.pdf:

    python examples/library_usage.py
"""

from pdf_swiss import ops

# Merge two files, keeping only the first three pages of the second one.
merged = ops.merge(["a.pdf", "b.pdf:1-3"], bookmarks=True)
ops.save(merged, "merged.pdf")

# Stamp and number the result. Each operation takes a reader and returns a writer.
reader = ops.open_pdf("merged.pdf")
ops.save(ops.watermark_text(reader, "INTERNAL", opacity=0.15), "merged.pdf")
ops.save(ops.number_pages(ops.open_pdf("merged.pdf"), fmt="{n} / {total}"), "merged.pdf")

# Split into files of 10 pages each.
for n, (pages, writer) in enumerate(ops.split(ops.open_pdf("merged.pdf"), every=10), 1):
    ops.save(writer, f"part-{n}.pdf")
    print(f"part-{n}.pdf: pages {pages[0] + 1}-{pages[-1] + 1}")

# Text of every page.
for number, text in ops.extract_text(ops.open_pdf("merged.pdf")):
    print(number, text[:60].replace("\n", " "))

print(ops.info("merged.pdf")["pages"], "pages")
