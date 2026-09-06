"""Decision/flow invariants independent of visual presentation."""
import unittest

import numpy as np
import pandas as pd

import engine
from test_review import fixture


class EngineInvariants(unittest.TestCase):
    def run_case(self, data=None, controls=None, overrides=None):
        c = dict(runs=3, horizon_weeks=8)
        c.update(controls or {})
        return engine.analyze(data or fixture(), c, overrides)

    def test_no_approval_means_exactly_identical_paths(self):
        r = self.run_case(controls={"demand_shock_pct":35,"lead_time_shock_pct":40})
        a = r["simulation_paths"].query("scenario == 'Baseline'").drop(columns="scenario").reset_index(drop=True)
        b = r["simulation_paths"].query("scenario == 'Proposed'").drop(columns="scenario").reset_index(drop=True)
        pd.testing.assert_frame_equal(a,b,check_exact=True)
        self.assertEqual(r["kpis"]["simulated_net_benefit_inr"],0)

    def test_repeated_seed_is_exact(self):
        a,b = self.run_case(),self.run_case()
        pd.testing.assert_frame_equal(a["run_results"],b["run_results"],check_exact=True)

    def test_fefo_consumes_oldest_eligible_lot(self):
        lots = [[100,50],[45,20],[200,30]]
        self.assertEqual(engine._take_fefo(lots,35,7,30),35)
        self.assertEqual(lots,[[100,35],[45,0],[200,30]])

    def test_fefo_excludes_customer_unusable_stock(self):
        lots = [[35,40],[100,25]]
        self.assertEqual(engine._take_fefo(lots,45,7,37),25)
        self.assertEqual(lots[0][1],40)

    def test_dated_commitment_only_once_when_residual_shocked_to_zero(self):
        r = self.run_case(controls={"demand_shock_pct":-100})
        p = r["simulation_paths"].query("scenario == 'Baseline' and run == 1")
        self.assertEqual(p.demand_l.sum(),20)
        self.assertEqual(p.commitment_due_l.sum(),20)

    def test_approvals_need_reason(self):
        with self.assertRaisesRegex(ValueError,"explain"):
            self.run_case(overrides=pd.DataFrame([dict(sku="TEST-1",approve_policy=True)]))

    def test_stage_override_needs_reason(self):
        with self.assertRaisesRegex(ValueError,"explain"):
            self.run_case(overrides=pd.DataFrame([dict(sku="TEST-1",stage_override="Decline")]))

    def test_commercial_status_does_not_force_demand_exit(self):
        data = fixture()
        data["Products"]["commercial_status"] = "Discontinued"
        r = self.run_case(data)
        self.assertEqual(r["classification"].iloc[0].stage,"Maturity")

    def test_supply_constraint_suspends_approved_policy(self):
        data = fixture()
        data["History"]["availability_pct"] = 60
        data["History"]["shipments_l"] = 60
        overrides = pd.DataFrame([dict(sku="TEST-1",approve_policy=True,reason="Review constrained supply")])
        r = self.run_case(data,overrides=overrides)
        self.assertEqual(r["classification"].iloc[0].confidence,"Suspended")
        self.assertFalse(r["policy"].approved.any())

    def test_short_history_preserves_prior_stage(self):
        data = fixture()
        data["History"] = data["History"].tail(3)
        data["Products"]["prior_stage"] = "Introduction"
        r = self.run_case(data)
        self.assertEqual(r["classification"].iloc[0].confidence,"Insufficient")
        self.assertEqual(r["classification"].iloc[0].stage,"Introduction")

    def test_exit_without_commitments_stops_routine_orders(self):
        data = fixture()
        data["Commitments"] = data["Commitments"].iloc[:0]
        data["Positions"]["commitments_included_l"] = 0
        overrides = pd.DataFrame([dict(sku="TEST-1",stage_override="Exit",approve_policy=True,reason="Dated commercial exit review")])
        r = self.run_case(data,overrides=overrides)
        self.assertEqual(r["simulation_paths"].query("scenario == 'Proposed'").ordered_l.sum(),0)

    def test_exit_replenishes_future_dated_deficit(self):
        data = fixture()
        data["Batches"] = data["Batches"].iloc[:0]
        data["Commitments"]["due_date"] = "2026-09-28"
        data["Commitments"]["quantity_l"] = 40
        data["Positions"]["forecast_next_month_l"] = 40
        data["Positions"]["commitments_included_l"] = 40
        overrides = pd.DataFrame([dict(sku="TEST-1",stage_override="Exit",approve_policy=True,reason="Dated obligation requires replenishment")])
        r = self.run_case(data,overrides=overrides)
        p = r["simulation_paths"].query("scenario == 'Proposed' and run == 1")
        self.assertEqual(p.ordered_l.sum(),40)
        self.assertEqual(p.commitment_served_l.sum(),40)

    def test_litres_conserved_and_capacity_respected(self):
        r = self.run_case()
        for _,p in r["simulation_paths"].groupby(["scenario","run"]):
            p=p.sort_values("week")
            balance=120+p.received_l.cumsum()-p.served_l.cumsum()-p.expired_l.cumsum()
            np.testing.assert_allclose(balance,p.stock_l,rtol=0,atol=1e-8)
            self.assertTrue((p.stock_l<=500+1e-9).all())
            self.assertTrue((p.served_l<=p.demand_l+1e-9).all())

    def test_cost_components_reconcile_without_inventory_principal(self):
        r = self.run_case()
        p = r["simulation_paths"]
        np.testing.assert_allclose(p.total_cost_inr,p.holding_cost_inr+p.expiry_cost_inr+p.shortage_cost_inr)

    def test_numeric_lead_time_sd_rejected(self):
        data = fixture()
        data["Products"]["lead_time_sd_days"] = "bad"
        with self.assertRaisesRegex(ValueError,"lead_time_sd_days"):
            self.run_case(data)

    def test_missing_location_history_rejected(self):
        data = fixture()
        row = data["Positions"].iloc[0].copy()
        row["location"] = "Missing depot"
        data["Positions"] = pd.concat([data["Positions"],row.to_frame().T],ignore_index=True)
        with self.assertRaisesRegex(ValueError,"SKU/location"):
            self.run_case(data)

    def test_stale_location_history_rejected(self):
        data = fixture()
        data["History"] = data["History"].iloc[:-1]
        with self.assertRaisesRegex(ValueError,"stale"):
            self.run_case(data)

    def test_bad_commercial_status_rejected(self):
        data = fixture()
        data["Products"]["commercial_status"] = "Invented"
        with self.assertRaisesRegex(ValueError,"commercial_status"):
            self.run_case(data)

    def test_owned_inventory_includes_pipeline_without_principal_cost(self):
        r = self.run_case()
        paths = r["simulation_paths"]
        np.testing.assert_allclose(paths.owned_inventory_value_inr,paths.inventory_value_inr+paths.pipeline_value_inr)
        np.testing.assert_allclose(paths.holding_cost_inr,paths.owned_inventory_value_inr*.18*7/365)
        self.assertIn("ending_pipeline_value_inr",r["simulation_summary"].metric.tolist())

    def test_commercial_hold_blocks_policy_approval(self):
        data = fixture()
        data["Products"]["commercial_status"] = "Hold"
        overrides = pd.DataFrame([dict(sku="TEST-1",approve_policy=True,reason="Local scenario review")])
        r = self.run_case(data,overrides=overrides)
        self.assertFalse(r["policy"].approved.any())
        self.assertIn("Hold",r["policy"].iloc[0].gate)

    def test_dated_rcr_consumes_stock_once_and_checks_customer_life(self):
        data = fixture()
        later = dict(commitment_id="C-2",sku="TEST-1",location="Mumbai",due_date="2026-10-19",quantity_l=100)
        data["Commitments"] = pd.concat([data["Commitments"],pd.DataFrame([later])],ignore_index=True)
        overrides = pd.DataFrame([dict(sku="TEST-1",stage_override="Exit",reason="Reviewed residual commitments")])
        r = self.run_case(data,overrides=overrides)
        dated = r["exit_coverage"]
        self.assertEqual(dated.eligible_stock_l.tolist(),[90,70])
        np.testing.assert_allclose(dated.rcr,[4.5,.7])
        self.assertEqual(dated.gap_l.tolist(),[0,30])

    def test_unsupported_frozen_launch_exposure_remains_missing(self):
        data = fixture()
        data["History"] = data["History"].tail(3)
        data["Products"]["prior_stage"] = "Introduction"
        r = self.run_case(data)
        row = r["stage_metrics"].query("metric == 'Frozen launch-plan exposure'").iloc[0]
        self.assertTrue(pd.isna(row.value))
        self.assertEqual(row.unit,"Not available")


if __name__ == "__main__":
    unittest.main(verbosity=2)
