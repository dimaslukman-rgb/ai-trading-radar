"""Auto-update system for AI Trading Radar.

Checks GitHub Releases for newer versions, downloads the installer,
and integrates with the dashboard to show update notifications.

Architecture:
    ┌─────────────┐    check GitHub API    ┌──────────────┐
    │  Background  │ ──────────────────────→│  GitHub       │
    │  Thread      │ ←──────────────────────│  Releases     │
    └──────┬──────┘    release info          └──────────────┘
           │
           ▼ UpdateState (shared via dashboard_data)
    ┌──────────────────────────────────────┐
    │  Web Dashboard SSE + API endpoints  │
    │  "Update v1.2.0 available! [Install]"│
    └──────────────────────────────────────┘
           │
           ▼ User clicks "Install"
    ┌──────────────────────────────────────┐
    │  Download installer → %TEMP%/updates/│
    │  Launch installer (Inno Setup)       │
    │  → Detects old install → upgrades    │
    └──────────────────────────────────────┘
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from .version import __version__, APP_NAME, APP_SHORT_NAME, VERSION_TUPLE

# ── Defaults ───────────────────────────────────────────────────────────
# These can be overridden via environment variables
# Default values match the project's GitHub repository
_GITHUB_OWNER = os.environ.get("AITRADAR_GITHUB_OWNER", "dimaslukman-rgb")
_GITHUB_REPO = os.environ.get("AITRADAR_GITHUB_REPO", "ai-trading-radar")
_GITHUB_API = "https://api.github.com"

# Minimum interval between version checks (24 hours)
_CHECK_INTERVAL_SECONDS = int(os.environ.get("AITRADAR_UPDATE_INTERVAL", "86400"))
# How often the background thread wakes up to check if enough time passed
_WAKE_INTERVAL_SECONDS = 300  # 5 minutes

# Expected asset name pattern for the installer
_ASSET_PATTERN = "_Setup.exe"


# ── Data Classes ───────────────────────────────────────────────────────

@dataclass
class UpdateInfo:
    """Information about an available update from GitHub Releases."""
    latest_version: str
    current_version: str
    download_url: str
    release_notes: str
    release_date: str
    asset_name: str
    asset_size: int  # bytes


@dataclass
class UpdateState:
    """Snapshot of the current update state for the dashboard."""
    current_version: str = __version__
    latest_version: str = ""
    update_available: bool = False
    download_url: str = ""
    release_notes: str = ""
    release_date: str = ""
    asset_name: str = ""
    asset_size: int = 0
    download_progress: float = 0.0       # 0.0 – 1.0
    download_path: str = ""
    downloading: bool = False
    download_complete: bool = False
    error: str = ""
    last_checked: str = "Never"
    status: str = "idle"  # idle | checking | available | downloading | ready | error

    def to_dict(self) -> dict:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "update_available": self.update_available,
            "download_url": self.download_url,
            "release_notes": self.release_notes[:500] if self.release_notes else "",
            "release_date": self.release_date,
            "asset_name": self.asset_name,
            "asset_size": self.asset_size,
            "download_progress": round(self.download_progress * 100, 1),
            "download_path": self.download_path,
            "downloading": self.downloading,
            "download_complete": self.download_complete,
            "error": self.error,
            "last_checked": self.last_checked,
            "status": self.status,
            "_version": __version__,
        }


# ── Internal State ─────────────────────────────────────────────────────

_state = UpdateState()
_lock = threading.Lock()
_listeners: list[Callable[[UpdateState], None]] = []


def _update_state(**kwargs) -> None:
    """Thread-safe update of the shared state."""
    with _lock:
        for key, value in kwargs.items():
            if hasattr(_state, key):
                setattr(_state, key, value)
        snapshot = UpdateState(**{
            f.name: getattr(_state, f.name)
            for f in UpdateState.__dataclass_fields__.values()
        })
    _notify_listeners(snapshot)


def get_state() -> UpdateState:
    """Thread-safe read of the current update state."""
    with _lock:
        return UpdateState(**{
            f.name: getattr(_state, f.name)
            for f in UpdateState.__dataclass_fields__.values()
        })


def add_listener(callback: Callable[[UpdateState], None]) -> None:
    """Register a callback that fires when update state changes."""
    _listeners.append(callback)


def _notify_listeners(state: UpdateState) -> None:
    for cb in _listeners:
        try:
            cb(state)
        except Exception:
            pass


# ── Version Comparison ──────────────────────────────────────────────────

def parse_version(v: str) -> tuple[int, ...]:
    """Parse '1.2.0' or 'v1.2.0' → (1, 2, 0)."""
    cleaned = v.lstrip("vV").strip()
    parts = []
    for part in cleaned.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            break
    return tuple(parts)


def is_newer_version(latest: str, current: str) -> bool:
    """Compare two version strings. Returns True if latest > current."""
    return parse_version(latest) > parse_version(current)


# ── GitHub API ─────────────────────────────────────────────────────────

def _fetch_json(url: str, timeout: int = 15) -> dict | list | None:
    """Fetch and parse JSON from a URL."""
    try:
        req = Request(url, headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"{APP_SHORT_NAME}/{__version__}",
        })
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, json.JSONDecodeError, OSError):
        return None


def check_for_update(
    owner: str = _GITHUB_OWNER,
    repo: str = _GITHUB_REPO,
    current_version: str = __version__,
    timeout: int = 15,
) -> UpdateInfo | None:
    """Check GitHub Releases for a newer version.

    Args:
        owner: GitHub username or organization.
        repo: GitHub repository name.
        current_version: Current local version string.
        timeout: Request timeout in seconds.

    Returns:
        UpdateInfo if a newer version + matching asset is found, else None.
    """
    if not owner or not repo:
        _update_state(status="idle", error="GitHub repo not configured")
        return None

    _update_state(status="checking", error="")

    api_url = f"{_GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    data = _fetch_json(api_url, timeout=timeout)

    if data is None:
        _update_state(status="idle", error="Could not reach GitHub API")
        return None
    if not isinstance(data, dict):
        _update_state(status="idle", error="Unexpected API response")
        return None

    tag_name = data.get("tag_name", "")
    release_version = tag_name.lstrip("vV")

    if not is_newer_version(release_version, current_version):
        _update_state(status="idle", last_checked=_now_str())
        return None

    # Find the installer asset by pattern
    assets = data.get("assets", [])
    target = None
    for asset in assets:
        name = asset.get("name", "")
        if _ASSET_PATTERN in name:
            target = asset
            break
    if target is None and assets:
        target = assets[0]
    if target is None:
        return None

    info = UpdateInfo(
        latest_version=release_version,
        current_version=current_version,
        download_url=target.get("browser_download_url", ""),
        release_notes=data.get("body", "No release notes.")[:2000],
        release_date=data.get("published_at", ""),
        asset_name=target.get("name", "installer.exe"),
        asset_size=target.get("size", 0),
    )

    _update_state(
        status="available",
        latest_version=info.latest_version,
        update_available=True,
        download_url=info.download_url,
        release_notes=info.release_notes,
        release_date=info.release_date,
        asset_name=info.asset_name,
        asset_size=info.asset_size,
        last_checked=_now_str(),
        error="",
    )
    return info


# ── Download ────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _on_download_progress(fraction: float) -> None:
    """Callback during download to update shared state."""
    _update_state(download_progress=fraction)


def download_update(
    info: UpdateInfo,
    dest_dir: str | Path | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> str | None:
    """Download the update installer.

    Args:
        info: UpdateInfo returned by check_for_update().
        dest_dir: Where to save (default: %%TEMP%%/AITradingRadar/updates/).
        progress_callback: Called with fraction 0.0–1.0.

    Returns:
        Path to downloaded file, or None on failure.
    """
    if not info.download_url:
        _update_state(status="error", error="No download URL available")
        return None

    if dest_dir is None:
        dest_dir = Path(tempfile.gettempdir()) / APP_SHORT_NAME / "updates"
    else:
        dest_dir = Path(dest_dir)

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / info.asset_name

    _update_state(status="downloading", downloading=True, error="")

    try:
        req = Request(info.download_url, headers={
            "User-Agent": f"{APP_SHORT_NAME}/{__version__}",
            "Accept": "application/octet-stream",
        })
        resp = urlopen(req, timeout=300)  # 5 min timeout for large files
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk = 8192

        with open(dest_path, "wb") as f:
            while True:
                data = resp.read(chunk)
                if not data:
                    break
                f.write(data)
                downloaded += len(data)
                if total > 0:
                    frac = downloaded / total
                    _on_download_progress(frac)
                    if progress_callback:
                        progress_callback(frac)

        _update_state(
            status="ready",
            downloading=False,
            download_complete=True,
            download_path=str(dest_path),
            download_progress=1.0,
        )
        return str(dest_path)

    except (URLError, OSError) as e:
        _update_state(
            status="error",
            downloading=False,
            error=f"Download failed: {e}",
        )
        if dest_path.exists():
            try:
                dest_path.unlink()
            except OSError:
                pass
        return None


# ── Apply Update ───────────────────────────────────────────────────────

def apply_update(installer_path: str) -> bool:
    """Launch the downloaded Inno Setup installer.

    The installer shares the same AppId as the previous install, so
    Inno Setup will automatically detect the old version and offer
    to upgrade (or silently upgrade with /VERYSILENT).

    Args:
        installer_path: Full path to the downloaded .exe.

    Returns:
        True if the installer was launched successfully.
    """
    if not installer_path or not os.path.isfile(installer_path):
        _update_state(error=f"Installer not found: {installer_path}")
        return False

    try:
        subprocess.Popen(
            [installer_path],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return True
    except (OSError, subprocess.SubprocessError) as e:
        _update_state(error=f"Failed to launch installer: {e}")
        return False


# ── Background Update Check Thread ─────────────────────────────────────

class UpdateChecker:
    """Background thread that periodically checks GitHub for new releases."""

    def __init__(
        self,
        owner: str = _GITHUB_OWNER,
        repo: str = _GITHUB_REPO,
        interval_seconds: int = _CHECK_INTERVAL_SECONDS,
    ):
        self._owner = owner
        self._repo = repo
        self._interval = interval_seconds
        self._last_check: float = 0.0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Start the background check daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def check_now(self) -> UpdateInfo | None:
        """Force an immediate update check (called from API)."""
        info = check_for_update(self._owner, self._repo)
        if info:
            self._last_check = time.time()
        return info

    def _run(self) -> None:
        """Main loop — checks periodically."""
        # Do an initial check after a short delay (don't block startup)
        if not self._stop_event.wait(10):
            self._last_check = time.time()
            check_for_update(self._owner, self._repo)

        while not self._stop_event.is_set():
            elapsed = time.time() - self._last_check
            if elapsed >= self._interval:
                self._last_check = time.time()
                check_for_update(self._owner, self._repo)

            self._stop_event.wait(_WAKE_INTERVAL_SECONDS)


# ── Convenience ────────────────────────────────────────────────────────

def check_text() -> str:
    """CLI-friendly output of update status."""
    if not _GITHUB_OWNER or not _GITHUB_REPO:
        return (
            "Update check is not configured.\n\n"
            "To enable, either:\n"
            "  a) Set environment variables:\n"
            "     AITRADAR_GITHUB_OWNER=your-username\n"
            "     AITRADAR_GITHUB_REPO=your-repo\n"
            "  b) Or configure in version.py\n"
        )

    print(f"Checking for updates (current: v{__version__})...")
    info = check_for_update()
    if info:
        size_mb = info.asset_size / 1024 / 1024
        return (
            f"\n{'='*50}\n"
            f"  UPDATE AVAILABLE!\n"
            f"  New version: v{info.latest_version}\n"
            f"  Current:     v{info.current_version}\n"
            f"  Asset:       {info.asset_name} ({size_mb:.1f} MB)\n"
            f"{'='*50}\n"
            f"\nRelease notes:\n{info.release_notes[:1000]}\n"
            f"\nDownload URL:\n{info.download_url}\n"
        )
    else:
        return f"\nYou are up to date (v{__version__}).\n"
