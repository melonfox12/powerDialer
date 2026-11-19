import tempfile
import unittest

from features._campaigns.import_rules import build_import_plan
from features._campaigns.store import LocalCampaignStore
from features._campaigns.stats import build_campaign_stats
from features._campaigns.transitions import (
    WORKFLOW_EDGES,
    WORKFLOW_ENTRY_NODE,
    build_flow_snapshot,
    is_allowed_transition,
)


class CampaignImportRulesTests(unittest.TestCase):
    def test_preview_groups_warnings(self):
        leads = {
            "a": {"id": "a", "phone": "555", "status": "new"},
            "b": {"id": "b", "phone": "", "status": "new"},
            "c": {"id": "c", "phone": "556", "status": "closed"},
        }
        plan = build_import_plan(["a", "a", "b", "c", "missing"], set(), leads)
        self.assertEqual(plan["requested"], 4)
        self.assertEqual(plan["new_count"], 3)
        codes = {row["code"] for row in plan["warnings"]}
        self.assertIn("duplicate_request", codes)
        self.assertIn("missing_lead", codes)
        self.assertIn("no_phone", codes)
        self.assertIn("closed_status", codes)


class CampaignStoreTests(unittest.TestCase):
    def test_create_active_and_import(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCampaignStore(directory)
            catalog = store.catalog()
            self.assertTrue(catalog["campaigns"])
            first_id = catalog["active_id"]
            catalog = store.create_campaign("West pest")
            west_id = next(row["id"] for row in catalog["campaigns"] if row["name"] == "West pest")
            store.set_active(west_id)
            store.import_members(west_id, ["lead-1", "lead-2", "lead-1"])
            self.assertEqual(store.member_ids(west_id), ["lead-1", "lead-2"])
            plan = build_import_plan(["lead-2", "lead-3"], set(store.member_ids(west_id)), {
                "lead-2": {"id": "lead-2", "phone": "1", "status": "new"},
                "lead-3": {"id": "lead-3", "phone": "2", "status": "new"},
            })
            self.assertEqual(plan["new_count"], 1)
            store.import_members(west_id, plan["new_lead_ids"])
            self.assertEqual(store.member_ids(west_id), ["lead-1", "lead-2", "lead-3"])

    def test_import_sets_entry_stage_and_flow_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalCampaignStore(directory)
            campaign_id = store.catalog()["active_id"]
            store.import_members(campaign_id, ["lead-a", "lead-b"])
            flow = store.flow_snapshot(campaign_id)
            self.assertEqual(flow["nodes"][WORKFLOW_ENTRY_NODE]["count"], 2)
            self.assertEqual(flow["edges"]["e-lead-phone"]["count"], 2)

    def test_transition_table_has_fixed_edge_count(self):
        self.assertEqual(len(WORKFLOW_EDGES), 15)
        self.assertTrue(
            is_allowed_transition("lead-list", "phone-lookup", "out"),
        )
        self.assertIsNone(is_allowed_transition("lead-list", "phone-lookup", "out-business-line"))

    def test_campaign_stats_rates_and_cost(self):
        settings = {
            "calling_start_hour": 8,
            "calling_end_hour": 21,
            "CAMPAIGN_COST_PER_MINUTE": "0.1",
            "conversation_threshold": 30,
        }

        class FakeMetrics:
            lock = __import__("threading").RLock()
            data = {"daily": {"2099-01-01": {"dials": 10, "connected": 4, "booked": 1, "talk_seconds": 240}}}

            def _today(self):
                return "2099-01-01"

        payload = build_campaign_stats(
            "camp-test",
            ["a", "b", "c"],
            {"a": {"id": "a", "status": "booked"}, "b": {"id": "b", "status": "qualified"}},
            FakeMetrics(),
            settings,
            scope="campaign",
        )
        self.assertEqual(payload["funnel"]["dials"], 3)
        self.assertGreaterEqual(payload["funnel"]["booked"], 1)
        self.assertIsNotNone(payload["funnel"]["rates"]["pickups"])
        self.assertEqual(payload["live"]["cost_per_minute"], 0.1)
        self.assertGreater(payload["live"]["cost_usd"], 0)

    def test_build_flow_snapshot_respects_branch(self):
        stages = {
            "x": {"node": "phone-lookup", "branch": "out-excluded"},
            "y": {"node": "phone-lookup", "branch": "out-business-line"},
        }
        flow = build_flow_snapshot(["x", "y"], stages)
        self.assertEqual(flow["nodes"]["phone-lookup"]["count"], 2)
        self.assertEqual(flow["edges"]["e-phone-excluded"]["count"], 1)
        self.assertEqual(flow["edges"]["e-phone-compliance"]["count"], 1)

