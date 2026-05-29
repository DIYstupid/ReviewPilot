from __future__ import annotations

from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from reviewpilot.analyzer.llm import ChatMessage, ChatCompletionClient, LLMRequest
from reviewpilot.config import get_settings
from reviewpilot.context.builder import ReviewContext


PROMPT_ENV = Environment(
    loader=FileSystemLoader("reviewpilot/analyzer/prompts"),
    undefined=StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass(frozen=True)
class SummaryResult:
    content: str
    model: str = "offline"
    cached: bool = False


def render_summary_prompt(context: ReviewContext) -> str:
    template = PROMPT_ENV.get_template("summary.j2")
    return template.render(context=context, fallback_summary=summarize_context(context))


def summarize_context(context: ReviewContext) -> str:
    files = [diff_file.path for diff_file in context.diff_files]
    file_part = ", ".join(files[:5]) if files else "no changed files parsed"
    if len(files) > 5:
        file_part += f", and {len(files) - 5} more"

    hunk_count = len(context.hunks)
    symbol_names = [symbol.name for symbol in context.symbols[:5]]
    symbol_part = ", ".join(symbol_names) if symbol_names else "no changed symbols detected"

    return (
        f"{context.pr_title}. "
        f"Changed files: {file_part}. "
        f"Diff hunks: {hunk_count}. "
        f"Symbols: {symbol_part}."
    )


async def generate_summary(
    context: ReviewContext,
    client: ChatCompletionClient | None = None,
) -> SummaryResult:
    settings = get_settings()
    if client is None:
        return SummaryResult(content=summarize_context(context))

    request = LLMRequest(
        model=settings.deepseek_model,
        temperature=0.3,
        messages=[
            ChatMessage(role="system", content="You are ReviewPilot's summary agent."),
            ChatMessage(role="user", content=render_summary_prompt(context)),
        ],
        metadata={"agent": "summary"},
    )
    response = await client.complete(request)
    return SummaryResult(content=response.content, model=response.model, cached=response.cached)
