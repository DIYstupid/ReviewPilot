from reviewpilot.context.ast_graph import SymbolContext, build_symbol_contexts, extract_python_symbols
from reviewpilot.context.diff import parse_unified_diff


def test_symbol_context_defaults_to_empty_edges() -> None:
    symbol = SymbolContext(name="parse_pr_url")
    assert symbol.callers == []
    assert symbol.callees == []


def test_extract_python_symbols_finds_functions_classes_and_callees() -> None:
    content = """class Service:
    def run(self):
        return helper()

def helper():
    print("ok")
"""

    symbols = extract_python_symbols(content)

    assert [symbol.name for symbol in symbols] == ["Service", "run", "helper"]
    assert symbols[0].kind == "class"
    assert "helper" in symbols[0].callees
    assert "print" in symbols[2].callees


def test_build_symbol_contexts_selects_changed_python_symbols() -> None:
    content = """def untouched():
    return 1

def changed():
    return helper()

def helper():
    return 2
"""
    diff_files = parse_unified_diff(
        """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -4,2 +4,2 @@
 def changed():
-    return 1
+    return helper()
"""
    )

    contexts = build_symbol_contexts({"app.py": content}, diff_files[0].hunks)

    assert len(contexts) == 1
    assert contexts[0].name == "changed"
    assert contexts[0].file_path == "app.py"
    assert contexts[0].start_line == 4
    assert contexts[0].end_line == 5
    assert contexts[0].callees == ["helper"]
