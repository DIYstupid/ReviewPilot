from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence

from reviewpilot.analyzer.llm import LLMConfigurationError
from reviewpilot.fetcher.github_api import (
    GitHubAPIError,
    GitHubClient,
    parse_pr_url,
)
from reviewpilot.language import normalize_report_language
from reviewpilot.render import render_comment_body, render_report_markdown
from reviewpilot.review_service import (
    ReviewConfigurationError,
    create_configured_review_job,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reviewpilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_fetch_parser(subparsers)
    _add_review_parser(subparsers)
    return parser


def _add_fetch_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("fetch", help="Fetch GitHub pull request context")
    p.add_argument("pr_url", help="GitHub pull request URL")
    p.add_argument("--format", choices=("json", "diff"), default="json", help="Output format")
    p.add_argument("--token", default=None, help="GitHub token")
    p.add_argument("--base-url", default="https://api.github.com", help="GitHub API base URL")


def _add_review_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("review", help="Run a full review pipeline on a PR")
    p.add_argument("pr_url", help="GitHub pull request URL")
    p.add_argument(
        "--format", choices=("markdown", "json"), default="markdown", help="Output format"
    )
    p.add_argument("--out", default=None, metavar="PATH", help="Write output to file instead of stdout")
    p.add_argument("--token", default=None, help="GitHub token")
    p.add_argument("--lang", choices=("en", "zh"), default="en", help="Report language")
    p.add_argument("--post-comment", action="store_true", help="Post review summary as a PR comment")


def resolve_token(args_token: str | None) -> str | None:
    return args_token or os.environ.get("GITHUB_PAT") or os.environ.get("GITHUB_TOKEN")


async def run_fetch(args: argparse.Namespace) -> int:
    ref = parse_pr_url(args.pr_url)
    token = resolve_token(args.token)
    client = GitHubClient(token=token, base_url=args.base_url)
    snapshot = await client.fetch_pull_request(ref)
    if args.format == "diff":
        print(snapshot.diff)
    else:
        print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
    return 0


async def run_review(args: argparse.Namespace) -> int:
    token = resolve_token(args.token)
    report_language = normalize_report_language(args.lang)
    job = await create_configured_review_job(
        args.pr_url,
        github_token=token,
        report_language=report_language,
    )
    if job.report is None:
        print("error: review completed but no report was produced", file=sys.stderr)
        return 1

    output = (
        job.report.model_dump_json(indent=2)
        if args.format == "json"
        else render_report_markdown(job.report, report_language=report_language)
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Report saved to {args.out}", file=sys.stderr)
    else:
        print(output)

    if args.post_comment:
        ref = parse_pr_url(args.pr_url)
        if not token:
            print("error: --post-comment requires a GitHub token", file=sys.stderr)
            return 1
        body = render_comment_body(job.report, report_language=report_language)
        client = GitHubClient(token=token)
        comment = await client.post_issue_comment(ref, body)
        print(
            f"Comment posted: {comment.get('html_url', '')}",
            file=sys.stderr,
        )

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "fetch":
            return asyncio.run(run_fetch(args))
        if args.command == "review":
            return asyncio.run(run_review(args))
    except (GitHubAPIError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (LLMConfigurationError, ReviewConfigurationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2
