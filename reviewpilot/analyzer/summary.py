from reviewpilot.context.builder import ReviewContext


def summarize_context(context: ReviewContext) -> str:
    return context.pr_title
