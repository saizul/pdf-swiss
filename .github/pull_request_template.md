## What does this pull request do?

<!-- One or two sentences. Link the issue: "Closes #123". -->

## Type

- [ ] New command or option
- [ ] Bug fix
- [ ] Documentation

## Checklist

- [ ] Tests added or updated (`pytest` passes; test PDFs and images are generated in the test, no binary fixtures, no network)
- [ ] `ruff check . && ruff format --check .` passes
- [ ] The operation lives in `ops.py` (usable as a library); `cli.py` only parses arguments
- [ ] Works without pikepdf installed (optional features degrade with a clear message)
- [ ] Passwords are never printed or logged
- [ ] README command reference updated
- [ ] CHANGELOG.md updated under "Unreleased"
