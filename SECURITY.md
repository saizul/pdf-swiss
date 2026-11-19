# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | yes |

## What counts as a vulnerability

- A password passed to pdf-swiss appearing in output, error messages or the written file
- `encrypt` producing a file that opens without the password, or silently using a weaker
  algorithm than requested
- `meta strip` leaving document information or XMP metadata behind
- Writing outside the requested output path (for example through `split --pattern`)
- A crafted PDF or image making pdf-swiss execute code

Crashes, very slow processing or high memory use on malformed PDFs are usually bugs in the
underlying libraries (pypdf, Pillow, pikepdf). Report them as normal issues here, and upstream
if you can, unless they are exploitable.

## Reporting

Please **do not** open a public issue. Use
[GitHub private vulnerability reporting](https://github.com/saizul/pdf-swiss/security/advisories/new)
with the version, the impact and steps to reproduce. Do not attach confidential documents.

You will get an answer within 5 working days. Fixes are released as soon as
possible and credited in the changelog unless you prefer otherwise.

## Notes for users

- Prefer `--password-env VAR` or `--password -` (prompt) over `--password PW`: command line
  arguments are visible to other users of the machine and end up in shell history.
- PDF permissions (`--no-print`, `--no-copy`, `--no-modify`) are honoured by well-behaved
  readers only. Anyone with the owner password, or a tool that ignores the flags, can bypass
  them. Only the user password actually protects the content.
- `meta strip` removes the document information dictionary and XMP metadata. Other places can
  still identify a document: text, images, form fields, embedded files and attachments.
