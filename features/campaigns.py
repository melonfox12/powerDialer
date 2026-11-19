"""HTTP routes for workflow campaigns and membership import."""

import json
import urllib.parse

from features._campaigns.import_rules import build_import_plan


def _campaigns(request):
    return request.account.campaigns


def _leads_by_id(request):
    return {lead["id"]: lead for lead in request.account.crm.snapshot() if lead.get("id")}


def _campaign_or_error(request, campaign_id):
    campaign = _campaigns(request).get_campaign(campaign_id)
    if not campaign:
        raise ValueError("Unknown campaign.")
    return campaign


def _campaign_id_from_path(request, tail):
    path = request._trace_path
    prefix = "/api/campaigns/"
    if not path.startswith(prefix) or not path.endswith(tail):
        raise ValueError("Invalid campaign route.")
    campaign_id = path[len(prefix):][: -len(tail)].strip("/")
    if not campaign_id or "/" in campaign_id:
        raise ValueError("Invalid campaign id.")
    return urllib.parse.unquote(campaign_id)


def get_campaigns(request):
    try:
        request.send_json(200, _campaigns(request).catalog())
    except (OSError, ValueError) as exc:
        request.send_json(400, {"error": str(exc)})


def post_campaign(request):
    try:
        length = int(request.headers.get("Content-Length", "0") or 0)
        raw = request.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        catalog = _campaigns(request).create_campaign(data.get("name"))
        request.send_json(200, catalog)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        request.send_json(400, {"error": str(exc)})


def post_campaign_active(request):
    try:
        length = int(request.headers.get("Content-Length", "0") or 0)
        raw = request.rfile.read(length) if length else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        campaign_id = str(data.get("id") or "").strip()
        if not campaign_id:
            raise ValueError("Campaign id is required.")
        catalog = _campaigns(request).set_active(campaign_id)
        request.send_json(200, catalog)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        request.send_json(400, {"error": str(exc)})


def _import_body(request):
    length = int(request.headers.get("Content-Length", "0") or 0)
    if length > MAX_IMPORT_BODY:
        raise ValueError("Import payload is too large.")
    raw = request.rfile.read(length) if length else b"{}"
    data = json.loads(raw.decode("utf-8") or "{}")
    if not isinstance(data, dict):
        raise ValueError("Import body must be an object.")
    lead_ids = data.get("lead_ids")
    if not isinstance(lead_ids, list):
        raise ValueError("lead_ids must be an array.")
    return lead_ids


MAX_IMPORT_BODY = 8 * 1024 * 1024


def post_campaign_import_preview(request):
    try:
        campaign_id = _campaign_id_from_path(request, "/import/preview")
        _campaign_or_error(request, campaign_id)
        lead_ids = _import_body(request)
        members = set(_campaigns(request).member_ids(campaign_id))
        plan = build_import_plan(lead_ids, members, _leads_by_id(request))
        plan["campaign_id"] = campaign_id
        request.send_json(200, plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        request.send_json(400, {"error": str(exc)})


def get_campaign_flow(request):
    try:
        campaign_id = _campaign_id_from_path(request, "/flow")
        _campaign_or_error(request, campaign_id)
        request.send_json(200, _campaigns(request).flow_snapshot(campaign_id))
    except (OSError, ValueError) as exc:
        request.send_json(400, {"error": str(exc)})


def post_campaign_import(request):
    try:
        campaign_id = _campaign_id_from_path(request, "/import")
        _campaign_or_error(request, campaign_id)
        lead_ids = _import_body(request)
        members = set(_campaigns(request).member_ids(campaign_id))
        plan = build_import_plan(lead_ids, members, _leads_by_id(request))
        result = _campaigns(request).import_members(campaign_id, plan["new_lead_ids"])
        catalog = _campaigns(request).catalog()
        request.send_json(200, {
            "campaign_id": campaign_id,
            "added": result["added"],
            "member_count": result["member_count"],
            "requested": plan["requested"],
            "new_count": plan["new_count"],
            "warnings": plan["warnings"],
            "catalog": catalog,
        })
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        request.send_json(400, {"error": str(exc)})


ROUTES = [
    ("GET", "/api/campaigns", get_campaigns, "GET reads"),
    ("POST", "/api/campaigns", post_campaign, "POST"),
    ("POST", "/api/campaigns/active", post_campaign_active, "POST"),
    ("POST", "/api/campaigns/{id}/import/preview", post_campaign_import_preview, "POST"),
    ("POST", "/api/campaigns/{id}/import", post_campaign_import, "POST"),
    ("GET", "/api/campaigns/{id}/flow", get_campaign_flow, "GET reads"),
]