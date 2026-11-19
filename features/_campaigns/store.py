"""Campaign list and per-campaign lead membership storage."""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from features._campaigns.transitions import WORKFLOW_ENTRY_NODE, build_flow_snapshot

CAMPAIGNS_BLOB_ID = "__campaigns__"
CAMPAIGN_STATUSES = ("draft", "running", "paused", "stopped")


def is_campaigns_storage_lead(lead):
    return isinstance(lead, dict) and lead.get("id") == CAMPAIGNS_BLOB_ID


def campaigns_path(crm_path):
    path = Path(crm_path)
    if path.is_dir() or not path.suffix:
        return path / "campaigns.json"
    return path.with_name("campaigns.json")


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _default_payload():
    first_id = f"camp-{uuid.uuid4().hex[:12]}"
    now = _utc_now()
    return {
        "revision": 1,
        "active_id": first_id,
        "campaigns": [{
            "id": first_id,
            "name": "Campaign 1",
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }],
        "members": {first_id: {"lead_ids": [], "stages": {}, "updated_at": now}},
    }


class LocalCampaignStore:
    def __init__(self, crm_path):
        self.path = campaigns_path(crm_path)
        self.lock = threading.RLock()
        self.revision = 0
        self._data = None

    def _load(self):
        if self._data is not None:
            return self._data
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("campaigns"), list):
                    self._data = raw
                    self.revision = int(raw.get("revision") or 0)
                    return self._data
            except (OSError, json.JSONDecodeError):
                pass
        self._data = _default_payload()
        self.revision = self._data["revision"]
        self._save()
        return self._data

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self._data)
        self.revision = int(self.revision) + 1
        payload["revision"] = self.revision
        self._data = payload
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def catalog(self):
        with self.lock:
            data = self._load()
            campaigns = []
            for row in data.get("campaigns") or []:
                cid = row.get("id")
                member_row = (data.get("members") or {}).get(cid) or {}
                campaigns.append({
                    **row,
                    "member_count": len(member_row.get("lead_ids") or []),
                })
            return {
                "revision": self.revision,
                "active_id": data.get("active_id"),
                "campaigns": campaigns,
            }

    def get_campaign(self, campaign_id):
        with self.lock:
            data = self._load()
            for row in data.get("campaigns") or []:
                if row.get("id") == campaign_id:
                    return dict(row)
        return None

    def member_ids(self, campaign_id):
        with self.lock:
            data = self._load()
            row = (data.get("members") or {}).get(campaign_id) or {}
            return list(row.get("lead_ids") or [])

    def _member_row(self, data, campaign_id):
        return (data.get("members") or {}).get(campaign_id) or {}

    def flow_snapshot(self, campaign_id):
        with self.lock:
            data = self._load()
            if not any(row.get("id") == campaign_id for row in data.get("campaigns") or []):
                raise ValueError("Unknown campaign.")
            row = self._member_row(data, campaign_id)
            lead_ids = list(row.get("lead_ids") or [])
            stages = row.get("stages") if isinstance(row.get("stages"), dict) else {}
            payload = build_flow_snapshot(lead_ids, stages)
            payload["campaign_id"] = campaign_id
            payload["member_count"] = len(lead_ids)
            payload["revision"] = self.revision
            return payload

    def set_active(self, campaign_id):
        with self.lock:
            data = self._load()
            if not any(row.get("id") == campaign_id for row in data.get("campaigns") or []):
                raise ValueError("Unknown campaign.")
            data["active_id"] = campaign_id
            self._save()
            return self.catalog()

    def create_campaign(self, name):
        label = str(name or "").strip() or "New campaign"
        now = _utc_now()
        entry = {
            "id": f"camp-{uuid.uuid4().hex[:12]}",
            "name": label,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        with self.lock:
            data = self._load()
            data.setdefault("campaigns", []).append(entry)
            data.setdefault("members", {})[entry["id"]] = {
                "lead_ids": [],
                "stages": {},
                "updated_at": now,
            }
            if not data.get("active_id"):
                data["active_id"] = entry["id"]
            self._save()
            return self.catalog()

    def import_members(self, campaign_id, lead_ids):
        with self.lock:
            data = self._load()
            if not any(row.get("id") == campaign_id for row in data.get("campaigns") or []):
                raise ValueError("Unknown campaign.")
            members = data.setdefault("members", {}).setdefault(
                campaign_id,
                {"lead_ids": [], "stages": {}, "updated_at": _utc_now()},
            )
            existing = set(members.get("lead_ids") or [])
            stages = members.setdefault("stages", {})
            added = []
            for lead_id in lead_ids or []:
                lid = str(lead_id or "").strip()
                if not lid or lid in existing:
                    continue
                existing.add(lid)
                added.append(lid)
                stages[lid] = WORKFLOW_ENTRY_NODE
            members["lead_ids"] = sorted(existing)
            members["updated_at"] = _utc_now()
            for row in data.get("campaigns") or []:
                if row.get("id") == campaign_id:
                    row["updated_at"] = _utc_now()
            self._save()
            return {"added": len(added), "member_count": len(existing)}


class SupabaseCampaignStore:
    def __init__(self, client, user_id=None):
        self.client = client
        self.user_id = user_id
        self.lock = threading.RLock()
        self._cache = None
        self.revision = 0

    def _scope(self, params=None):
        scoped = dict(params or {})
        if self.user_id:
            scoped["user_id"] = f"eq.{self.user_id}"
        return scoped

    def _blob_lead(self, payload):
        return {
            "id": CAMPAIGNS_BLOB_ID,
            "name": "",
            "phone": "",
            "business": "",
            "status": "new",
            "timezone": "",
            "campaign_storage": payload,
        }

    def _fetch(self):
        rows = self.client.request(
            "GET",
            "prospects",
            self._scope({"id": f"eq.{CAMPAIGNS_BLOB_ID}", "select": "data"}),
        )
        if not rows:
            return None
        data = rows[0].get("data") if isinstance(rows[0], dict) else {}
        stored = data.get("campaign_storage") if isinstance(data, dict) else None
        return stored if isinstance(stored, dict) else None

    def _all(self):
        if self._cache is None:
            stored = self._fetch()
            self._cache = stored if stored else _default_payload()
            self.revision = int(self._cache.get("revision") or 0)
        return self._cache

    def _persist(self):
        payload = dict(self._all())
        self.revision = int(self.revision) + 1
        payload["revision"] = self.revision
        self._cache = payload
        self.client.request(
            "POST",
            "prospects",
            {"on_conflict": "id"},
            [{"id": CAMPAIGNS_BLOB_ID, "user_id": self.user_id, "data": self._blob_lead(payload)}],
            "resolution=merge-duplicates,return=minimal",
        )

    def catalog(self):
        with self.lock:
            data = self._all()
            campaigns = []
            for row in data.get("campaigns") or []:
                cid = row.get("id")
                member_row = (data.get("members") or {}).get(cid) or {}
                campaigns.append({
                    **row,
                    "member_count": len(member_row.get("lead_ids") or []),
                })
            return {
                "revision": self.revision,
                "active_id": data.get("active_id"),
                "campaigns": campaigns,
            }

    def get_campaign(self, campaign_id):
        with self.lock:
            for row in self._all().get("campaigns") or []:
                if row.get("id") == campaign_id:
                    return dict(row)
        return None

    def member_ids(self, campaign_id):
        with self.lock:
            row = (self._all().get("members") or {}).get(campaign_id) or {}
            return list(row.get("lead_ids") or [])

    def _member_row(self, data, campaign_id):
        return (data.get("members") or {}).get(campaign_id) or {}

    def flow_snapshot(self, campaign_id):
        with self.lock:
            data = self._all()
            if not any(row.get("id") == campaign_id for row in data.get("campaigns") or []):
                raise ValueError("Unknown campaign.")
            row = self._member_row(data, campaign_id)
            lead_ids = list(row.get("lead_ids") or [])
            stages = row.get("stages") if isinstance(row.get("stages"), dict) else {}
            payload = build_flow_snapshot(lead_ids, stages)
            payload["campaign_id"] = campaign_id
            payload["member_count"] = len(lead_ids)
            payload["revision"] = self.revision
            return payload

    def set_active(self, campaign_id):
        with self.lock:
            data = self._all()
            if not any(row.get("id") == campaign_id for row in data.get("campaigns") or []):
                raise ValueError("Unknown campaign.")
            data["active_id"] = campaign_id
            self._persist()
            return self.catalog()

    def create_campaign(self, name):
        label = str(name or "").strip() or "New campaign"
        now = _utc_now()
        entry = {
            "id": f"camp-{uuid.uuid4().hex[:12]}",
            "name": label,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
        }
        with self.lock:
            data = self._all()
            data.setdefault("campaigns", []).append(entry)
            data.setdefault("members", {})[entry["id"]] = {
                "lead_ids": [],
                "stages": {},
                "updated_at": now,
            }
            if not data.get("active_id"):
                data["active_id"] = entry["id"]
            self._persist()
            return self.catalog()

    def import_members(self, campaign_id, lead_ids):
        with self.lock:
            data = self._all()
            if not any(row.get("id") == campaign_id for row in data.get("campaigns") or []):
                raise ValueError("Unknown campaign.")
            members = data.setdefault("members", {}).setdefault(
                campaign_id,
                {"lead_ids": [], "stages": {}, "updated_at": _utc_now()},
            )
            existing = set(members.get("lead_ids") or [])
            stages = members.setdefault("stages", {})
            added = []
            for lead_id in lead_ids or []:
                lid = str(lead_id or "").strip()
                if not lid or lid in existing:
                    continue
                existing.add(lid)
                added.append(lid)
                stages[lid] = WORKFLOW_ENTRY_NODE
            members["lead_ids"] = sorted(existing)
            members["updated_at"] = _utc_now()
            for row in data.get("campaigns") or []:
                if row.get("id") == campaign_id:
                    row["updated_at"] = _utc_now()
            self._persist()
            return {"added": len(added), "member_count": len(existing)}


def CampaignStore(*args, client=None, user_id=None, crm_path=None, **kwargs):
    if client is not None:
        return SupabaseCampaignStore(client, user_id=user_id)
    if crm_path is None and args:
        crm_path = args[0]
    return LocalCampaignStore(crm_path)