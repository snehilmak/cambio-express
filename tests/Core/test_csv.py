"""Tests for the shared CSV-construction helper."""
from api.Core.Csv import build_csv


def test_build_csv_with_headers_and_rows():
    result = build_csv(
        ["A", "B", "C"],
        [[1, 2, 3], [4, 5, 6]],
    )
    lines = result.strip().split("\r\n")
    assert lines[0] == "A,B,C"
    assert lines[1] == "1,2,3"
    assert lines[2] == "4,5,6"


def test_build_csv_empty_rows_returns_header_only():
    result = build_csv(["A", "B"], [])
    lines = result.strip().split("\r\n")
    assert lines == ["A,B"]


def test_build_csv_accepts_generator():
    rows = ((i, i * 2) for i in range(3))
    result = build_csv(["x", "y"], rows)
    lines = result.strip().split("\r\n")
    assert lines == ["x,y", "0,0", "1,2", "2,4"]


def test_build_csv_handles_string_values_with_commas():
    """csv.writer quotes strings containing commas."""
    result = build_csv(
        ["name", "address"],
        [["Doe, Jane", "1 Main St, Apt 2"]],
    )
    lines = result.strip().split("\r\n")
    assert lines[1] == '"Doe, Jane","1 Main St, Apt 2"'


def test_build_csv_handles_mixed_types():
    """Numbers, strings, None, floats all get serialized."""
    result = build_csv(
        ["a", "b", "c", "d"],
        [["text", 42, 3.14, None]],
    )
    lines = result.strip().split("\r\n")
    assert lines[1] == "text,42,3.14,"


def test_build_csv_preserves_row_order():
    result = build_csv(
        ["i"],
        [[i] for i in [3, 1, 2]],
    )
    lines = result.strip().split("\r\n")
    assert lines == ["i", "3", "1", "2"]


def test_build_csv_with_unicode():
    result = build_csv(
        ["name"],
        [["López"], ["日本語"], ["café"]],
    )
    assert "López" in result
    assert "日本語" in result
    assert "café" in result
