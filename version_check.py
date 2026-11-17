"""Version and update-check helpers for Meeting Transcriber."""

import json
import urllib.request

APP_VERSION = "1.8.0"
REPO_OWNER = "rashidzainol"
REPO_NAME = "MeetingTranscipt"
GITHUB_API = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases"


def _parse_version(v):
    """Convert 'v1.8.0' to (1, 8, 0) for comparison."""
    parts = []
    for chunk in str(v).strip().lstrip("v").split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer(candidate, current):
    return _parse_version(candidate) > _parse_version(current)


def check_for_update(current=APP_VERSION, timeout=8):
    """Return (latest_version, release_url, notes) or (None, None, None) on failure."""
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "MeetingTranscriber"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name") or data.get("name") or ""
        url = data.get("html_url") or RELEASES_PAGE
        notes = (data.get("body") or "").strip()
        return tag, url, notes
    except Exception:
        return None, None, None
