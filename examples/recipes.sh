#!/usr/bin/env sh
# Everyday recipes. Each line is independent; copy the ones you need.
set -eu

# Combine a cover, pages 2-5 of a report and an appendix, with a bookmark per file
pdf-swiss merge cover.pdf report.pdf:2-5 appendix.pdf --bookmarks -o handout.pdf

# One file per chapter
pdf-swiss split book.pdf --ranges 1-12,13-40,41-end -d chapters --pattern "{stem}-ch{n}.pdf"

# Scanned the pages upside down? Rotate the even pages and fix the order of a duplex scan
pdf-swiss rotate scan.pdf -a 180 -p even -o scan.pdf
pdf-swiss reorder scan.pdf --order 1,3,5,2,4,6 -o scan.pdf

# "DRAFT" across every page, and a logo in the top-right corner of the first page
pdf-swiss watermark proposal.pdf --text DRAFT -o proposal-draft.pdf
pdf-swiss watermark proposal-draft.pdf --image logo.png -p 1 --position top-right --scale 0.2 --opacity 1 -o proposal-draft.pdf

# "Page 1 of 9" at the bottom right, skipping the cover
pdf-swiss number thesis.pdf -p 2-end --format "Page {n} of {total}" --position bottom-right -o thesis.pdf

# Send a password-protected copy (the password comes from the environment, not the command line)
export PDF_PASSWORD='change-me'
pdf-swiss encrypt invoice.pdf --user-password-env PDF_PASSWORD --no-modify -o invoice-protected.pdf

# Remove author, software and dates before publishing
pdf-swiss meta strip whitepaper.pdf -o whitepaper-public.pdf
pdf-swiss meta set whitepaper-public.pdf --title "Whitepaper 2026" -o whitepaper-public.pdf

# Phone photos of receipts to one A4 PDF, then shrink it
pdf-swiss img2pdf IMG_*.jpg --page-size a4 --margin 20 -o receipts.pdf
pdf-swiss compress receipts.pdf --image-quality 60 --max-image-dpi 150 -o receipts-small.pdf

# Search a folder of PDFs for a word
for f in *.pdf; do pdf-swiss text "$f" | grep -qi "invoice" && echo "$f"; done
