#!/usr/bin/env python3
"""AI Trading Radar — GitHub Release Automation Tool.

This script automates the release process:
  1. Reads the current version from aitrader_bot/version.py
  2. Builds the EXE with PyInstaller
  3. Creates the Inno Setup installer
  4. Creates a GitHub Release with the installer as an asset

Requirements:
  pip install PyGithub    (for GitHub API interaction)
  Inno Setup 6+ installed (for iscc compiler)

Usage:
    python tools/release.py --dry-run          # Preview without uploading
    python tools/release.py --publish          # Build + upload to GitHub
    python tools/release.py --build-only       # Just build the installer
    python tools/release.py --token ghp_xxx    # GitHub token (or set GITHUB_TOKEN env)

Environment Variables:
    GITHUB_TOKEN    Personal Access Token with repo scope
    GITHUB_OWNER    GitHub username/organization (default: from version.py)
    GITHUB_REPO     Repository name (default: from version.py)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PY = PROJECT_ROOT / "aitrader_bot" / "version.py"
SPEC_FILE = PROJECT_ROOT / "AITradingRadar-Windows.spec"
INNO_SCRIPT = PROJECT_ROOT / "installer.iss"
DIST_DIR = PROJECT_ROOT / "dist"
INSTALLER_OUTPUT_DIR = PROJECT_ROOT / "installer_output"


# ── Read version ───────────────────────────────────────────────────────

def read_version() -> str:
    """Extract __version__ from version.py."""
    content = VERSION_PY.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise SystemExit(f"ERROR: Cannot find __version__ in {VERSION_PY}")
    return match.group(1).strip()


def read_changelog_since(version: str) -> str:
    """Read unreleased changelog entries from CHANGELOG.md (if exists)."""
    changelog = PROJECT_ROOT / "CHANGELOG.md"
    if not changelog.exists():
        return get_fallback_release_notes(version)

    content = changelog.read_text(encoding="utf-8")
    lines = content.splitlines()
    notes: list[str] = []
    found_current = False

    for line in lines:
        if line.startswith(f"## [{version}") or line.startswith(f"## v{version}"):
            found_current = True
            continue
        if found_current:
            if line.startswith("## [") or line.startswith("## v"):
                break
            notes.append(line)

    notes_str = "\n".join(notes).strip()
    if not notes_str:
        return get_fallback_release_notes(version)
    return notes_str


def get_fallback_release_notes(version: str) -> str:
    """Generate basic release notes if no CHANGELOG is available."""
    return (
        f"## AI Trading Radar v{version}\n\n"
        f"**Release date:** {datetime.now().strftime('%Y-%m-%d')}\n\n"
        "### Changes\n"
        "- Bug fixes and performance improvements\n"
        "- See commit history for full details\n"
    )


# ── Build steps ────────────────────────────────────────────────────────

def build_exe() -> Path:
    """Run PyInstaller to build the executable.

    Returns:
        Path to the built EXE.
    """
    print("=" * 60)
    print(f"  STEP 1: Building executable with PyInstaller...")
    print("=" * 60)

    # Clean old build
    for path in [DIST_DIR / "AITradingRadar.exe",
                 PROJECT_ROOT / "build",
                 PROJECT_ROOT / "AITradingRadar.spec"]:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller",
         "--onefile",
         "--name", "AITradingRadar",
         "--icon", str(PROJECT_ROOT / "icon.ico"),
         "--hidden-import=MetaTrader5._core",
         "--hidden-import=pystray._win32",
         "--hidden-import=PIL._tkinter_finder",
         "--hidden-import=queue",
         "--hidden-import=threading",
         f"--add-data={PROJECT_ROOT / 'config.example.json'};.",
         f"--add-data={PROJECT_ROOT / 'data'};data",
         "--collect-all=aitrader_bot",
         "--clean",
         "--noconfirm",
         str(PROJECT_ROOT / "run_scalping.py")],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"[ERROR] PyInstaller failed:\n{result.stderr}")
        raise SystemExit(1)

    exe_path = DIST_DIR / "AITradingRadar.exe"
    if not exe_path.exists():
        raise SystemExit(f"ERROR: {exe_path} not found after build")

    size_mb = exe_path.stat().st_size / 1024 / 1024
    print(f"  ✓ Build complete: {exe_path.name} ({size_mb:.1f} MB)")
    return exe_path


def build_installer(version: str) -> Path | None:
    """Run Inno Setup compiler to build the installer.

    Inno Setup's iscc.exe must be in PATH or at the default install location.

    Returns:
        Path to the built installer EXE, or None if iscc is not found.
    """
    print("=" * 60)
    print(f"  STEP 2: Building Inno Setup installer...")
    print("=" * 60)

    possible_paths = [
        "iscc",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]

    iscc = None
    for path in possible_paths:
        try:
            subprocess.run([path, "/?"], capture_output=True, timeout=5)
            iscc = path
            break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if iscc is None:
        print("  ⚠ Inno Setup compiler (iscc.exe) not found.")

        # Check if installer was already built via build_exe.bat → manual Inno step
        existing = list(INSTALLER_OUTPUT_DIR.glob(f"*_Setup_v{version}.exe"))
        if existing:
            print(f"  ✓ Found existing installer: {existing[0].name}")
            return existing[0]
        print("  ⚠ Skipping installer build. Run installer.iss manually in Inno Setup.")
        return None

    # Clean previous installer
    if INSTALLER_OUTPUT_DIR.exists():
        shutil.rmtree(INSTALLER_OUTPUT_DIR)

    result = subprocess.run(
        [iscc, str(INNO_SCRIPT)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"[WARN] Inno Setup build may have failed:\n{result.stderr}")
        return None

    installers = list(INSTALLER_OUTPUT_DIR.glob("*.exe"))
    if installers:
        installer = installers[0]
        size_mb = installer.stat().st_size / 1024 / 1024
        print(f"  ✓ Installer built: {installer.name} ({size_mb:.1f} MB)")
        return installer

    print("  ⚠ Installer output not found.")
    return None


# ── GitHub Release ─────────────────────────────────────────────────────

def create_github_release(
    version: str,
    installer_path: Path | None,
    token: str,
    owner: str,
    repo: str,
    dry_run: bool = False,
) -> None:
    """Create a GitHub Release and upload the installer asset."""
    print("=" * 60)
    print(f"  STEP 3: Creating GitHub Release v{version}...")
    print("=" * 60)

    if dry_run:
        print(f"  [DRY RUN] Would create release: v{version} on {owner}/{repo}")
        if installer_path:
            print(f"  [DRY RUN] Would upload: {installer_path.name}")
        print("  ✓ Dry run complete.\n")
        return

    try:
        from github import Github, GithubException
    except ImportError:
        print(
            "ERROR: PyGithub library required.\n"
            "  pip install PyGithub\n\n"
            "Or upload the installer manually via:\n"
            f"  https://github.com/{owner}/{repo}/releases/new?tag=v{version}"
        )
        return

    print(f"  Connecting to GitHub as {owner}...")
    gh = Github(token)
    try:
        gh_repo = gh.get_repo(f"{owner}/{repo}")
    except GithubException as e:
        print(f"  ERROR: Cannot access repo {owner}/{repo}: {e}")
        return

    # Check if release already exists
    try:
        existing = gh_repo.get_release(f"v{version}")
        print(f"  ⚠ Release v{version} already exists!")
        overwrite = input("  Overwrite? [y/N]: ").strip().lower() == "y"
        if not overwrite:
            print("  ✗ Skipping release creation.")
            return
        existing.delete_release()
        print("  ✓ Old release deleted.")
    except GithubException:
        pass  # Release doesn't exist — good

    # Read release notes
    notes = read_changelog_since(version)

    # Create release
    print(f"  Creating release v{version}...")
    try:
        release = gh_repo.create_git_release(
            tag=f"v{version}",
            name=f"v{version}",
            message=notes,
            draft=False,
            prerelease=False,
        )
        print(f"  ✓ Release created: {release.html_url}")
    except GithubException as e:
        print(f"  ERROR creating release: {e}")
        return

    # Upload installer asset
    if installer_path and installer_path.exists():
        print(f"  Uploading {installer_path.name}...")
        try:
            with open(installer_path, "rb") as f:
                release.upload_asset(
                    path=str(installer_path),
                    label=f"AI Trading Radar v{version} Setup",
                    content_type="application/x-msdownload",
                )
            print(f"  ✓ Asset uploaded: {installer_path.name}")
        except GithubException as e:
            print(f"  ERROR uploading asset: {e}")

    print(f"\n  ✓ Release complete: {release.html_url}")


# ── Main ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Trading Radar Release Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview release steps without uploading")
    parser.add_argument("--publish", action="store_true",
                        help="Build + upload to GitHub Releases")
    parser.add_argument("--build-only", action="store_true",
                        help="Just build the installer, don't publish")
    parser.add_argument("--token",
                        help="GitHub Personal Access Token (or GITHUB_TOKEN env)")
    parser.add_argument("--owner",
                        help=f"GitHub owner (default: from version.py)")
    parser.add_argument("--repo",
                        help=f"GitHub repo (default: from version.py)")
    args = parser.parse_args()

    if not any([args.dry_run, args.publish, args.build_only]):
        parser.print_help()
        print("\nUse --dry-run, --publish, or --build-only")
        return

    # Read version
    version = read_version()
    print(f"\n🔖 AI Trading Radar Release Tool — v{version}\n")

    # Read GitHub config
    from aitrader_bot.version import APP_SHORT_NAME

    github_owner = args.owner or os.environ.get("AITRADAR_GITHUB_OWNER", "")
    github_repo = args.repo or os.environ.get("AITRADAR_GITHUB_REPO", "")
    github_token = args.token or os.environ.get("GITHUB_TOKEN", "")

    # Build EXE
    exe_path = build_exe()

    # Copy config & data to dist
    shutil.copy2(PROJECT_ROOT / "config.example.json", DIST_DIR / "config.example.json")
    data_dist = DIST_DIR / "data"
    data_dist.mkdir(exist_ok=True)
    for csv in (PROJECT_ROOT / "data").glob("*.csv"):
        shutil.copy2(csv, data_dist)

    # Build installer
    installer_path = build_installer(version)

    if args.build_only:
        if installer_path:
            print(f"\n✅ Build complete! Installer: {installer_path}")
        else:
            print(f"\n✅ Build complete! EXE: {exe_path}")
        return

    # Publish to GitHub
    if not github_owner or not github_repo:
        print(
            "\n⚠ GitHub owner/repo not configured.\n"
            f"  Set AITRADAR_GITHUB_OWNER and AITRADAR_GITHUB_REPO env vars.\n"
            f"  Or use --owner and --repo flags.\n"
        )
        return

    if not github_token and not args.dry_run:
        print(
            "\n⚠ GitHub token required.\n"
            "  Set GITHUB_TOKEN env var or use --token flag.\n"
        )
        return

    create_github_release(
        version=version,
        installer_path=installer_path,
        token=github_token,
        owner=github_owner,
        repo=github_repo,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
