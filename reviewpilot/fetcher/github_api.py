from __future__ import annotations

import base64
import binascii
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}#{self.number}"


@dataclass(frozen=True)
class PullRequestMetadata:
    title: str
    body: str
    state: str
    draft: bool
    html_url: str
    base_ref: str
    head_ref: str
    author: str
    changed_files: int
    additions: int
    deletions: int
    head_sha: str = ""


@dataclass(frozen=True)
class ChangedFile:
    filename: str
    status: str
    additions: int
    deletions: int
    changes: int
    patch: str | None = None


@dataclass(frozen=True)
class PullRequestSnapshot:
    ref: PullRequestRef
    metadata: PullRequestMetadata
    commits: list[str] = field(default_factory=list)
    files: list[ChangedFile] = field(default_factory=list)
    diff: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class GitHubAPIError(RuntimeError):
    """Raised when GitHub returns an unsuccessful response."""


def parse_pr_url(url: str) -> PullRequestRef:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
        "github.com",
        "www.github.com",
    }:
        raise ValueError("Expected a github.com pull request URL")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 4 or parts[2] != "pull":
        raise ValueError("Expected a GitHub pull request URL")

    try:
        number = int(parts[3])
    except ValueError as exc:
        raise ValueError("Pull request number must be an integer") from exc

    return PullRequestRef(owner=parts[0], repo=parts[1], number=number)


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        timeout: float = 20.0,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def fetch_pull_request(self, ref: PullRequestRef) -> PullRequestSnapshot:
        import httpx

        headers = self._headers()
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout,
        ) as client:
            pr_data = await self._get_json(client, f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}")
            commits_data = await self._get_paginated_json(
                client,
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/commits",
            )
            files_data = await self._get_paginated_json(
                client,
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}/files",
            )
            diff = await self._get_text(
                client,
                f"/repos/{ref.owner}/{ref.repo}/pulls/{ref.number}",
                accept="application/vnd.github.v3.diff",
            )

        return PullRequestSnapshot(
            ref=ref,
            metadata=PullRequestMetadata(
                title=pr_data.get("title") or "",
                body=pr_data.get("body") or "",
                state=pr_data.get("state") or "",
                draft=bool(pr_data.get("draft")),
                html_url=pr_data.get("html_url") or "",
                base_ref=(pr_data.get("base") or {}).get("ref") or "",
                head_ref=(pr_data.get("head") or {}).get("ref") or "",
                head_sha=(pr_data.get("head") or {}).get("sha") or "",
                author=(pr_data.get("user") or {}).get("login") or "",
                changed_files=int(pr_data.get("changed_files") or 0),
                additions=int(pr_data.get("additions") or 0),
                deletions=int(pr_data.get("deletions") or 0),
            ),
            commits=[commit.get("sha", "") for commit in commits_data if commit.get("sha")],
            files=[
                ChangedFile(
                    filename=file_data.get("filename") or "",
                    status=file_data.get("status") or "",
                    additions=int(file_data.get("additions") or 0),
                    deletions=int(file_data.get("deletions") or 0),
                    changes=int(file_data.get("changes") or 0),
                    patch=file_data.get("patch"),
                )
                for file_data in files_data
            ],
            diff=diff,
        )

    async def fetch_changed_file_contents(self, snapshot: PullRequestSnapshot) -> dict[str, str]:
        import asyncio

        import httpx

        ref = snapshot.metadata.head_sha or snapshot.metadata.head_ref
        if not ref:
            return {}

        files_to_fetch = [
            f for f in snapshot.files
            if f.status != "removed" and f.filename
        ]
        if not files_to_fetch:
            return {}

        sem = asyncio.Semaphore(8)

        async def fetch_one(client: httpx.AsyncClient, changed_file: ChangedFile) -> tuple[str, str | None]:
            async with sem:
                data = await self._get_json(
                    client,
                    _contents_path(snapshot.ref, changed_file.filename),
                    params={"ref": ref},
                )
                return changed_file.filename, _decode_file_content(data)

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            results = await asyncio.gather(
                *[fetch_one(client, f) for f in files_to_fetch]
            )

        contents: dict[str, str] = {}
        for filename, content in results:
            if content is not None:
                contents[filename] = content
        return contents

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "ReviewPilot",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _get_json(
        self,
        client: Any,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = await client.get(path, headers=self._headers(), params=params)
        self._raise_for_status(response)
        data = response.json()
        if not isinstance(data, dict):
            raise GitHubAPIError(f"Expected object response from GitHub for {path}")
        return data

    async def _get_paginated_json(self, client: Any, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        per_page = 100
        while True:
            response = await client.get(
                path,
                headers=self._headers(),
                params={"page": page, "per_page": per_page},
            )
            self._raise_for_status(response)
            data = response.json()
            if not isinstance(data, list):
                raise GitHubAPIError(f"Expected list response from GitHub for {path}")
            items.extend(item for item in data if isinstance(item, dict))
            if len(data) < per_page:
                return items
            page += 1

    async def _get_text(self, client: Any, path: str, accept: str) -> str:
        response = await client.get(path, headers=self._headers(accept=accept))
        self._raise_for_status(response)
        return response.text

    async def _post_json(self, client: Any, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await client.post(path, headers=self._headers(), json=body)
        self._raise_for_status(response)
        data = response.json()
        if not isinstance(data, dict):
            raise GitHubAPIError(f"Expected object response from GitHub for {path}")
        return data

    async def post_issue_comment(self, ref: PullRequestRef, body: str) -> dict[str, Any]:
        import httpx

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        ) as client:
            return await self._post_json(
                client,
                f"/repos/{ref.owner}/{ref.repo}/issues/{ref.number}/comments",
                {"body": body},
            )

    def _raise_for_status(self, response: Any) -> None:
        if response.status_code < 400:
            return
        message = response.text[:300] if response.text else response.reason_phrase
        raise GitHubAPIError(f"GitHub API returned {response.status_code}: {message}")


def _contents_path(ref: PullRequestRef, file_path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in file_path.split("/"))
    return f"/repos/{ref.owner}/{ref.repo}/contents/{encoded_path}"


def _decode_file_content(data: dict[str, Any]) -> str | None:
    if data.get("type") != "file" or data.get("encoding") != "base64":
        return None
    raw_content = data.get("content")
    if not isinstance(raw_content, str):
        return None

    try:
        decoded = base64.b64decode(raw_content, validate=False)
        return decoded.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None
