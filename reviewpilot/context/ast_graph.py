from dataclasses import dataclass, field


@dataclass(frozen=True)
class SymbolContext:
    name: str
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)
