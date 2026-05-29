from reviewpilot.context.ast_graph import SymbolContext


def test_symbol_context_defaults_to_empty_edges() -> None:
    symbol = SymbolContext(name="parse_pr_url")
    assert symbol.callers == []
    assert symbol.callees == []
