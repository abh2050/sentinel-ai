"""
GitHub Pull Request Clients

Two implementations behind one interface:

  * `SimulatedGitHubClient` fabricates a PR reference. It is the demo default
    and makes no network calls.
  * `RestGitHubClient` performs the real sequence against the GitHub REST API:
    resolve base -> create branch -> commit files -> open pull request.

The agent depends on the interface, not on either implementation, so moving
from demo to production is a configuration change rather than a code change.

Note what is deliberately absent: there is no `merge_pull_request` method.
The safety covenant forbids autonomous merges, and the client simply offers no
way to perform one. A policy that can be violated by calling a different method
is weaker than one enforced by the absence of the method.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Dict, Optional, Protocol, runtime_checkable


class GitHubError(RuntimeError):
    """Raised when the GitHub API rejects a request or is unreachable."""


@dataclass
class PullRequestRef:
    """Identity of a pull request, real or simulated."""
    number: int
    url: str
    branch: str
    simulated: bool = False


@runtime_checkable
class GitHubClient(Protocol):
    """What the remediation workflow needs from a code host."""

    def open_pull_request(
        self,
        *,
        branch: str,
        title: str,
        body: str,
        commit_message: str,
        file_changes: Dict[str, str],
    ) -> PullRequestRef:
        """
        Create `branch`, commit `file_changes` onto it, and open a PR.

        `file_changes` maps repository-relative path to complete new file
        content. Full content rather than a patch: the GitHub contents API
        writes whole files, and resolving a patch against a moving base is a
        source of silent corruption.
        """
        ...


class SimulatedGitHubClient:
    """
    Produces a plausible PR reference without touching the network.

    Used for the demo and for tests. The returned ref is marked `simulated`
    so callers and the UI can be honest about what happened.
    """

    def __init__(self, repository: str = "your-org/your-ai-platform"):
        self.repository = repository

    def open_pull_request(
        self,
        *,
        branch: str,
        title: str,
        body: str,
        commit_message: str,
        file_changes: Dict[str, str],
    ) -> PullRequestRef:
        number = int(time.time()) % 900 + 100
        return PullRequestRef(
            number=number,
            url=f"https://github.com/{self.repository}/pull/{number}",
            branch=branch,
            simulated=True,
        )


class RestGitHubClient:
    """
    Real pull request creation via the GitHub REST API.

    Requires a token with `contents: write` and `pull_requests: write` on the
    target repository (classic PATs: the `repo` scope). Works against
    github.com or GitHub Enterprise by pointing `api_url` at the right host.
    """

    def __init__(
        self,
        token: str,
        repository: str,
        base_branch: str = "main",
        api_url: str = "https://api.github.com",
        timeout_seconds: float = 20.0,
    ):
        if "/" not in repository:
            raise ValueError(f"repository must be 'owner/name', got {repository!r}")
        self.token = token
        self.repository = repository
        self.base_branch = base_branch
        self.api_url = api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    # -- HTTP plumbing ------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        # Imported lazily so the simulated path never requires the dependency.
        import httpx

        url = f"{self.api_url}{path}"
        try:
            response = httpx.request(
                method,
                url,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a domain error
            raise GitHubError(f"{method} {path} failed to reach GitHub: {exc}") from exc

        if response.status_code >= 400:
            # GitHub's error body explains far more than the status alone
            # (bad scope, protected branch, branch already exists).
            detail = response.text[:400]
            raise GitHubError(
                f"{method} {path} returned {response.status_code}: {detail}"
            )

        if not response.content:
            return {}
        return response.json()

    # -- PR creation sequence ----------------------------------------------

    def open_pull_request(
        self,
        *,
        branch: str,
        title: str,
        body: str,
        commit_message: str,
        file_changes: Dict[str, str],
    ) -> PullRequestRef:
        if not file_changes:
            raise GitHubError("refusing to open a pull request with no file changes")

        repo_path = f"/repos/{self.repository}"

        base_sha = self._resolve_base_sha(repo_path)
        self._create_branch(repo_path, branch, base_sha)

        for file_path, content in file_changes.items():
            self._commit_file(repo_path, branch, file_path, content, commit_message)

        pr = self._request(
            "POST",
            f"{repo_path}/pulls",
            {
                "title": title,
                "body": body,
                "head": branch,
                "base": self.base_branch,
                "maintainer_can_modify": True,
            },
        )

        return PullRequestRef(
            number=pr["number"],
            url=pr["html_url"],
            branch=branch,
            simulated=False,
        )

    def _resolve_base_sha(self, repo_path: str) -> str:
        ref = self._request("GET", f"{repo_path}/git/ref/heads/{self.base_branch}")
        try:
            return ref["object"]["sha"]
        except (KeyError, TypeError) as exc:
            raise GitHubError(
                f"could not resolve base branch '{self.base_branch}' on {self.repository}"
            ) from exc

    def _create_branch(self, repo_path: str, branch: str, base_sha: str) -> None:
        try:
            self._request(
                "POST",
                f"{repo_path}/git/refs",
                {"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
        except GitHubError as exc:
            # A repeat incident reuses the branch name. Reusing an existing
            # branch is correct here; any other failure is not ours to swallow.
            if "already exists" not in str(exc).lower():
                raise

    def _commit_file(
        self,
        repo_path: str,
        branch: str,
        file_path: str,
        content: str,
        commit_message: str,
    ) -> None:
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload = {
            "message": commit_message,
            "content": encoded,
            "branch": branch,
        }

        # Updating an existing file requires its current blob SHA; creating a
        # new one requires the field to be absent.
        existing_sha = self._existing_blob_sha(repo_path, file_path, branch)
        if existing_sha:
            payload["sha"] = existing_sha

        self._request("PUT", f"{repo_path}/contents/{file_path}", payload)

    def _existing_blob_sha(self, repo_path: str, file_path: str, branch: str) -> Optional[str]:
        try:
            existing = self._request(
                "GET", f"{repo_path}/contents/{file_path}?ref={branch}"
            )
        except GitHubError:
            return None  # File does not exist on this branch yet.
        return existing.get("sha") if isinstance(existing, dict) else None


def build_github_client(settings=None) -> GitHubClient:
    """
    Select a client from deployment settings.

    Falls back to the simulated client when GitHub is not fully configured, so
    a partial configuration degrades to a working demo rather than crashing the
    incident pipeline mid-remediation.
    """
    if settings is None:
        from sentinel_core.settings import settings as default_settings
        settings = default_settings

    gh = settings.github
    if not gh.is_configured:
        return SimulatedGitHubClient()

    return RestGitHubClient(
        token=gh.token,
        repository=gh.repository,
        base_branch=gh.base_branch,
        api_url=gh.api_url,
    )
