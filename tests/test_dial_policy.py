import unittest
from datetime import timedelta

from shared.dial_policy import (
    apply_dial_cap_to_lead,
    dialed_recently,
    dial_cap_reached,
    open_dial_lead_ids,
    pool_leads,
    repair_dial_status_for_lead,
    resolve_pool_status,
)
from shared.infra import utc_now


def lead(**fields):
    base = {
        "id": "p1",
        "name": "Ada",
        "business": "Shop",
        "phone": "+12025550123",
        "timezone": "Eastern",
        "status": "new",
        "scheduled_until": None,
        "transcript": [],
        "fields": {},
        "call_log": [],
    }
    base.update(fields)
    return base


class DialPolicyTests(unittest.TestCase):
    def test_pool_respects_business_type_filter(self):
        rows = [
            lead(id="pest", business_type="pest control", name="Pest Co"),
            lead(id="hvac", business_type="HVAC", name="Cool Co", phone="+12025550124"),
        ]
        all_pool = pool_leads(rows, pool_status="new", busy_ids=set(), now=utc_now())
        self.assertEqual({item["id"] for item in all_pool}, {"pest", "hvac"})
        pest_pool = pool_leads(
            rows, pool_status="new", busy_ids=set(), now=utc_now(), selected_business_type="pest control",
        )
        self.assertEqual([item["id"] for item in pest_pool], ["pest"])
        hvac_pool = pool_leads(
            rows, pool_status="new", busy_ids=set(), now=utc_now(), selected_business_type="hvac",
        )
        self.assertEqual([item["id"] for item in hvac_pool], ["hvac"])

    def test_pool_respects_send_info_mode(self):
        rows = [
            lead(id="n", status="new", name="New Person"),
            lead(id="s", status="send_info", name="Info Person", phone="+12025550124"),
        ]
        new_pool = pool_leads(rows, pool_status="new", busy_ids=set(), now=utc_now())
        info_pool = pool_leads(rows, pool_status="send_info", busy_ids=set(), now=utc_now())
        self.assertEqual([item["id"] for item in new_pool], ["n"])
        self.assertEqual([item["id"] for item in info_pool], ["s"])

    def test_fifth_dial_cap_without_live_contact(self):
        row = lead()
        for index in range(5):
            row["call_log"].append({"id": f"d{index}", "started_at": f"2026-01-0{index + 1}T12:00:00+00:00"})
        self.assertTrue(dial_cap_reached(row))
        self.assertTrue(apply_dial_cap_to_lead(row))
        self.assertEqual(row["status"], "no_answer_disqualified")

    def test_repair_wrong_disqualified_to_new(self):
        row = lead(status="disqualified", call_log=[{"id": "d1", "started_at": "2026-01-01T12:00:00+00:00"}])
        self.assertEqual(repair_dial_status_for_lead(row), "new")

    def test_no_pickup_stays_out_of_pool_for_two_hours(self):
        now = utc_now()
        row = lead(call_log=[{
            "id": "d1",
            "started_at": (now - timedelta(hours=1)).isoformat(),
            "answered_by": "no_answer",
        }])
        self.assertTrue(dialed_recently(row, now))
        row["call_log"][0]["started_at"] = (now - timedelta(hours=3)).isoformat()
        self.assertFalse(dialed_recently(row, now))

    def test_in_progress_dial_uses_two_hour_retry_window(self):
        now = utc_now()
        row = lead(call_log=[{
            "id": "d1",
            "started_at": (now - timedelta(hours=1)).isoformat(),
            "answered_by": "",
            "ended_at": "",
        }])
        self.assertTrue(dialed_recently(row, now))
        self.assertEqual(open_dial_lead_ids([row]), {"p1"})
        self.assertEqual(pool_leads([row], pool_status="new", busy_ids={"p1"}, now=now), [])

    def test_resolve_pool_status_defaults_unknown(self):
        self.assertEqual(resolve_pool_status("booked"), "new")


if __name__ == "__main__":
    unittest.main()
