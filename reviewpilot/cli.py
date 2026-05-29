from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence

from reviewpilot.fetcher.github_api import GitHubAPIError, GitHubClient, parse_pr_url


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reviewpilot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch GitHub pull request context")
    fetch_parser.add_argument("pr_url", help="GitHub pull request URL")
    fetch_parser.add_argument(
        "--format",
        choices=("json", "diff"),
        default="json",
        help="Output format",
    )
    fetch_parser.add_argument("--token", default=None, help="GitHub token")
    fetch_parser.add_argument(
        "--base-url",
        default="https://api.github.com",
        help="GitHub API base URL",
    )
    return parser


async def run_fetch(args: argparse.Namespace) -> int:
    ref = parse_pr_url(args.pr_url)
    token = args.token or os.environ.get("GITHUB_PAT") or os.environ.get("GITHUB_TOKEN")
    client = GitHubClient(token=token, base_url=args.base_url)
    snapshot = await client.fetch_pull_request(ref)
    if args.format == "diff":
        print(snapshot.diff)
    else:
        print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "fetch":
            return asyncio.run(run_fetch(args))
    except (GitHubAPIError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    parser.error(f"unknown command: {args.command}")
    return 2
