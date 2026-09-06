"""Deterministic, wholly synthetic liquid-coatings data for Chain Reaction.

No Asian Paints operational records are used.  The trajectories intentionally
exercise review gates; they are not estimates of industry stage proportions.
make_demo() returns the seven input tables.  CLI exports JSON for the workbook
authoring step; this module does not write Excel files.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ORIGIN = "SYNTHETIC DEMONSTRATION — not Asian Paints operational data"
AS_OF = pd.Timestamp("2026-08-31")
LOCATIONS = ["Mumbai", "Delhi NCR", "Bengaluru", "Kolkata"]


def _pack(value: float, pack: int, *, minimum: int = 0) -> float:
    return float(max(minimum, round(max(0.0, value) / pack)) * pack)


def _curve(index: int, age: int, length: int) -> float:
    """Private generation recipe. No recipe/true-stage columns are exported."""
    if index < 6:
        return 0.35 + 0.105 * age
    if index < 12:
        return 0.42 * (1.058 ** age)
    if index < 22:
        return 1.0 + 0.001 * age
    if index < 29:
        return 1.3 if age < 16 else 1.3 * (0.875 ** (age - 15))
    if index < 33:
        return 1.05 if age < 15 else 1.05 * (0.69 ** (age - 14))
    if index == 34:
        if age < 12:
            return 1.15
        if age < 23:
            return 1.15 * (0.91 ** (age - 11))
        return 0.41 * (1.19 ** (age - 22))
    return 1.0


def make_demo(seed: int = 2608) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    months = pd.date_range(end=AS_OF, periods=30, freq="MS") + pd.offsets.MonthEnd(0)
    families = ["Interior emulsion", "Exterior emulsion", "Water-based primer", "Synthetic enamel", "Liquid waterproofing"]
    names = ["Velvet Matt", "Weather Coat", "Wall Base", "Gloss Enamel", "Roof Shield"]
    shades = ["White", "Ivory", "Sandstone", "Mist Grey", "Pale Blue", "Deep Base", "Terracotta", "Sea Green"]
    regional_weights = np.array([1.08, 1.00, 0.88, 0.72])
    products, history, positions, batches, commitments = [], [], [], [], []

    for idx in range(36):
        sku = f"PC-{idx + 1:03d}"
        fi = idx % len(families)
        pack_l = [1, 4, 10, 20][idx % 4]
        shelf = [270, 365, 180, 365, 270][fi]
        mrsl = [30, 45, 30, 45, 30][fi]
        cost = float([155, 195, 92, 175, 240][fi] + rng.integers(-12, 16))
        margin = float([65, 82, 38, 72, 95][fi] + rng.integers(-6, 9))
        prior_stage = ("Introduction" if idx < 6 else "Growth" if idx < 12 else
                       "Maturity" if idx < 22 else "Decline" if idx < 29 else
                       "Exit" if idx < 33 else "Decline" if idx == 34 else "Maturity")
        status = "Phase-out" if idx in (26, 27, 28, 29, 30) else "Discontinued" if idx in (31, 32) else "Active"
        # Linked replacement shares family, shade and pack. It remains a distinct
        # formulation: genealogy is context and does not authorise substitution.
        successor = f"PC-{idx - 20 + 1:03d}" if status != "Active" else ""
        lead = [10, 14, 7, 14, 12][fi]
        lead_sd = [2, 4, 2, 3, 3][fi]
        formulation = "Formula II" if idx < 20 else "Formula I"
        products.append(dict(sku=sku, product_name=f"{names[fi]} / {shades[(idx // 4) % 5]} / {pack_l} L / {formulation}",
                             family=families[fi], pack_l=pack_l, unit_cost_inr_l=cost,
                             unit_margin_inr_l=margin, shelf_life_days=shelf,
                             min_customer_life_days=mrsl, moq_l=float(pack_l * 6),
                             lead_time_days=lead, lead_time_sd_days=lead_sd,
                             prior_stage=prior_stage, commercial_status=status,
                             successor_sku=successor, data_origin=ORIGIN))
        length = [3, 4, 5, 6, 7, 8][idx] if idx < 6 else 30
        item_months = months[-length:]
        base = float(rng.uniform(270, 680))
        if idx == 35:
            base = 30.0  # A persistent niche: low volume does not imply Exit.

        for li, location in enumerate(LOCATIONS):
            local_base = base * regional_weights[li] * rng.uniform(0.91, 1.09)
            local_orders = []
            local_history = []
            for age, month in enumerate(item_months):
                # Mild recurring calendar variation: illustrative, not calibrated
                # to an actual festival/monsoon calendar or paint-sales history.
                season = 1.0 + 0.09 * np.sin(2 * np.pi * (month.month - 8) / 12)
                if fi == 4:
                    season += 0.07 * np.cos(2 * np.pi * (month.month - 5) / 12)
                expected = local_base * _curve(idx, age, length) * season
                order = _pack(expected * rng.lognormal(-0.002, 0.065), pack_l)
                if idx in (31, 32) and age >= 27:
                    order = float(pack_l if (age + li + idx) % 3 == 0 else 0)
                availability = float(np.clip(rng.normal(98.4, 0.9), 95.0, 100.0))
                fill = float(np.clip(rng.normal(0.988, 0.009), 0.95, 1.0))
                if idx == 33 and age >= 24:
                    # Stable captured orders, low supply availability, declining
                    # shipments: a deliberate false-decline diagnostic example.
                    availability = max(42.0, 74.0 - (age - 24) * 4.5 + li)
                    fill = availability / 100
                # Random complete-pack fulfilment avoids a systematic one-pack
                # shortfall from flooring (which distorts low-volume niches).
                shipped = float(rng.binomial(int(order / pack_l), fill) * pack_l)
                # Historical forecasts use earlier order observations only.
                lagged = np.mean(local_orders[-3:]) if local_orders else local_base * _curve(idx, 0, length)
                forecast = _pack(lagged * rng.uniform(0.95, 1.05), pack_l)
                closing = _pack(max(order, forecast) * rng.uniform(0.7, 1.25), pack_l)
                local_history.append(dict(month=month.date().isoformat(), sku=sku, location=location,
                                          orders_l=order, shipments_l=shipped, forecast_l=forecast,
                                          availability_pct=round(availability, 2), closing_stock_l=closing))
                local_orders.append(order)

            next_forecast = _pack(float(np.mean(local_orders[-3:])), pack_l, minimum=1)
            due_quantities = [_pack(next_forecast * 0.10, pack_l), _pack(next_forecast * 0.13, pack_l)]
            if idx in (31, 32):
                # Explicit fulfilment obligations survive commercial withdrawal.
                due_quantities = [float(pack_l), 0.0]
            included = sum(due_quantities)
            next_forecast = max(next_forecast, included)
            for ci, (days, quantity) in enumerate(zip([7, 21], due_quantities)):
                if quantity > 0:
                    commitments.append(dict(commitment_id=f"C-{idx+1:03d}-{li+1}-{ci+1}", sku=sku,
                                            location=location, due_date=(AS_OF + pd.Timedelta(days=days)).date().isoformat(), quantity_l=quantity))
            if idx % 11 == 0:
                commitments.append(dict(commitment_id=f"C-{idx+1:03d}-{li+1}-3", sku=sku,
                                        location=location, due_date=(AS_OF + pd.Timedelta(days=49)).date().isoformat(),
                                        quantity_l=_pack(max(next_forecast * .18, pack_l), pack_l)))

            baseline_cover = 1.50 if idx < 22 else 3.40 if idx < 29 else 4.20 if idx < 33 else 1.50
            current_target = _pack(max(next_forecast * baseline_cover, pack_l * 6), pack_l)
            stock_factor = (0.65 if idx < 6 else 0.93 if idx < 12 else 1.2 if idx < 22 else
                            3.8 if idx < 29 else 5.0 if idx < 33 else 0.4 if idx == 33 else 1.35)
            onhand = _pack(max(next_forecast * stock_factor, pack_l * 4), pack_l)
            if idx in (29, 30, 31, 32):
                onhand = _pack(max(onhand, local_base * .38), pack_l)
            # A spatial imbalance across identical SKU/pack gives transfer gates
            # an interpretable demonstration case without substituting products.
            if idx in (22, 23, 24):
                onhand = _pack(onhand * (1.7 if li == 0 else .35 if li == 2 else 1), pack_l)
            capacity = _pack(max(current_target * 2.2, onhand * 1.2, next_forecast * 4.5, pack_l * 18), pack_l)
            positions.append(dict(sku=sku, location=location, current_order_up_to_l=current_target,
                                  current_review_days=7, service_floor_pct=95.0 if fi != 2 else 97.0,
                                  capacity_l=capacity, forecast_next_month_l=next_forecast,
                                  commitments_included_l=included, data_origin=ORIGIN))

            old_fraction = .58 if idx in range(22, 33) else .18
            old_quantity = _pack(onhand * old_fraction, pack_l)
            mid_quantity = _pack((onhand - old_quantity) * .42, pack_l)
            fresh_quantity = onhand - old_quantity - mid_quantity
            # Remaining life is a batch attribute. The product shelf-life input
            # is full life at manufacture and controls future synthetic receipts.
            remaining_days = [mrsl + 18 + (idx % 4) * 7, min(shelf - 20, mrsl + 95), shelf - 12]
            if idx in (25, 30):
                remaining_days[0] = mrsl - 5  # Already outside customer-life acceptance.
            for bi, (quantity, remaining) in enumerate(zip([old_quantity, mid_quantity, fresh_quantity], remaining_days)):
                if quantity > 0:
                    batches.append(dict(batch_id=f"B-{idx+1:03d}-{li+1}-{bi+1}", sku=sku, location=location,
                                        quantity_l=float(quantity), expiry_date=(AS_OF + pd.Timedelta(days=int(remaining))).date().isoformat()))
            local_history[-1]["closing_stock_l"] = float(onhand)
            history.extend(local_history)

    lanes = []
    transit = [[0, 4, 3, 5], [4, 0, 5, 4], [3, 5, 0, 5], [5, 4, 5, 0]]
    for i, source in enumerate(LOCATIONS):
        for j, destination in enumerate(LOCATIONS):
            if i != j:
                lanes.append(dict(source=source, destination=destination, transit_days=transit[i][j],
                                  cost_inr_l=float(3.0 + transit[i][j] * .65), capacity_l=2400.0,
                                  enabled=not (source == "Kolkata" and destination == "Bengaluru")))
    settings = [dict(parameter="as_of_date", value=AS_OF.date().isoformat(), explanation="Snapshot date; all History observations end on or before this date."),
                dict(parameter="data_origin", value=ORIGIN, explanation="Entire workbook is synthetic and intentionally illustrative; no company outcomes can be inferred."),
                dict(parameter="seed", value=seed, explanation="Deterministic generation seed. Trajectories, costs, constraints and inventory are team demonstration assumptions.")]
    result = {name: pd.DataFrame(rows) for name, rows in
              [("Products", products), ("History", history), ("Positions", positions),
               ("Batches", batches), ("Commitments", commitments), ("Lanes", lanes), ("Settings", settings)]}
    validate_demo(result)
    return result


def validate_demo(data: dict[str, pd.DataFrame]) -> None:
    p, h, pos, b, c = (data[x] for x in ["Products", "History", "Positions", "Batches", "Commitments"])
    assert len(p) == 36 and len(pos) == 144
    assert not p.sku.duplicated().any() and not pos.duplicated(["sku", "location"]).any()
    assert not h.duplicated(["month", "sku", "location"]).any()
    assert (h.shipments_l <= h.orders_l).all() and (h.orders_l >= 0).all()
    assert h.availability_pct.between(0, 100).all()
    assert pd.to_datetime(h.month).max() == AS_OF
    assert (p.min_customer_life_days < p.shelf_life_days).all()
    assert (pd.to_datetime(c.due_date) > AS_OF).all()
    assert (pd.to_datetime(b.expiry_date) > AS_OF).all()
    snapshot = h.loc[h.month == AS_OF.date().isoformat()].set_index(["sku", "location"]).closing_stock_l.sort_index()
    physical = b.groupby(["sku", "location"]).quantity_l.sum().sort_index()
    assert np.allclose(snapshot, physical)
    pos_indexed = pos.set_index(["sku", "location"]).sort_index()
    assert len(snapshot) == 144
    assert (physical <= pos_indexed.capacity_l).all()
    due_next30 = c.loc[pd.to_datetime(c.due_date) <= AS_OF + pd.Timedelta(days=30)]
    included = due_next30.groupby(["sku", "location"]).quantity_l.sum().reindex(pos_indexed.index, fill_value=0)
    assert np.allclose(included, pos_indexed.commitments_included_l)
    assert (pos.commitments_included_l <= pos.forecast_next_month_l).all()
    by_sku = p.set_index("sku")
    for row in p.loc[p.successor_sku != ""].itertuples():
        successor = by_sku.loc[row.successor_sku]
        assert row.family == successor.family and row.pack_l == successor.pack_l
        assert successor.commercial_status == "Active"
    for table, cols in [(h, ["orders_l", "shipments_l", "forecast_l", "closing_stock_l"]),
                        (b, ["quantity_l"]), (c, ["quantity_l"]),
                        (pos, ["current_order_up_to_l", "capacity_l", "forecast_next_month_l", "commitments_included_l"])]:
        merged = table.merge(p[["sku", "pack_l"]], on="sku", validate="many_to_one")
        for col in cols:
            assert np.allclose((merged[col] / merged.pack_l) % 1, 0), f"Non-pack quantity: {col}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="demo_tables.json")
    parser.add_argument("--seed", type=int, default=2608)
    args = parser.parse_args()
    tables = make_demo(args.seed)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({name: json.loads(frame.to_json(orient="records")) for name, frame in tables.items()},
                                 ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(target), "rows": {k: len(v) for k, v in tables.items()}, "checks": "passed"}))
