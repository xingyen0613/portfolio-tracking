"""Cloud Run free-tier usage, read from Cloud Monitoring.

Only meaningful when running on Cloud Run: both the project id and the access
token come from the GCE metadata server, so off Cloud Run (local cron, tests)
`collect()` returns None and the caller simply omits the section.

Free tier is per billing account per month — see
https://docs.cloud.google.com/free/docs/free-cloud-features:
  180,000 vCPU-seconds · 360,000 GiB-seconds · 2,000,000 requests

Reading these costs nothing: Cloud Monitoring's first 1M time series read per
billing account per month are free, and this runs a handful of times a day.
"""

import calendar
import json
import logging
import statistics
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger(__name__)

_METADATA = "http://metadata.google.internal/computeMetadata/v1"
_TIMEOUT = 10

# key -> (metric short name, monthly free allowance, label)
_METRICS = {
    "cpu": ("container/cpu/allocation_time", 180_000, "CPU"),
    "mem": ("container/memory/allocation_time", 360_000, "記憶體"),
    "req": ("request_count", 2_000_000, "請求"),
}


def _metadata(path: str) -> str | None:
    try:
        r = requests.get(
            f"{_METADATA}/{path}", headers={"Metadata-Flavor": "Google"}, timeout=2
        )
        return r.text.strip() if r.ok else None
    except requests.RequestException:
        return None


def _daily_points(project: str, token: str, metric: str, start: datetime, end: datetime
                  ) -> dict[str, float] | None:
    """{'YYYY-MM-DD': total} for one Cloud Run metric, one bucket per day.

    Daily buckets rather than one giant alignment period: an alignmentPeriod
    longer than the interval makes the API widen the window backwards, which
    silently reports ~31 trailing days as if it were month-to-date.
    """
    try:
        resp = requests.get(
            f"https://monitoring.googleapis.com/v3/projects/{project}/timeSeries",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "filter": f'metric.type="run.googleapis.com/{metric}"',
                "interval.startTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "interval.endTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "aggregation.alignmentPeriod": "86400s",
                "aggregation.perSeriesAligner": "ALIGN_SUM",
                "aggregation.crossSeriesReducer": "REDUCE_SUM",
            },
            timeout=_TIMEOUT,
        )
        if not resp.ok:
            log.warning("gcp_usage: monitoring API %s — %s", resp.status_code, resp.text[:200])
            return None
        days: dict[str, float] = {}
        for series in resp.json().get("timeSeries", []):
            for point in series.get("points", []):
                v = point["value"]
                day = point["interval"]["endTime"][:10]
                days[day] = days.get(day, 0.0) + float(
                    v.get("doubleValue", v.get("int64Value", 0))
                )
        return days
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("gcp_usage: failed to read %s: %s", metric, e)
        return None


def collect() -> dict | None:
    """Month-to-date Cloud Run usage as a fraction of the free tier.

    `pct` is what has actually been consumed this month. `projected_pct` is the
    run rate — the *median* day that had any traffic, times the length of the
    month. The median deliberately ignores days the service was down: averaging
    month-to-date over elapsed days would report a reassuring 1% straight after
    an outage, which is the moment the number matters most.

    Returns {'month', 'day', 'days_in_month', 'items': [{'label', 'pct',
    'projected_pct'}, ...]} or None when not running on Cloud Run.
    """
    project = _metadata("project/project-id")
    raw_token = _metadata("instance/service-accounts/default/token")
    if not project or not raw_token:
        return None  # not on Cloud Run
    try:
        token = json.loads(raw_token)["access_token"]
    except (ValueError, KeyError) as e:
        log.warning("gcp_usage: cannot parse metadata token: %s", e)
        return None

    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    # One window covering both what we need: month-to-date for the accumulated
    # figure, and ~30 days of history for a run rate that survives the 1st.
    window_start = min(month_start, now - timedelta(days=30))

    items = []
    for metric, allowance, label in _METRICS.values():
        days = _daily_points(project, token, metric, window_start, now)
        if days is None:
            continue
        mtd = sum(v for d, v in days.items() if d >= month_start.strftime("%Y-%m-%d"))
        active = [v for v in days.values() if v > 0]
        rate = statistics.median(active) if active else 0.0
        items.append({
            "label": label,
            "pct": mtd / allowance * 100,
            "projected_pct": rate * days_in_month / allowance * 100,
        })
    if not items:
        return None
    return {
        "month": now.month,
        "day": now.day,
        "days_in_month": days_in_month,
        "items": items,
    }


def _pct(value: float) -> str:
    """One decimal below 10% — '0%' for everything hides real movement."""
    return f"{value:.1f}%" if value < 10 else f"{value:.0f}%"


def format_lines(usage: dict) -> list[str]:
    """Three compact lines for the Telegram summary."""
    parts = " ｜ ".join(f"{i['label']} {_pct(i['pct'])}" for i in usage["items"])
    worst = max(usage["items"], key=lambda i: i["projected_pct"])
    return [
        f"GCP 免費額度（{usage['month']}月已過 {usage['day']}/{usage['days_in_month']} 天）",
        f"• 本月已用：{parts}",
        f"• 依目前速率整月：{worst['label']} {_pct(worst['projected_pct'])}",
    ]
