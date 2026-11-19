import pytest

from pdf_swiss.pages import PageSpecError, chunks, describe, parse_groups, parse_pages


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (None, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]),
        ("", list(range(10))),
        ("all", list(range(10))),
        ("1", [0]),
        ("1-3", [0, 1, 2]),
        ("3-1", [2, 1, 0]),
        ("8-", [7, 8, 9]),
        ("-2", [0, 1]),
        ("end", [9]),
        ("last", [9]),
        ("end-1", [8]),
        ("8-end", [7, 8, 9]),
        ("5-end-3", [4, 5, 6]),
        ("odd", [0, 2, 4, 6, 8]),
        ("even", [1, 3, 5, 7, 9]),
        ("3,1,2", [2, 0, 1]),
        ("1,1", [0, 0]),
        (" 2 - 3 , 10 ", [1, 2, 9]),
    ],
)
def test_parse_pages(spec, expected):
    assert parse_pages(spec, 10) == expected


@pytest.mark.parametrize("spec", ["0", "11", "1-11", "abc", "1--2", ",", "end-10", "2.5"])
def test_invalid_specs(spec):
    with pytest.raises(PageSpecError):
        parse_pages(spec, 10)


def test_no_pages():
    with pytest.raises(PageSpecError):
        parse_pages(None, 0)


def test_groups_and_chunks():
    assert parse_groups("1-3,4,5-", 6) == [[0, 1, 2], [3], [4, 5]]
    assert chunks(5, 2) == [[0, 1], [2, 3], [4]]
    with pytest.raises(PageSpecError):
        chunks(5, 0)
    with pytest.raises(PageSpecError):
        parse_groups("", 3)


def test_describe():
    assert describe([0, 1, 2, 6, 8, 9]) == "1-3,7,9-10"
    assert describe([]) == ""
    assert describe([4]) == "5"
