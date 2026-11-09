import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from .virlo_client import USER_AGENT


SCRAPECREATORS_BASE_URL = "https://api.scrapecreators.com"


class ScrapeCreatorsClientError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class ScrapeCreatorsClient:
    def __init__(self, api_key=None, base_url=SCRAPECREATORS_BASE_URL, user_agent=USER_AGENT):
        _load_dotenv_if_needed("SCRAPECREATORS_API_KEY")
        self.api_key = api_key or os.environ.get("SCRAPECREATORS_API_KEY")
        if not self.api_key:
            raise ScrapeCreatorsClientError("SCRAPECREATORS_API_KEY is not set")
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.calls = []

    def _headers(self):
        return {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    def request(self, path, params=None):
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                query = "?" + urllib.parse.urlencode(clean)
        req = urllib.request.Request(f"{self.base_url}{path}{query}", headers=self._headers())
        started = time.monotonic()
        status = None
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                status = resp.status
                text = resp.read().decode("utf-8")
                body = json.loads(text) if text else {}
                self._log_call(path, status, resp.headers, started)
                return body
        except urllib.error.HTTPError as e:
            status = e.code
            body = e.read().decode("utf-8", errors="replace")
            self._log_call(path, status, e.headers, started)
            raise ScrapeCreatorsClientError(
                f"ScrapeCreators API error {e.code}: {_error_message(body)}", status=e.code
            ) from e
        except (OSError, ValueError) as e:
            self._log_call(path, status, {}, started)
            raise ScrapeCreatorsClientError(f"ScrapeCreators API request failed: {e}") from e

    def _log_call(self, path, status, headers, started):
        self.calls.append(
            {
                "provider": "scrapecreators",
                "method": "GET",
                "path": path,
                "status": status,
                "cost": 1.0,
                "credits_used": _header_value(headers, "x-credits-used") or "1",
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
        )

    def facebook_search_companies(self, query, country="US"):
        try:
            body = self.request(
                "/v1/facebook/adLibrary/search/companies",
                params={"query": query, "country": country},
            )
        except ScrapeCreatorsClientError as e:
            # Only "nothing found" means no page. A bad key, an empty balance or an outage
            # must surface as itself, never as "no Facebook page found".
            if e.status == 404:
                return []
            raise
        return body.get("searchResults") or []

    def facebook_company_ads(self, company_name=None, *, page_id=None, country="US", trim=False, max_ads=60, extra_params=None):
        if (company_name is None) == (page_id is None):
            raise ValueError("facebook_company_ads requires exactly one of company_name or page_id")
        # trim=False returns the full ad snapshot (creative images and video_hd_url/video_sd_url).
        # trim=True strips the snapshot, which leaves no video to watch and no creative to read.
        params = {
            ("pageId" if page_id is not None else "companyName"): page_id if page_id is not None else company_name,
            "country": country,
            "trim": str(trim).lower(),
            **(extra_params or {}),
        }
        results = []
        last_body = {}
        while len(results) < max_ads:
            body = self.request("/v1/facebook/adLibrary/company/ads", params=params)
            last_body = body
            page_results = _facebook_ad_results(body)
            if not page_results:
                break
            results.extend(page_results)
            cursor = body.get("cursor") if isinstance(body, dict) else None
            if not cursor:
                break
            params = {**params, "cursor": cursor}
        return results[:max_ads], last_body

    def post_video_url(self, url):
        """Resolve a public TikTok/Instagram post URL to a direct downloadable video URL.

        Virlo only hands back the post permalink; ScrapeCreators returns the full media,
        which is far more reliable than scraping the platform page with yt-dlp (Instagram
        needs a login there). Returns "" when there is no playable video.
        """
        u = str(url or "").strip()
        try:
            if "tiktok.com" in u:
                body = self.request("/v2/tiktok/video", params={"url": u})
                video = (body.get("aweme_detail") or {}).get("video") or {}
                for key in ("play_addr_h264", "play_addr", "download_addr"):
                    urls = (video.get(key) or {}).get("url_list") or []
                    if urls:
                        return str(urls[0])
            elif "instagram.com" in u:
                body = self.request("/v1/instagram/post", params={"url": u})
                data = body.get("data") or {}
                node = data.get("xdt_shortcode_media") or data.get("shortcode_media") or data
                if isinstance(node, dict) and node.get("video_url"):
                    return str(node["video_url"])
        except ScrapeCreatorsClientError:
            return ""
        return ""

    def facebook_ad_transcript(self, ad_id, *, cache_max_age="7d", allow_long_transcription=False):
        """Native captions or an AI transcript for one Ad Library video ad.

        GET /v1/facebook/adLibrary/ad/transcript. 1 credit per video up to 2 minutes; a cached
        result no older than cache_max_age costs 0; no transcript costs 0. Long videos need
        allow_long_transcription=true (10 credits per started minute), off by default.
        Returns {"transcript", "transcript_available", "cached", "cached_at",
        "credits_charged", "duration_seconds"} (the last three None when not sent).
        """
        params = {"id": str(ad_id), "cache_max_age": cache_max_age}
        if allow_long_transcription:
            params["allow_long_transcription"] = "true"
        body = self.request("/v1/facebook/adLibrary/ad/transcript", params=params)
        data = body.get("data") if isinstance(body.get("data"), dict) else body
        text = str(data.get("transcript") or "").strip()
        return {
            "transcript": text,
            "transcript_available": bool(data.get("transcript_available", bool(text))),
            "cached": bool(body.get("cached") or data.get("cached")),
            "cached_at": body.get("cached_at") or data.get("cached_at"),
            "credits_charged": data.get("credits_charged", body.get("credits_charged")),
            "duration_seconds": data.get("duration_seconds"),
        }

    def tiktok_transcript(self, url):
        try:
            body = self.request("/v1/tiktok/video/transcript", params={"url": url})
        except ScrapeCreatorsClientError:
            return ""
        return body.get("transcript") or ""

    def instagram_transcript(self, url):
        try:
            body = self.request("/v2/instagram/media/transcript", params={"url": url})
        except ScrapeCreatorsClientError:
            return ""
        for item in body.get("transcripts") or []:
            text = item.get("text") if isinstance(item, dict) else None
            if text:
                return text
        return ""

    def tiktok_recent_views(self, handle):
        """Return recent TikTok play counts for a creator handle."""
        body = self.request("/v3/tiktok/profile/videos", params={"handle": handle})
        return _recent_view_counts(body.get("aweme_list"), ("play_count",), "statistics")

    def instagram_recent_views(self, handle):
        """Return recent Instagram post play/view counts for a creator handle."""
        body = self.request("/v1/instagram/user/posts", params={"handle": handle})
        return _recent_view_counts(
            body.get("posts"),
            ("play_count", "view_count", "video_view_count", "ig_play_count"),
        )

    def creator_recent_views(self, handle, platform):
        """Fetch a creator baseline without making baseline failures fatal to a run."""
        try:
            if platform == "tiktok":
                return self.tiktok_recent_views(handle)
            if platform == "instagram":
                return self.instagram_recent_views(handle)
        except ScrapeCreatorsClientError:
            return []
        return []


def _facebook_ad_results(body):
    if isinstance(body, list):
        return body
    if not isinstance(body, dict):
        return []
    if isinstance(body.get("results"), list):
        return body["results"]
    data = body.get("data")
    if isinstance(data, dict):
        for key in ("results", "ads", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    for key in ("ads", "items"):
        if isinstance(body.get(key), list):
            return body[key]
    return []


def _header_value(headers, key):
    if not headers:
        return None
    return headers.get(key) or headers.get(key.title())


def _error_message(body):
    try:
        parsed = json.loads(body)
    except ValueError:
        return body[:500]
    return parsed.get("message") or parsed.get("error") or parsed.get("detail") or body[:500]


def _recent_view_counts(items, keys, nested_key=None):
    if not isinstance(items, list):
        return []
    views = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = item.get(nested_key) if nested_key else item
        if not isinstance(source, dict):
            continue
        for key in keys:
            value = source.get(key)
            try:
                if value is not None:
                    views.append(int(value))
                    break
            except (TypeError, ValueError):
                continue
    return views


def _load_dotenv_if_needed(key_name):
    if os.environ.get(key_name):
        return
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
