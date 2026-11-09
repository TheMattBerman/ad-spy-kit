import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request


VIRLO_BASE_URL = "https://api.virlo.ai/v1"
USER_AGENT = "winning-creative-tracker/0.1"


class VirloClientError(Exception):
    pass


class VirloClient:
    def __init__(self, api_key=None, base_url=VIRLO_BASE_URL, user_agent=USER_AGENT):
        _load_dotenv_if_needed("VIRLO_API_KEY")
        self.api_key = api_key or os.environ.get("VIRLO_API_KEY")
        if not self.api_key:
            raise VirloClientError("VIRLO_API_KEY is not set")
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.calls = []

    def _headers(self, has_body=False):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        return headers

    def request(self, method, path, params=None, payload=None):
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v not in (None, "")}
            if clean:
                query = "?" + urllib.parse.urlencode(clean)
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}{path}{query}"
        req = urllib.request.Request(url, data=data, headers=self._headers(payload is not None), method=method)

        started = time.monotonic()
        status = None
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                status = resp.status
                text = resp.read().decode("utf-8")
                body = json.loads(text) if text else {}
                self._log_call(method, path, status, resp.headers, started)
                return body
        except urllib.error.HTTPError as e:
            status = e.code
            body = e.read().decode("utf-8", errors="replace")
            self._log_call(method, path, status, e.headers, started)
            message = _error_message(body)
            if e.code == 403 and "1010" in body:
                message = (
                    "Virlo rejected this HTTP client with Cloudflare 1010. "
                    "Use the repo VirloClient or send a normal User-Agent header."
                )
            raise VirloClientError(f"Virlo API error {e.code}: {message}") from e
        except (OSError, ValueError) as e:
            self._log_call(method, path, status, {}, started)
            raise VirloClientError(f"Virlo API request failed: {e}") from e

    def _log_call(self, method, path, status, headers, started):
        self.calls.append(
            {
                "provider": "virlo",
                "method": method,
                "path": path,
                "status": status,
                "cost": _header_value(headers, "x-cost") or "0.00",
                "credits_used": _header_value(headers, "x-credits-used") or "0",
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
        )

    def list_orbits(self, limit=100):
        body = self.request("GET", "/orbit", params={"limit": limit, "page": 1})
        data = body.get("data") or {}
        return data.get("orbits") or []

    def list_comets(self, limit=100, include_inactive=True):
        body = self.request(
            "GET",
            "/comet",
            params={"limit": limit, "include_inactive": str(include_inactive).lower()},
        )
        data = body.get("data") or {}
        return data.get("configurations") or data.get("comets") or []

    def orbit_videos(self, orbit_id, limit=25, page=1):
        body = self.request("GET", f"/orbit/{orbit_id}/videos", params={"limit": limit, "page": page})
        data = body.get("data") or {}
        return data.get("videos") or [], data

    def orbit_outliers(self, orbit_id, limit=10, page=1):
        body = self.request("GET", f"/orbit/{orbit_id}/creators/outliers", params={"limit": limit, "page": page})
        data = body.get("data") or {}
        return data.get("outliers") or [], data

    def comet_videos(self, comet_id, limit=25, page=1):
        body = self.request("GET", f"/comet/{comet_id}/videos", params={"limit": limit, "page": page})
        data = body.get("data") or {}
        return data.get("videos") or [], data

    def comet_outliers(self, comet_id, limit=10, page=1):
        body = self.request("GET", f"/comet/{comet_id}/creators/outliers", params={"limit": limit, "page": page})
        data = body.get("data") or {}
        return data.get("outliers") or [], data

    def create_orbit(self, name, keywords, platforms=None, time_period="this_month", min_views=0, run_analysis=False):
        payload = {
            "name": name,
            "keywords": keywords[:10],
            "time_period": time_period,
            "platforms": platforms or ["instagram", "tiktok"],
            "min_views": min_views,
            "run_analysis": run_analysis,
        }
        body = self.request("POST", "/orbit", payload=payload)
        data = body.get("data") or body
        orbit_id = data.get("orbit_id") or data.get("id")
        if not orbit_id:
            raise VirloClientError(f"Could not parse orbit id from Virlo response: {data}")
        return orbit_id, data


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
