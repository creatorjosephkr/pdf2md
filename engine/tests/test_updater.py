"""Tests for GitHub Releases update checker."""

from __future__ import annotations

from typing import Any

from pdf_convert_engine.server.updater import (
    LATEST_RELEASE_API_URL,
    RELEASES_LIST_API_URL,
    RELEASES_PAGE_URL,
    check_github_release,
    is_newer_version,
    select_download_asset_url,
)


def test_semver_comparison() -> None:
    assert is_newer_version("0.2.0", "0.1.0") is True
    assert is_newer_version("v1.0.0", "0.9.9") is True
    assert is_newer_version("0.1.1", "0.1.0") is True
    assert is_newer_version("1.0.0", "1.0.0-rc.1") is True
    assert is_newer_version("1.0.0-beta.2", "1.0.0-beta.1") is True

    assert is_newer_version("0.1.0", "0.1.0") is False
    assert is_newer_version("v0.1.0", "0.1.0") is False
    assert is_newer_version("0.0.9", "0.1.0") is False
    assert is_newer_version("1.0.0-rc.1", "1.0.0") is False


def test_select_download_asset_url() -> None:
    assets = [
        {"name": "PDF-Eolgae_0.2.0_x64-setup.exe", "browser_download_url": "https://example.com/win.exe"},
        {"name": "PDF-Eolgae_0.2.0_x86_64.dmg", "browser_download_url": "https://example.com/mac-x64.dmg"},
        {"name": "PDF-Eolgae_0.2.0_aarch64.dmg", "browser_download_url": "https://example.com/mac-arm64.dmg"},
        {"name": "PDF-Eolgae_0.2.0_amd64.AppImage", "browser_download_url": "https://example.com/linux.AppImage"},
    ]
    assert select_download_asset_url(assets, os_name="darwin", arch="arm64") == "https://example.com/mac-arm64.dmg"
    assert select_download_asset_url(assets, os_name="darwin", arch="x86_64") == "https://example.com/mac-x64.dmg"
    assert select_download_asset_url(assets, os_name="win32", arch="amd64") == "https://example.com/win.exe"
    assert select_download_asset_url(assets, os_name="linux", arch="x86_64") == "https://example.com/linux.AppImage"


def test_check_github_release_update_available() -> None:
    def fake_fetch(url: str, _timeout: float, _ua: str) -> tuple[int, Any]:
        assert url == LATEST_RELEASE_API_URL
        return 200, {
            "tag_name": "v0.2.0",
            "name": "PDF 얼개 v0.2.0",
            "body": "- RTF 내보내기\n- 미리보기 탭 개선",
            "published_at": "2026-11-25T00:00:00Z",
            "html_url": "https://github.com/creatorjosephkr/pdf2md/releases/tag/v0.2.0",
            "assets": [
                {
                    "name": "PDF-Eolgae_0.2.0_universal.dmg",
                    "browser_download_url": "https://github.com/creatorjosephkr/pdf2md/releases/download/v0.2.0/PDF-Eolgae_0.2.0_universal.dmg",
                }
            ],
        }

    res = check_github_release(current_version="0.1.0", fetcher=fake_fetch)
    assert res.status == "update_available"
    assert res.has_update is True
    assert res.current_version == "0.1.0"
    assert res.latest_version == "0.2.0"
    assert res.release_name == "PDF 얼개 v0.2.0"
    assert "RTF 내보내기" in (res.release_notes or "")
    assert res.download_url is not None and res.download_url.endswith(".dmg")


def test_check_github_release_up_to_date_and_no_release_and_error() -> None:
    def fake_up_to_date(_url: str, _t: float, _ua: str) -> tuple[int, Any]:
        return 200, {
            "tag_name": "v0.1.0",
            "name": "v0.1.0",
            "html_url": f"{RELEASES_PAGE_URL}/tag/v0.1.0",
            "assets": [],
        }

    ok = check_github_release(current_version="0.1.0", fetcher=fake_up_to_date)
    assert ok.status == "up_to_date"
    assert ok.has_update is False

    def fake_empty_404(url: str, _t: float, _ua: str) -> tuple[int, Any]:
        if url == LATEST_RELEASE_API_URL:
            return 404, {"message": "Not Found"}
        assert url == RELEASES_LIST_API_URL
        return 200, []

    none_rel = check_github_release(current_version="0.1.0", fetcher=fake_empty_404)
    assert none_rel.status == "no_release"
    assert none_rel.has_update is False
    assert none_rel.release_url == RELEASES_PAGE_URL

    def fake_rate_limit(_url: str, _t: float, _ua: str) -> tuple[int, Any]:
        return 403, {"message": "API rate limit exceeded"}

    err_rel = check_github_release(current_version="0.1.0", fetcher=fake_rate_limit)
    assert err_rel.status == "error"
    assert err_rel.has_update is False
    assert "한도" in err_rel.message

    def fake_boom(_url: str, _t: float, _ua: str) -> tuple[int, Any]:
        raise RuntimeError("timed out")

    net_err = check_github_release(current_version="0.1.0", fetcher=fake_boom)
    assert net_err.status == "error"
    assert "timed out" in net_err.message
