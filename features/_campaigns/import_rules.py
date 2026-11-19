"""Pure rules for campaign membership import preview and apply."""

from shared.vocabulary import NEVER_DIAL_STATUSES

WARNING_SAMPLE_LIMIT = 8


def _dedupe_preserve_order(ids):
    seen = set()
    ordered = []
    for raw in ids or []:
        lead_id = str(raw or "").strip()
        if not lead_id or lead_id in seen:
            continue
        seen.add(lead_id)
        ordered.append(lead_id)
    return ordered


def build_import_plan(lead_ids, members_set, leads_by_id):
    """Return counts, new ids, and grouped warnings without mutating storage."""
    requested = _dedupe_preserve_order(lead_ids)
    duplicates_in_request = len(lead_ids or []) - len(requested)
    warnings = []
    if duplicates_in_request > 0:
        warnings.append({
            "code": "duplicate_request",
            "count": duplicates_in_request,
            "message": f"{duplicates_in_request} duplicate id(s) in the request were ignored.",
        })

    new_ids = []
    already_member = []
    missing = []
    no_phone = []
    closed_status = []

    members = members_set if isinstance(members_set, set) else set(members_set or [])

    for lead_id in requested:
        if lead_id in members:
            already_member.append(lead_id)
            continue
        lead = leads_by_id.get(lead_id)
        if not lead:
            missing.append(lead_id)
            continue
        status = str(lead.get("status") or "new").strip()
        if status in NEVER_DIAL_STATUSES or status == "closed":
            closed_status.append(lead_id)
        phone = str(lead.get("phone") or "").strip()
        if not phone:
            no_phone.append(lead_id)
        new_ids.append(lead_id)

    def pack(code, ids, message):
        if not ids:
            return
        warnings.append({
            "code": code,
            "count": len(ids),
            "message": message,
            "lead_ids": ids[:WARNING_SAMPLE_LIMIT],
        })

    pack("already_member", already_member, "Already in this campaign.")
    pack("missing_lead", missing, "Not found in CRM.")
    pack("no_phone", no_phone, "Missing a phone number (imported but may not dial).")
    pack("closed_status", closed_status, "Closed or do-not-dial status (imported for tracking).")

    return {
        "requested": len(requested),
        "new_count": len(new_ids),
        "new_lead_ids": new_ids,
        "warnings": warnings,
    }