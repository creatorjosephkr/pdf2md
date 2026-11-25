"""GitHub Releases update checker for PDF 얼개 (PDF Eolgae)."""

from __future__ import annotations

import json
import platform
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from pdf_convert_engine import __version__
from pdf_convert_engine.server.models import UpdateCheckResponse

GITHUB_OWNER = "creatorjosephkr"
GITHUB_REPO = "pdf2md"
REPO_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
RELEASES_PAGE_URL = f"{REPO_URL}/releases"
LATEST_RELEASE_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_LIST_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases?per_page=5"

_SEMVER_RE = re.compile(
    r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)


def normalize_version(raw: str | None) -> str:
    if not raw:
        return "0.0.0"
    cleaned = raw.strip()
    if cleaned.lower().startswith("v"):
        cleaned = cleaned[1:]
    return cleaned or "0.0.0"


def parse_semver(raw: str | None) -> tuple[tuple[int, int, int], bool, tuple[tuple[int, int | str], ...]]:
    """Return comparable semver key: ((major, minor, patch), is_stable, pre_parts)."""
    s = (raw or "").strip()
    m = _SEMVER_RE.match(s)
    if not m:
        nums = [int(x) for x in re.findall(r"\d+", s)[:3]]
        while len(nums) < 3:
            nums.append(0)
        return ((nums[0], nums[1], nums[2]), True, ())

    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    pre_raw = m.group(4)
    if not pre_raw:
        return ((major, minor, patch), True, ())

    pre_parts: list[tuple[int, int | str]] = []
    for part in pre_raw.split("."):
        if part.isdigit():
            pre_parts.append((0, int(part)))
        else:
            pre_parts.append((1, part.lower()))
    return ((major, minor, patch), False, tuple(pre_parts))


def is_newer_version(latest: str, current: str) -> bool:
    l_core, l_stable, l_pre = parse_semver(latest)
    c_core, c_stable, c_pre = parse_semver(current)
    if l_core != c_core:
        return l_core > c_core
    if l_stable != c_stable:
        return l_stable and not c_stable
    if not l_stable and not c_stable:
        return l_pre > c_pre
    return False


def select_download_asset_url(
    assets: list[dict[str, Any]],
    os_name: str | None = None,
    arch: str | None = None,
) -> str | None:
    if not assets:
        return None
    target_os = (os_name or sys.platform).lower()
    target_arch = (arch or platform.machine()).lower()

    valid: list[tuple[str, str]] = []
    for item in assets:
        name = str(item.get("name") or "")
        url = str(item.get("browser_download_url") or "")
        if url.startswith("https://") and name:
            valid.append((name.lower(), url))
    if not valid:
        return None

    def _pick(exts: tuple[str, ...], arch_hints: tuple[str, ...] = ()) -> str | None:
        for ext in exts:
            matched = [(n, u) for n, u in valid if n.endswith(ext)]
            if not matched:
                continue
            if arch_hints:
                for n, u in matched:
                    if any(h in n for h in arch_hints):
                        return u
            return matched[0][1]
        return None

    if target_os.startswith("darwin") or target_os == "macos":
        if target_arch in ("arm64", "aarch64"):
            hints = ("arm64", "aarch64", "universal")
        else:
            hints = ("x64", "x86_64", "universal")
        return _pick((".dmg", ".app.tar.gz", ".pkg", ".zip"), hints)

    if target_os.startswith("win"):
        hints = ("x64", "x86_64", "amd64")
        return _pick((".msi", ".exe", ".zip"), hints)

    return _pick((".appimage", ".deb", ".tar.gz", ".zip"))


def _default_fetcher(url: str, timeout_s: float, user_agent: str) -> tuple[int, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": user_agent,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        body_raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            parsed = json.loads(body_raw) if body_raw.strip() else {}
        except json.JSONDecodeError:
            parsed = {"message": body_raw.strip() or str(exc)}
        return exc.code, parsed


def check_github_release(
    current_version: str | None = None,
    *,
    timeout_s: float = 6.0,
    fetcher: Callable[[str, float, str], tuple[int, Any]] | None = None,
) -> UpdateCheckResponse:
    """Query GitHub Releases for creatorjosephkr/pdf2md and compare versions."""
    cur_norm = normalize_version(current_version or __version__)
    checked_at = datetime.now(timezone.utc).isoformat()
    user_agent = f"PDF-Eolgae/{cur_norm}"
    fetch = fetcher or _default_fetcher

    try:
        status_code, payload = fetch(LATEST_RELEASE_API_URL, timeout_s, user_agent)
        if status_code == 404:
            # No non-prerelease release published yet; inspect recent releases list
            list_status, list_payload = fetch(RELEASES_LIST_API_URL, timeout_s, user_agent)
            if list_status == 200 and isinstance(list_payload, list):
                published = [r for r in list_payload if isinstance(r, dict) and not r.get("draft")]
                if published:
                    status_code = 200
                    payload = published[0]
                else:
                    return UpdateCheckResponse(
                        status="no_release",
                        current_version=cur_norm,
                        has_update=False,
                        release_url=RELEASES_PAGE_URL,
                        repo_url=REPO_URL,
                        checked_at=checked_at,
                        message="아직 게시된 GitHub 릴리즈가 없습니다.",
                    )
            else:
                return UpdateCheckResponse(
                    status="no_release",
                    current_version=cur_norm,
                    has_update=False,
                    release_url=RELEASES_PAGE_URL,
                    repo_url=REPO_URL,
                    checked_at=checked_at,
                    message="아직 게시된 GitHub 릴리즈가 없습니다.",
                )

        if status_code in (403, 429):
            return UpdateCheckResponse(
                status="error",
                current_version=cur_norm,
                has_update=False,
                release_url=RELEASES_PAGE_URL,
                repo_url=REPO_URL,
                checked_at=checked_at,
                message="GitHub API 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.",
            )

        if status_code != 200 or not isinstance(payload, dict):
            detail = payload.get("message") if isinstance(payload, dict) else None
            msg = f"GitHub 릴리즈 확인 실패 (HTTP {status_code})"
            if detail:
                msg = f"{msg}: {detail}"
            return UpdateCheckResponse(
                status="error",
                current_version=cur_norm,
                has_update=False,
                release_url=RELEASES_PAGE_URL,
                repo_url=REPO_URL,
                checked_at=checked_at,
                message=msg,
            )

        tag_name = str(payload.get("tag_name") or "").strip()
        if not tag_name:
            return UpdateCheckResponse(
                status="no_release",
                current_version=cur_norm,
                has_update=False,
                release_url=RELEASES_PAGE_URL,
                repo_url=REPO_URL,
                checked_at=checked_at,
                message="아직 게시된 GitHub 릴리즈가 없습니다.",
            )

        latest_norm = normalize_version(tag_name)
        release_url = str(payload.get("html_url") or RELEASES_PAGE_URL)
        release_name = str(payload.get("name") or f"v{latest_norm}").strip()
        raw_notes = str(payload.get("body") or "").strip()
        release_notes = raw_notes[:4000] if raw_notes else None
        published_at = str(payload.get("published_at") or "").strip() or None
        assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
        download_url = select_download_asset_url(assets)

        newer = is_newer_version(latest_norm, cur_norm)
        if newer:
            return UpdateCheckResponse(
                status="update_available",
                current_version=cur_norm,
                latest_version=latest_norm,
                has_update=True,
                release_name=release_name,
                release_notes=release_notes,
                published_at=published_at,
                release_url=release_url,
                download_url=download_url,
                repo_url=REPO_URL,
                checked_at=checked_at,
                message=f"새 버전 v{latest_norm}이(가) 출시되었습니다.",
            )

        return UpdateCheckResponse(
            status="up_to_date",
            current_version=cur_norm,
            latest_version=latest_norm,
            has_update=False,
            release_name=release_name,
            release_notes=release_notes,
            published_at=published_at,
            release_url=release_url,
            download_url=download_url,
            repo_url=REPO_URL,
            checked_at=checked_at,
            message=f"현재 최신 버전(v{cur_norm})을 사용 중입니다.",
        )
    except Exception as exc:
        return UpdateCheckResponse(
            status="error",
            current_version=cur_norm,
            has_update=False,
            release_url=RELEASES_PAGE_URL,
            repo_url=REPO_URL,
            checked_at=checked_at,
            message=f"업데이트 서버에 연결할 수 없습니다: {exc}",
        )
