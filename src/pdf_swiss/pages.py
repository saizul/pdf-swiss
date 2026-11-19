"""Page selection syntax shared by every command.

Pages are 1-based. A spec is a comma-separated list of items:

``5``            one page
``2-7``          a range (inclusive); ``7-2`` is the same range in reverse order
``4-`` / ``-3``  open ranges (to the end / from the start)
``end``/``last`` the last page; ``end-1`` the one before it
``odd``/``even`` every odd / even page
``all``          every page
"""

from __future__ import annotations

import re

_ITEM = re.compile(r"^(?P<a>[^-]*)-(?P<b>.*)$")
_REF = re.compile(r"^(?:(?P<num>\d+)|(?P<end>end|last|z)(?:-(?P<back>\d+))?)$")


class PageSpecError(ValueError):
    """Raised for malformed page specs or pages outside the document."""


def _ref(token: str, total: int) -> int:
    token = token.strip().lower()
    m = _REF.match(token)
    if not m:
        raise PageSpecError(f"invalid page reference {token!r}")
    if m["num"]:
        page = int(m["num"])
    else:
        page = total - int(m["back"] or 0)
    if not 1 <= page <= total:
        raise PageSpecError(f"page {token} is out of range (document has {total} page{'s' * (total != 1)})")
    return page


def parse_item(item: str, total: int) -> list[int]:
    """Return 0-based page indexes for one item of a spec."""
    item = item.strip().lower()
    if not item:
        raise PageSpecError("empty page item")
    if item == "all":
        return list(range(total))
    if item == "odd":
        return list(range(0, total, 2))
    if item == "even":
        return list(range(1, total, 2))
    if _REF.match(item):
        return [_ref(item, total) - 1]
    m = _ITEM.match(item)
    if not m:
        raise PageSpecError(f"invalid page item {item!r}")
    a_tok, b_tok = m["a"], m["b"]
    # "end-2" is a reference, not a range; handled above. Here: "a-b".
    a = _ref(a_tok, total) if a_tok.strip() else 1
    b = _ref(b_tok, total) if b_tok.strip() else total
    step = 1 if b >= a else -1
    return [p - 1 for p in range(a, b + step, step)]


def parse_pages(spec: str | None, total: int) -> list[int]:
    """Parse a spec into 0-based indexes, keeping order and duplicates. ``None`` means all."""
    if total <= 0:
        raise PageSpecError("the document has no pages")
    if spec is None or not str(spec).strip():
        return list(range(total))
    out: list[int] = []
    for item in str(spec).split(","):
        out.extend(parse_item(item, total))
    return out


def parse_groups(spec: str, total: int) -> list[list[int]]:
    """Parse a spec into groups, one per comma-separated item (used by ``split --ranges``)."""
    if not spec or not spec.strip():
        raise PageSpecError("no ranges given")
    return [parse_item(item, total) for item in spec.split(",")]


def chunks(total: int, size: int) -> list[list[int]]:
    """Split ``total`` pages into groups of ``size`` (the last one may be shorter)."""
    if size < 1:
        raise PageSpecError("--every must be at least 1")
    return [list(range(i, min(i + size, total))) for i in range(0, total, size)]


def describe(indexes: list[int]) -> str:
    """Compact 1-based description such as ``1-3,7``."""
    if not indexes:
        return ""
    parts = []
    start = prev = indexes[0]
    for i in [*indexes[1:], None]:
        if i is not None and i == prev + 1:
            prev = i
            continue
        parts.append(str(start + 1) if start == prev else f"{start + 1}-{prev + 1}")
        if i is not None:
            start = prev = i
    return ",".join(parts)
