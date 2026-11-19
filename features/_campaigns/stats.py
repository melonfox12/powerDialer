"""Campaign funnel and live cost snapshot (orchestrator-ready, mock-filled today)."""

from shared.infra import utc_now
from shared.vocabulary import CONVERSATION_MIN_SECONDS, SETTING_DEFAULTS

QUALIFIED_STATUSES = frozenset({"qualified", "contact_engaged", "proposal_sent"})
BOOKED_STATUS = "booked"


def _rate(part, whole):
    if not whole:
        return None
    return round(part / whole, 4)


def _format_hour_label(hour):
    h = int(hour) % 24
    if h == 0:
        return "12am"
    if h < 12:
        return f"{h}am"
    if h == 12:
        return "12pm"
    return f"{h - 12}pm"


def calling_window(settings):
    start = int(settings.get("calling_start_hour") or SETTING_DEFAULTS["CALLING_START_HOUR"])
    end = int(settings.get("calling_end_hour") or SETTING_DEFAULTS["CALLING_END_HOUR"])
    now = utc_now().hour
    inside = start <= now < end if start < end else now >= start or now < end
    return {
        "start_hour": start,
        "end_hour": end,
        "inside_window": inside,
        "label": f"{_format_hour_label(start)} – {_format_hour_label(end)}",
    }


def _cost_per_minute(settings):
    raw = settings.get("CAMPAIGN_COST_PER_MINUTE", settings.get("campaign_cost_per_minute"))
    if raw in (None, ""):
        raw = SETTING_DEFAULTS.get("CAMPAIGN_COST_PER_MINUTE", "0.12")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.12


def _member_leads(member_ids, leads_by_id):
    return [leads_by_id[lid] for lid in member_ids if lid in leads_by_id]


def _count_booked(leads):
    return sum(1 for lead in leads if lead.get("status") == BOOKED_STATUS)


def _count_qualified(leads):
    return sum(1 for lead in leads if lead.get("status") in QUALIFIED_STATUSES)


def _mock_campaign_funnel(member_count, seed):
    if member_count <= 0:
        return {"dials": 0, "pickups": 0, "conversations": 0, "qualified": 0, "booked": 0, "call_minutes": 0.0}
    dials = member_count
    pickups = min(dials, max(0, (dials * 11 + seed) // 25))
    conversations = min(pickups, max(0, (pickups * 7 + seed) // 10))
    qualified = min(conversations, max(0, (conversations * 4 + seed) // 13))
    booked = min(qualified, max(0, (qualified * 2 + seed) // 7))
    minutes = round(pickups * 2.4 + conversations * 1.8, 1)
    return {
        "dials": dials,
        "pickups": pickups,
        "conversations": conversations,
        "qualified": qualified,
        "booked": booked,
        "call_minutes": minutes,
    }


def _funnel_from_telemetry(row):
    if not isinstance(row, dict):
        return None
    keys = ("dials", "pickups", "conversations", "qualified", "booked", "call_minutes")
    if not any(key in row for key in keys):
        return None
    return {
        "dials": int(row.get("dials") or 0),
        "pickups": int(row.get("pickups") or 0),
        "conversations": int(row.get("conversations") or 0),
        "qualified": int(row.get("qualified") or 0),
        "booked": int(row.get("booked") or 0),
        "call_minutes": float(row.get("call_minutes") or 0.0),
    }


def _today_metrics_bucket(metrics_store):
    with metrics_store.lock:
        today_key = metrics_store._today()
        return dict(metrics_store.data.get("daily", {}).get(today_key, {}))


def _funnel_today(metrics_store, settings):
    bucket = _today_metrics_bucket(metrics_store)
    dials = int(bucket.get("dials") or 0)
    pickups = int(bucket.get("connected") or 0)
    talk_seconds = int(bucket.get("talk_seconds") or 0)
    threshold = int(settings.get("conversation_threshold") or CONVERSATION_MIN_SECONDS)
    conversations = int(bucket.get("interested") or 0)
    if not conversations and talk_seconds and threshold > 0:
        conversations = min(pickups, talk_seconds // threshold)
    qualified = int(bucket.get("interested") or 0)
    booked = int(bucket.get("booked") or 0)
    minutes = round(talk_seconds / 60.0, 1)
    return {
        "dials": dials,
        "pickups": pickups,
        "conversations": conversations,
        "qualified": qualified,
        "booked": booked,
        "call_minutes": minutes,
    }


def _attach_rates(funnel):
    return {
        **funnel,
        "rates": {
            "pickups": _rate(funnel["pickups"], funnel["dials"]),
            "conversations": _rate(funnel["conversations"], funnel["pickups"]),
            "qualified": _rate(funnel["qualified"], funnel["conversations"]),
            "booked": _rate(funnel["booked"], funnel["qualified"]),
        },
    }


def build_campaign_stats(
    campaign_id,
    member_ids,
    leads_by_id,
    metrics_store,
    settings,
    telemetry=None,
    scope="campaign",
):
    scope = "today" if scope == "today" else "campaign"
    leads = _member_leads(member_ids, leads_by_id)
    seed = sum(ord(ch) for ch in campaign_id) % 17
    source = "live"

    if scope == "today":
        funnel = _funnel_today(metrics_store, settings)
        if funnel["dials"] == 0 and funnel["pickups"] == 0:
            funnel = _mock_campaign_funnel(min(len(member_ids), 3), seed)
            source = "mock"
    else:
        stored = _funnel_from_telemetry((telemetry or {}).get("campaign"))
        if stored:
            funnel = stored
            source = "telemetry"
        else:
            funnel = _mock_campaign_funnel(len(member_ids), seed)
            source = "mock"
        booked_real = _count_booked(leads)
        qualified_real = _count_qualified(leads)
        if booked_real:
            funnel["booked"] = max(funnel["booked"], booked_real)
        if qualified_real:
            funnel["qualified"] = max(funnel["qualified"], qualified_real)
        if len(member_ids) and funnel["dials"] < len(member_ids):
            funnel["dials"] = len(member_ids)

    funnel = _attach_rates(funnel)
    cost_rate = _cost_per_minute(settings)
    cost_usd = round(funnel["call_minutes"] * cost_rate, 2)
    calling = calling_window(settings)
    return {
        "campaign_id": campaign_id,
        "scope": scope,
        "source": source,
        "funnel": funnel,
        "live": {
            "call_minutes": funnel["call_minutes"],
            "cost_per_minute": cost_rate,
            "cost_usd": cost_usd,
            "is_live": bool((telemetry or {}).get("is_live")),
        },
        "calling_hours": calling,
    }