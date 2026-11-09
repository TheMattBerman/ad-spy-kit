"""Within-creator view baselines for organic format scoring."""

import math
import statistics


def annotate_overperformance(records, scrape_client, cache=None):
    """Attach conservative, within-creator overperformance scores in place.

    A creator's recent posts form the baseline, excluding posts with the same view
    count as the sampled post. Failures deliberately leave the source record alone:
    live capture must still be useful when a provider cannot supply a baseline.
    """
    cache = cache if cache is not None else {}
    fetcher = getattr(scrape_client, "creator_recent_views", None)
    if not callable(fetcher):
        return records

    for record in records:
        handle = str(record.get("creator_handle") or "").strip().lstrip("@")
        platform = _platform_from_url(record.get("post_url"))
        views = _view_count(record.get("views"))
        if not handle or not platform or views is None:
            continue

        cache_key = (platform, handle.lower())
        if cache_key not in cache:
            try:
                cache[cache_key] = list(fetcher(handle, platform) or [])
            except Exception:
                # Baselines are an optional enhancement; no provider error can abort capture.
                cache[cache_key] = []

        baseline = [v for v in cache[cache_key] if _view_count(v) is not None and _view_count(v) != views]
        n = len(baseline)
        if n < 1:
            continue
        median = statistics.median(baseline)
        score = math.log(views + 1) - math.log(median + 1)
        record["overperformance"] = (n / (n + 5)) * score
        record["baseline_n"] = n
    return records


def _platform_from_url(post_url):
    url = str(post_url or "").lower()
    if "tiktok.com" in url:
        return "tiktok"
    if "instagram.com" in url:
        return "instagram"
    return ""


def _view_count(value):
    try:
        views = int(value)
    except (TypeError, ValueError):
        return None
    return views if views >= 0 else None
