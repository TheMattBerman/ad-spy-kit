import hashlib
import os
import urllib.error
import urllib.parse
import urllib.request

from .virlo_client import USER_AGENT
from .video_evidence import VideoEvidenceError, capture_video_frames
from .media_evidence import MediaEvidenceError


IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


class AssetDownloadError(Exception):
    pass


class AssetDownloader:
    def __init__(self, run_dir, user_agent=USER_AGENT, timeout=30, max_bytes=8_000_000, enable_full_motion=None):
        self.run_dir = run_dir
        self.assets_dir = os.path.join(run_dir, "assets")
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.enable_full_motion = (
            os.environ.get("WCT_DISABLE_FULL_MOTION", "").strip().lower() not in ("1", "true", "yes")
            if enable_full_motion is None
            else bool(enable_full_motion)
        )
        self.events = []
        os.makedirs(self.assets_dir, exist_ok=True)

    def download(self, url, prefix):
        url = str(url or "").strip()
        if not url:
            return ""

        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        base = f"{_slug(prefix)}-{digest}"
        existing = self._existing_asset(base)
        if existing:
            self._log("hit", url, existing, "")
            return existing

        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept": "image/*,*/*;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                ext = IMAGE_EXTENSIONS.get(content_type) or _ext_from_url(url)
                if ext not in IMAGE_EXTENSIONS.values():
                    raise AssetDownloadError(f"unsupported content type: {content_type or 'unknown'}")
                data = resp.read(self.max_bytes + 1)
                if len(data) > self.max_bytes:
                    raise AssetDownloadError(f"asset exceeds {self.max_bytes} bytes")
        except (OSError, urllib.error.URLError, AssetDownloadError) as e:
            self._log("skip", url, "", str(e))
            return ""

        rel_path = os.path.join("assets", f"{base}{ext}")
        abs_path = os.path.join(self.run_dir, rel_path)
        try:
            with open(abs_path, "wb") as f:
                f.write(data)
        except OSError as e:
            self._log("skip", url, "", str(e))
            return ""

        self._log("downloaded", url, rel_path, "")
        return rel_path

    def download_video_frames(self, url, prefix, frame_count=6):
        """Return extracted video frames, or an empty list with a receipt."""
        if not self.enable_full_motion:
            self._log("skip", str(url or ""), "", "full-motion evidence disabled via WCT_DISABLE_FULL_MOTION")
            return []
        try:
            paths = capture_video_frames(url, self.run_dir, prefix, frame_count=frame_count)
        except (VideoEvidenceError, MediaEvidenceError) as error:
            self._log("skip", str(url or ""), "", f"full-motion evidence unavailable: {error}")
            return []
        for path in paths:
            self._log("downloaded", str(url), path, "full-motion frame")
        return paths

    def download_opening_frames(self, url, prefix, frame_count=5):
        """Return dense opening video frames, or an empty list with a receipt."""
        if not self.enable_full_motion:
            self._log("skip", str(url or ""), "", "full-motion evidence disabled via WCT_DISABLE_FULL_MOTION")
            return []
        try:
            paths = capture_video_frames(url, self.run_dir, prefix, frame_count=frame_count, opening=True)
        except (VideoEvidenceError, MediaEvidenceError) as error:
            self._log("skip", str(url or ""), "", f"full-motion evidence unavailable: {error}")
            return []
        for path in paths:
            self._log("downloaded", str(url), path, "opening full-motion frame")
        return paths

    def _existing_asset(self, base):
        for ext in IMAGE_EXTENSIONS.values():
            rel_path = os.path.join("assets", f"{base}{ext}")
            if os.path.exists(os.path.join(self.run_dir, rel_path)):
                return rel_path
        return ""

    def _log(self, status, url, local_path, reason):
        self.events.append({"status": status, "url": url, "local_path": local_path, "reason": reason})


def asset_summary(events):
    downloaded = len([e for e in events if e.get("status") in ("downloaded", "hit")])
    skipped = [e for e in events if e.get("status") == "skip"]
    return {"downloaded": downloaded, "skipped": skipped, "events": events}


def _slug(value):
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "asset"))
    text = "-".join(part for part in text.split("-") if part)
    return text[:48] or "asset"


def _ext_from_url(url):
    path = urllib.parse.urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ""
