"""Independent adversarial checks for the Chain Reaction input contract.

Run beside engine.py with: python -m unittest test_review -v
Synthetic fixtures intentionally minimize the system to make failures readable.
"""
from __future__ import annotations

import unittest

import pandas as pd
import numpy as np

import engine


def fixture() -> dict[str, pd.DataFrame]:
    months = pd.date_range("2025-09-01", periods=12, freq="MS") + pd.offsets.MonthEnd(0)
    return {
        "Products": pd.DataFrame([dict(
            sku="TEST-1", product_name="Synthetic white interior emulsion / 1 L",
            family="Interior emulsion", pack_l=1, unit_cost_inr_l=100,
            unit_margin_inr_l=40, shelf_life_days=365, min_customer_life_days=30,
            moq_l=1, lead_time_days=7, lead_time_sd_days=0, prior_stage="Maturity",
            commercial_status="Active", successor_sku="", data_origin="SYNTHETIC TEST",
        )]),
        "History": pd.DataFrame([dict(
            month=m, sku="TEST-1", location="Mumbai", orders_l=120,
            shipments_l=120, forecast_l=120, availability_pct=100,
            closing_stock_l=120,
        ) for m in months]),
        "Positions": pd.DataFrame([dict(
            sku="TEST-1", location="Mumbai", current_order_up_to_l=180,
            current_review_days=7, service_floor_pct=95, capacity_l=500,
            forecast_next_month_l=120, commitments_included_l=20,
            data_origin="SYNTHETIC TEST",
        )]),
        "Batches": pd.DataFrame([
            dict(batch_id="OLD", sku="TEST-1", location="Mumbai", quantity_l=30,
                 expiry_date="2026-10-08"),
            dict(batch_id="FRESH", sku="TEST-1", location="Mumbai", quantity_l=90,
                 expiry_date="2027-06-30"),
        ]),
        "Commitments": pd.DataFrame([dict(
            commitment_id="C-1", sku="TEST-1", location="Mumbai",
            due_date="2026-09-07", quantity_l=20,
        )]),
        "Lanes": pd.DataFrame(columns=["source", "destination", "transit_days", "cost_inr_l", "capacity_l", "enabled"]),
        "Settings": pd.DataFrame([
            dict(parameter="as_of_date", value="2026-08-31", explanation="Synthetic snapshot"),
            dict(parameter="data_origin", value="SYNTHETIC TEST", explanation="Not company data"),
            dict(parameter="seed", value=11, explanation="Repeatable fixture"),
        ]),
    }


def via_contract(data: dict[str, pd.DataFrame]):
    # Workbook serialization/SDK rendering is verified separately by the parent.
    return engine.validate_data(data)


class InputContractReview(unittest.TestCase):
    def test_valid_minimal_workbook_loads(self):
        loaded = via_contract(fixture())
        self.assertEqual(len(loaded["Products"]), 1)

    def reject(self, change):
        data = fixture()
        change(data)
        with self.assertRaises(ValueError):
            via_contract(data)

    def test_percentage_outside_domain_rejected(self):
        self.reject(lambda d: d.__setitem__("History", d["History"].assign(availability_pct=101)))

    def test_duplicate_history_natural_key_rejected(self):
        self.reject(lambda d: d.__setitem__("History", pd.concat([d["History"], d["History"].iloc[[0]]], ignore_index=True)))

    def test_duplicate_sku_rejected(self):
        self.reject(lambda d: d.__setitem__("Products", pd.concat([d["Products"], d["Products"]], ignore_index=True)))

    def test_invalid_expiry_date_rejected(self):
        self.reject(lambda d: d.__setitem__("Batches", d["Batches"].assign(expiry_date="not-a-date")))

    def test_future_history_rejected(self):
        self.reject(lambda d: d.__setitem__("History", d["History"].assign(month=pd.date_range("2026-09-01", periods=12, freq="MS"))))

    def test_negative_quantity_rejected(self):
        self.reject(lambda d: d.__setitem__("Batches", d["Batches"].assign(quantity_l=-1)))

    def test_zero_pack_rejected(self):
        self.reject(lambda d: d.__setitem__("Products", d["Products"].assign(pack_l=0)))

    def test_unknown_sku_rejected(self):
        self.reject(lambda d: d.__setitem__("Batches", d["Batches"].assign(sku="MISSING")))

    def test_commitment_inclusion_exceeding_forecast_rejected(self):
        self.reject(lambda d: d.__setitem__("Positions", d["Positions"].assign(commitments_included_l=121)))

    def test_customer_life_not_below_full_life_rejected(self):
        self.reject(lambda d: d.__setitem__("Products", d["Products"].assign(min_customer_life_days=365)))

    def test_fractional_sealed_batch_pack_rejected(self):
        self.reject(lambda d: d.__setitem__("Batches", d["Batches"].assign(quantity_l=1.5)))


class SimulationReview(unittest.TestCase):
    controls = dict(runs=3, horizon_weeks=10, seed=19)

    def test_unapproved_paths_are_exactly_identical(self):
        result = engine.analyze(fixture(), self.controls)
        paths = result["simulation_paths"]
        baseline = paths.loc[paths.scenario == "Baseline"].drop(columns="scenario").reset_index(drop=True)
        proposed = paths.loc[paths.scenario == "Proposed"].drop(columns="scenario").reset_index(drop=True)
        pd.testing.assert_frame_equal(baseline, proposed, check_exact=True)
        self.assertEqual(result["kpis"]["simulated_net_benefit_inr"], 0)

    def test_same_seed_repeats_paths(self):
        first = engine.analyze(fixture(), self.controls)["simulation_paths"]
        second = engine.analyze(fixture(), self.controls)["simulation_paths"]
        pd.testing.assert_frame_equal(first, second, check_exact=True)

    def test_commitment_forecast_overlap_is_subtracted_once(self):
        inclusive = fixture()
        exclusive = fixture()
        exclusive["Positions"] = exclusive["Positions"].assign(
            forecast_next_month_l=100, commitments_included_l=0)
        # Both inputs encode 100 L uncommitted monthly rate plus the same 20 L
        # dated obligation. Full paired paths must therefore be equivalent.
        first = engine.analyze(inclusive, self.controls)
        second = engine.analyze(exclusive, self.controls)
        pd.testing.assert_frame_equal(first["simulation_paths"], second["simulation_paths"], check_exact=True)
        paths = first["simulation_paths"]
        for _, group in paths.groupby(["scenario", "run"]):
            self.assertEqual(group.commitment_due_l.sum(), 20)

    def test_commitment_horizon_boundary(self):
        data = fixture()
        data["Positions"] = data["Positions"].assign(commitments_included_l=0)
        data["Commitments"] = pd.DataFrame([
            dict(commitment_id="DAY28", sku="TEST-1", location="Mumbai", due_date="2026-09-28", quantity_l=20),
            dict(commitment_id="DAY29", sku="TEST-1", location="Mumbai", due_date="2026-09-29", quantity_l=30),
        ])
        result = engine.analyze(data, dict(runs=1, horizon_weeks=4, seed=11))
        for _, group in result["simulation_paths"].groupby("scenario"):
            self.assertEqual(group.commitment_due_l.sum(), 20)

    def test_cost_excludes_inventory_principal(self):
        data = fixture()
        data["Batches"] = data["Batches"].assign(expiry_date="2027-06-30")
        result = engine.analyze(data, dict(runs=1, horizon_weeks=4, seed=11,
                                         annual_holding_pct=0, shortage_penalty_multiplier=0))
        paths = result["simulation_paths"]
        self.assertGreater(paths.inventory_value_inr.max(), 0)
        self.assertTrue((paths.total_cost_inr == 0).all())

    def test_total_cost_is_only_disclosed_components(self):
        result = engine.analyze(fixture(), self.controls)
        paths = result["simulation_paths"]
        expected = paths.holding_cost_inr + paths.expiry_cost_inr + paths.shortage_cost_inr
        np.testing.assert_allclose(paths.total_cost_inr, expected, rtol=0, atol=1e-10)

    def test_stock_flow_reconciles_for_each_path(self):
        result = engine.analyze(fixture(), self.controls)
        for _, group in result["simulation_paths"].groupby(["scenario", "run"]):
            previous_stock = 120.0
            for row in group.sort_values("week").itertuples():
                self.assertAlmostEqual(row.stock_l, previous_stock+row.received_l-row.served_l-row.expired_l)
                previous_stock = row.stock_l

    def test_short_history_retains_prior_and_blocks_unreviewed_approval(self):
        data = fixture()
        data["History"] = data["History"].tail(1).copy()
        overrides = pd.DataFrame([dict(sku="TEST-1", stage_override="Auto", commercial_status="Active",
                                       approve_policy=True, reason="Testing approval gate")])
        result = engine.analyze(data, self.controls, overrides)
        row = result["classification"].iloc[0]
        self.assertEqual(row.confidence, "Insufficient")
        self.assertEqual(row.stage, "Maturity")
        self.assertFalse(result["policy"].approved.any())

    def test_discontinued_status_stops_routine_without_relabeling_maturity(self):
        data = fixture()
        data["Products"] = data["Products"].assign(commercial_status="Discontinued")
        data["Commitments"] = data["Commitments"].iloc[:0].copy()
        data["Positions"] = data["Positions"].assign(commitments_included_l=0)
        overrides = pd.DataFrame([dict(sku="TEST-1", stage_override="Auto", commercial_status="Discontinued",
                                       approve_policy=True, reason="Commercial withdrawal confirmed")])
        result = engine.analyze(data, self.controls, overrides)
        self.assertEqual(result["classification"].iloc[0].stage, "Maturity")
        paths = result["simulation_paths"]
        self.assertEqual(paths.loc[paths.scenario == "Proposed"].ordered_l.sum(), 0)
        self.assertGreater(paths.loc[paths.scenario == "Baseline"].ordered_l.sum(), 0)

    def test_missing_depot_months_do_not_create_confident_decline(self):
        data = fixture()
        m = pd.date_range("2025-03-01", periods=18, freq="MS") + pd.offsets.MonthEnd(0)
        first = pd.concat([data["History"].iloc[[0]]] * 18, ignore_index=True).assign(month=m)
        second = first.assign(location="Pune").drop(index=[15,16])
        data["History"] = pd.concat([first, second], ignore_index=True)
        data["Positions"] = pd.concat([data["Positions"], data["Positions"].assign(location="Pune", commitments_included_l=0)], ignore_index=True)
        data["Batches"] = pd.concat([data["Batches"], data["Batches"].assign(location="Pune", batch_id=["PUNE-OLD", "PUNE-FRESH"])], ignore_index=True)
        result = engine.analyze(data, self.controls)
        row = result["classification"].iloc[0]
        self.assertIn(row.confidence, {"Low", "Suspended", "Insufficient"})
        self.assertEqual(row.stage, "Maturity")

    def test_transfer_source_reserve_is_cumulative_across_batches(self):
        data = engine.validate_data(fixture())
        data["Lanes"] = pd.DataFrame([dict(source="Mumbai", destination="Pune", transit_days=1,
                                          cost_inr_l=1, capacity_l=1000, enabled=True)])
        policy = pd.DataFrame([
            dict(sku="TEST-1", location="Mumbai", usable_stock_l=120, commitment_floor_l=20,
                 safety_stock_l=60, mean_daily_demand_l=0, stock_l=120, capacity_l=500),
            dict(sku="TEST-1", location="Pune", usable_stock_l=0, commitment_floor_l=0,
                 safety_stock_l=0, mean_daily_demand_l=100, stock_l=0, capacity_l=500),
        ])
        risk = pd.DataFrame([
            dict(batch_id="A", sku="TEST-1", location="Mumbai", usable_days=30, at_risk_l=40),
            dict(batch_id="B", sku="TEST-1", location="Mumbai", usable_days=60, at_risk_l=60),
        ])
        moves = engine._transfer_screen(data, engine.default_controls(), policy, risk, pd.Timestamp("2026-08-31"))
        self.assertLessEqual(moves.quantity_l.sum(), 40, "Cumulative moves breach source commitment+safety reserve")


if __name__ == "__main__":
    unittest.main(verbosity=2)
