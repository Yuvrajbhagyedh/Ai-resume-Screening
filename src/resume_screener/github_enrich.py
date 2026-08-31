"""GitHub public API enrichment.

Every failure mode -- missing profile (404), rate limiting (403), network
error, timeout, malformed URL -- is caught here and mapped to a `status` on
`GitHubEnrichment`. None of it may ever propagate and crash the batch.
"""

from __future__ import annotations

import logging

import httpx

from resume_screener.config import Settings
from resume_screener.models import GitHubEnrichment, GitHubRepoSummary

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def _extract_username(github_url: str) -> str | None:
    parts = github_url.rstrip("/").split("/")
    return parts[-1] if parts and parts[-1] else None


def enrich(github_url: str | None, settings: Settings) -> GitHubEnrichment:
    if not github_url:
        return GitHubEnrichment(status="no_url")
    if not settings.github_enrichment_enabled:
        return GitHubEnrichment(status="disabled")

    username = _extract_username(github_url)
    if not username:
        return GitHubEnrichment(status="error", error_message="Could not parse username from URL")

    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    try:
        with httpx.Client(timeout=settings.github_timeout_seconds, headers=headers) as client:
            user_resp = client.get(f"{GITHUB_API_BASE}/users/{username}")

            if user_resp.status_code == 404:
                return GitHubEnrichment(status="not_found", username=username)
            if user_resp.status_code == 403 and "rate limit" in user_resp.text.lower():
                return GitHubEnrichment(status="rate_limited", username=username)
            user_resp.raise_for_status()
            user_data = user_resp.json()

            top_repos: list[GitHubRepoSummary] = []
            repos_resp = client.get(
                f"{GITHUB_API_BASE}/users/{username}/repos",
                params={"sort": "updated", "per_page": 10},
            )
            if repos_resp.status_code == 200:
                for repo in repos_resp.json():
                    top_repos.append(
                        GitHubRepoSummary(
                            name=repo.get("name", ""),
                            stars=repo.get("stargazers_count", 0),
                            language=repo.get("language"),
                            description=repo.get("description"),
                            fork=repo.get("fork", False),
                        )
                    )
            top_repos.sort(key=lambda r: r.stars, reverse=True)

            return GitHubEnrichment(
                status="ok",
                username=username,
                public_repos=user_data.get("public_repos"),
                followers=user_data.get("followers"),
                account_created_at=user_data.get("created_at"),
                top_repos=top_repos[:5],
            )
    except httpx.TimeoutException as exc:
        logger.warning("GitHub enrichment timed out for %s: %s", username, exc)
        return GitHubEnrichment(status="error", username=username, error_message="Request timed out")
    except httpx.HTTPError as exc:
        logger.warning("GitHub enrichment HTTP error for %s: %s", username, exc)
        return GitHubEnrichment(status="error", username=username, error_message=str(exc))
    except Exception as exc:  # noqa: BLE001 -- enrichment must never crash the batch
        logger.warning("GitHub enrichment failed unexpectedly for %s: %s", username, exc)
        return GitHubEnrichment(status="error", username=username, error_message=str(exc))
