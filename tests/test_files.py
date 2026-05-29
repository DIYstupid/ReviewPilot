from reviewpilot.context.files import build_file_context, build_file_contexts, trim_text


def test_trim_text_returns_original_when_under_budget() -> None:
    assert trim_text("abc", 5) == "abc"


def test_trim_text_truncates_to_budget() -> None:
    assert trim_text("abcdef", 3) == "abc"


def test_trim_text_rejects_negative_budget() -> None:
    try:
        trim_text("abc", -1)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected negative budget to be rejected")


def test_build_file_context_tracks_truncation_metadata() -> None:
    context = build_file_context("app.py", "abcdef", max_chars=3)

    assert context.path == "app.py"
    assert context.content == "abc"
    assert context.original_chars == 6
    assert context.included_chars == 3
    assert context.truncated is True


def test_build_file_contexts_applies_per_file_and_total_budget() -> None:
    contexts = build_file_contexts(
        {
            "b.py": "b" * 10,
            "a.py": "a" * 10,
            "c.py": "c" * 10,
        },
        max_chars_per_file=6,
        max_total_chars=10,
    )

    assert list(contexts) == ["a.py", "b.py", "c.py"]
    assert contexts["a.py"].included_chars == 6
    assert contexts["b.py"].included_chars == 4
    assert contexts["c.py"].included_chars == 0
