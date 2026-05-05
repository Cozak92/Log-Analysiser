from app.utils.log_parser import parse_log


def test_parse_log_handles_empty_input_gracefully() -> None:
    parsed = parse_log("")

    assert parsed.lines == ["<empty log input>"]
    assert parsed.parser_notes


def test_parse_log_extracts_status_and_stack_trace() -> None:
    parsed = parse_log(
        "status=500\nTraceback (most recent call last):\n  File \"app.py\", line 1, in <module>\nValueError: boom"
    )

    assert parsed.has_stack_trace is True
    assert parsed.http_statuses == [500]

