"""Auditable lifecycle decision support and paired, weekly FEFO what-if simulation.

No fitted result or simulated saving in this module is evidence of causal impact.
The five lifecycle outputs follow the submitted solution; numeric thresholds are
explicit demonstration controls, not estimated Asian Paints operating parameters.
"""
from __future__ import annotations

import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

STAGES = ["Introduction", "Growth", "Maturity", "Decline", "Exit"]
COMMERCIAL_STATUSES = ["Active", "Phase-out", "Discontinued", "Hold", "Relaunch"]
SCHEMA = {
    "Products": "sku product_name family pack_l unit_cost_inr_l unit_margin_inr_l shelf_life_days min_customer_life_days moq_l lead_time_days lead_time_sd_days prior_stage commercial_status successor_sku data_origin".split(),
    "History": "month sku location orders_l shipments_l forecast_l availability_pct closing_stock_l".split(),
    "Positions": "sku location current_order_up_to_l current_review_days service_floor_pct capacity_l forecast_next_month_l commitments_included_l data_origin".split(),
    "Batches": "batch_id sku location quantity_l expiry_date".split(),
    "Commitments": "commitment_id sku location due_date quantity_l".split(),
    "Lanes": "source destination transit_days cost_inr_l capacity_l enabled".split(),
    "Settings": "parameter value explanation".split(),
}


def default_controls():
    return dict(horizon_weeks=26, runs=30, seed=42, demand_shock_pct=0.0,
                lead_time_shock_pct=0.0, annual_holding_pct=18.0,
                shortage_penalty_multiplier=1.0, decline_cover_days=28,
                review_days=7, growth_cover_days=14, trend_threshold_pct=12.0,
                persistence_periods=2, min_history_months=6,
                expiry_buffer_days=7, transfer_approval=False,
                design_cycle_service_pct=95.0)


def _bool(value):
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if pd.isna(value):
        return False
    if str(value).strip().lower() in {"true", "1", "yes", "y"}:
        return True
    if str(value).strip().lower() in {"false", "0", "no", "n", "", "nan"}:
        return False
    raise ValueError(f"Expected True/False, received {value!r}.")


def _settings(data):
    return data["Settings"].set_index("parameter")["value"].to_dict()


def load_workbook(path):
    """Read the single workbook; formulas are never executed by this application."""
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Upload a .xlsx workbook using the supplied template.")
    if path.stat().st_size > 30 * 1024 * 1024:
        raise ValueError("Workbook exceeds the 30 MB local-demo limit.")
    with pd.ExcelFile(path, engine="openpyxl") as book:
        missing = set(SCHEMA) - set(book.sheet_names)
        if missing:
            raise ValueError("Missing worksheets: " + ", ".join(sorted(missing)))
        data = {name: pd.read_excel(book, sheet_name=name) for name in SCHEMA}
    return validate_data(data)


def validate_data(data):
    out = {}
    for name, columns in SCHEMA.items():
        if name not in data:
            raise ValueError(f"Missing worksheet {name}.")
        frame = data[name].copy()
        frame.columns = [str(x).strip() for x in frame.columns]
        if frame.columns.duplicated().any():
            raise ValueError(f"{name}: duplicate column headers.")
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: missing columns {', '.join(sorted(missing))}.")
        frame = frame[columns].dropna(how="all").reset_index(drop=True)
        if name in {"Products", "History", "Positions", "Settings"} and frame.empty:
            raise ValueError(f"{name} must contain data.")
        out[name] = frame
    for name in ["Products", "History", "Positions", "Batches", "Commitments"]:
        for col in ["sku", "location"]:
            if col in out[name]:
                if out[name][col].isna().any():
                    raise ValueError(f"{name}.{col}: blank identifiers are not allowed.")
                out[name][col] = out[name][col].astype(str).str.strip()
                if (out[name][col] == "").any():
                    raise ValueError(f"{name}.{col}: blank identifiers are not allowed.")
    out["Settings"]["parameter"] = out["Settings"]["parameter"].astype(str).str.strip()
    unique = {"Products": ["sku"], "History": ["month", "sku", "location"],
              "Positions": ["sku", "location"], "Batches": ["batch_id"],
              "Commitments": ["commitment_id"], "Lanes": ["source", "destination"],
              "Settings": ["parameter"]}
    for name, cols in unique.items():
        if out[name].duplicated(cols).any():
            raise ValueError(f"{name}: duplicate keys {', '.join(cols)}.")
    numeric = {
        "Products": ["pack_l", "unit_cost_inr_l", "unit_margin_inr_l", "shelf_life_days", "min_customer_life_days", "moq_l", "lead_time_days", "lead_time_sd_days"],
        "History": SCHEMA["History"][3:],
        "Positions": SCHEMA["Positions"][2:-1],
        "Batches": ["quantity_l"], "Commitments": ["quantity_l"],
        "Lanes": ["transit_days", "cost_inr_l", "capacity_l"]}
    for name, cols in numeric.items():
        for col in cols:
            out[name][col] = pd.to_numeric(out[name][col], errors="coerce")
            vals = out[name][col].to_numpy(dtype=float)
            if not np.isfinite(vals).all() or (vals < 0).any():
                raise ValueError(f"{name}.{col}: all entries must be finite non-negative numbers.")
    for name, col in [("History", "month"), ("Batches", "expiry_date"), ("Commitments", "due_date")]:
        out[name][col] = pd.to_datetime(out[name][col], errors="coerce").dt.normalize()
        if out[name][col].isna().any():
            raise ValueError(f"{name}.{col}: invalid date. Use real Excel dates or YYYY-MM-DD.")
    # Normalize monthly timestamps before the second duplicate check.
    out["History"]["month"] = out["History"]["month"].dt.to_period("M").dt.to_timestamp("M")
    if out["History"].duplicated(["month", "sku", "location"]).any():
        raise ValueError("History: more than one record per SKU/location/calendar month.")
    settings = _settings(out)
    if "as_of_date" not in settings:
        raise ValueError("Settings must define as_of_date.")
    try:
        as_of = pd.Timestamp(settings["as_of_date"]).normalize()
    except Exception as exc:
        raise ValueError("Settings.as_of_date is invalid.") from exc
    if pd.isna(as_of):
        raise ValueError("Settings.as_of_date is missing.")
    completed = as_of if as_of.is_month_end else as_of.replace(day=1) - pd.Timedelta(days=1)
    if (out["History"]["month"] > completed).any():
        raise ValueError("History must end at the latest completed month, without future observations.")
    if (out["Commitments"]["due_date"] <= as_of).any():
        raise ValueError("Commitments must be outstanding future obligations after as_of_date.")
    products = out["Products"]
    if not products["prior_stage"].isin(STAGES).all():
        raise ValueError("Products.prior_stage must use Introduction, Growth, Maturity, Decline or Exit.")
    status_map = {status.lower(): status for status in COMMERCIAL_STATUSES}
    products["commercial_status"] = products["commercial_status"].astype(str).str.strip().str.lower().map(status_map)
    if products["commercial_status"].isna().any():
        raise ValueError("Products.commercial_status must be Active, Phase-out, Discontinued, Hold or Relaunch.")
    if (products[["pack_l", "unit_cost_inr_l", "shelf_life_days", "moq_l"]] <= 0).any().any():
        raise ValueError("Products pack size, unit cost, shelf life and MOQ must be positive.")
    if (products["min_customer_life_days"] >= products["shelf_life_days"]).any():
        raise ValueError("Minimum customer life must be less than shelf life.")
    if (out["Positions"]["current_review_days"] <= 0).any():
        raise ValueError("Positions.current_review_days must be positive.")
    if (out["Positions"]["capacity_l"] <= 0).any():
        raise ValueError("Positions.capacity_l must be positive.")
    for name, col in [("History", "availability_pct"), ("Positions", "service_floor_pct")]:
        if (out[name][col] > 100).any():
            raise ValueError(f"{name}.{col}: use percentages from 0 to 100.")
    if (out["History"]["shipments_l"] > out["History"]["orders_l"] + 1e-6).any():
        raise ValueError("History shipments exceed same-period orders. This MVP assumes no backlog/catch-up shipments; reconcile before upload.")
    positions = out["Positions"]
    if (positions["commitments_included_l"] > positions["forecast_next_month_l"] + 1e-6).any():
        raise ValueError("Commitments included in the forecast cannot exceed that forecast.")
    known = set(products.sku)
    pairs = set(zip(positions.sku, positions.location))
    for name in ["History", "Positions", "Batches", "Commitments"]:
        if not set(out[name].sku).issubset(known):
            raise ValueError(f"{name}: unknown SKU identifier.")
        if "location" in out[name] and not set(zip(out[name].sku, out[name].location)).issubset(pairs):
            raise ValueError(f"{name}: SKU/location not listed in Positions.")
    if known != set(positions.sku):
        raise ValueError("Every product needs at least one Position.")
    if known != set(out["History"].sku):
        raise ValueError("Every product needs historical observations, even for a launch.")
    packs = products.set_index("sku").pack_l
    for table in ["Batches","Commitments"]:
        counts = out[table].quantity_l / out[table].sku.map(packs)
        if not np.allclose(counts, np.round(counts), rtol=0, atol=1e-7):
            raise ValueError(f"{table}.quantity_l must contain whole sealed-pack multiples of Products.pack_l.")
    if set(zip(out["History"].sku, out["History"].location)) != pairs:
        raise ValueError("Every SKU/location in Positions needs historical observations, even for a launch.")
    newest = out["History"].groupby(["sku", "location"]).month.max()
    if (newest < completed).any():
        raise ValueError("History is stale for at least one SKU/location: include the latest completed month, recording observed zero demand explicitly.")
    out["Lanes"]["enabled"] = out["Lanes"]["enabled"].map(_bool)
    locations = set(positions.location)
    if not (set(out["Lanes"].source) | set(out["Lanes"].destination)).issubset(locations):
        raise ValueError("Lanes contain a source/destination not listed in Positions.")
    if (out["Lanes"].source == out["Lanes"].destination).any():
        raise ValueError("A transfer lane must connect different locations.")
    commitments30 = out["Commitments"].loc[out["Commitments"].due_date <= as_of + pd.Timedelta(days=30)].groupby(["sku", "location"]).quantity_l.sum()
    for row in positions.itertuples():
        scheduled = float(commitments30.get((row.sku, row.location), 0))
        if row.commitments_included_l > scheduled + 1e-6:
            raise ValueError(f"{row.sku}/{row.location}: included commitments exceed dated obligations within 30 days.")
    return out


def _controls(controls):
    c = default_controls()
    c.update(controls or {})
    bounds = {"horizon_weeks": (1, 104), "runs": (1, 200), "seed": (0, 2**31-1),
              "demand_shock_pct": (-100, 200), "lead_time_shock_pct": (-100, 300),
              "annual_holding_pct": (0, 100), "shortage_penalty_multiplier": (0, 10),
              "decline_cover_days": (1, 180), "review_days": (1, 60),
              "growth_cover_days": (0, 90), "trend_threshold_pct": (1, 80),
              "persistence_periods": (1, 6), "min_history_months": (3, 24),
              "expiry_buffer_days": (0, 120), "design_cycle_service_pct": (50, 99.9)}
    for key, (lo, hi) in bounds.items():
        try:
            c[key] = float(c[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Control {key} must be numeric.") from exc
        if not np.isfinite(c[key]) or not lo <= c[key] <= hi:
            raise ValueError(f"Control {key} must be between {lo} and {hi}.")
    for key in ["horizon_weeks", "runs", "seed", "persistence_periods", "min_history_months"]:
        c[key] = int(c[key])
    c["transfer_approval"] = _bool(c["transfer_approval"])
    return c


def _override_map(overrides, known):
    if overrides is None:
        return {}
    frame = pd.DataFrame(overrides).copy()
    if frame.empty:
        return {}
    if "sku" not in frame:
        raise ValueError("Human input table must include sku.")
    if frame.sku.duplicated().any() or not set(frame.sku).issubset(known):
        raise ValueError("Human input table has duplicate/unknown SKUs.")
    records = {}
    for row in frame.to_dict("records"):
        stage = str(row.get("stage_override", "Auto")).strip()
        if stage in {"", "nan", "None"}:
            stage = "Auto"
        if stage not in STAGES + ["Auto"]:
            raise ValueError(f"{row['sku']}: invalid stage override.")
        approved = _bool(row.get("approve_policy", False))
        reason = str(row.get("reason", "") or "").strip()
        if reason.lower() in {"nan", "none"}:
            reason = ""
        if (stage != "Auto" or approved) and len(reason) < 5:
            raise ValueError(f"{row['sku']}: explain every override/approval with at least five characters.")
        records[row["sku"]] = dict(stage_override=stage, approved=approved, reason=reason,
                                    commercial_status=row.get("commercial_status"))
    return records


def _candidate(y, threshold, min_history):
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < min_history:
        return "Introduction", np.nan, 1.0, "Short launch history"
    recent = float(np.mean(y[-3:]))
    smooth = pd.Series(y).rolling(3, min_periods=1).mean()
    peak = float(smooth.max())
    ratio = recent / peak if peak > 0 else 0.0
    if n >= 15:
        reference = float(np.mean(y[-15:-12]))
        method = "Recent three months / same months last year"
    else:
        reference = float(np.mean(y[-6:-3]))
        method = "Recent / previous three months; seasonal evidence limited"
    trend = 100 * (recent / reference - 1) if reference > 1e-9 else (100.0 if recent > 0 else 0.0)
    if peak > 0 and ratio <= 0.05 and np.all(y[-3:] <= max(peak * 0.05, 1e-9)):
        return "Exit", trend, ratio, method
    if trend > threshold:
        return "Growth", trend, ratio, method
    if trend < -threshold and ratio < 0.85:
        return "Decline", trend, ratio, method
    return "Maturity", trend, ratio, method


def _classify(data, c, overrides):
    rows = []
    for p in data["Products"].itertuples():
        h = data["History"].loc[data["History"].sku == p.sku].sort_values("month")
        national = h.groupby("month").orders_l.sum()
        expected_months = pd.period_range(national.index.min(), national.index.max(), freq="M")
        missing_months = len(expected_months) - len(national)
        for _, local in h.groupby("location"):
            expected_local = len(pd.period_range(local.month.min(),local.month.max(),freq="M"))
            missing_months += expected_local-local.month.nunique()
        y = national.to_numpy(float)
        recent = h.loc[h.month.isin(national.index[-3:])]
        availability = float(recent.availability_pct.mean())
        fill = 100 * recent.shipments_l.sum() / recent.orders_l.sum() if recent.orders_l.sum() else 100.0
        observable = "Observable" if availability >= 90 and fill >= 85 else "Supply constrained"
        candidate, trend, peak, method = _candidate(y, c["trend_threshold_pct"], c["min_history_months"])
        persistence = 0
        for offset in range(c["persistence_periods"]):
            past = y[:len(y)-offset]
            if len(past) < 3 or _candidate(past, c["trend_threshold_pct"], c["min_history_months"])[0] != candidate:
                break
            persistence += 1
        confidence = "High" if len(y) >= 15 else "Medium"
        reasons = [method]
        if len(y) < c["min_history_months"]:
            confidence = "Insufficient"
            reasons.append("Insufficient history; preserve prior stage pending launch review")
        elif missing_months:
            confidence = "Low"
            reasons.append("Missing calendar months; do not treat missing demand as zero")
        elif observable != "Observable":
            confidence = "Suspended"
            reasons.append("Supply constraint: review captured orders and availability before action")
        elif persistence < c["persistence_periods"]:
            confidence = "Low"
            reasons.append("Candidate fails persistence gate")
        active = recent.loc[recent.orders_l > 0].location.nunique()
        locations = data["Positions"].loc[data["Positions"].sku == p.sku].location.nunique()
        prior_active = h.loc[h.month.isin(national.index[-6:-3]) & (h.orders_l > 0)].location.nunique()
        stage = candidate if confidence in {"High", "Medium"} else p.prior_stage
        override = overrides.get(p.sku, {})
        if override.get("stage_override", "Auto") != "Auto":
            stage = override["stage_override"]
            reasons.append("Human stage override recorded")
        status = override.get("commercial_status")
        if status is None or pd.isna(status) or str(status).strip() == "":
            status = p.commercial_status
        status = {x.lower():x for x in COMMERCIAL_STATUSES}.get(str(status).strip().lower())
        if status is None:
            raise ValueError(f"{p.sku}: commercial status must be Active, Phase-out, Discontinued, Hold or Relaunch.")
        if status != p.commercial_status and len(override.get("reason", "")) < 5:
            raise ValueError(f"{p.sku}: explain the commercial-status override with at least five characters.")
        # Context guides review; it never imposes a lifecycle sequence or forecasts a curve.
        if len(y) < c["min_history_months"]:
            archetype = "Launch / insufficient curve history"
        elif len(y) >= 15 and trend > c["trend_threshold_pct"] and peak < 0.8:
            archetype = "Possible recovery / second growth"
        elif np.count_nonzero(y[-12:] == 0) >= 3:
            archetype = "Intermittent / niche context"
        elif candidate == "Exit":
            archetype = "Residual tail context"
        elif candidate == "Decline":
            archetype = "Fading demand context"
        elif candidate == "Growth":
            archetype = "Rising adoption context"
        else:
            archetype = "Persistent demand / seasonality review"
        family_skus = data["Products"].loc[data["Products"].family==p.family,"sku"]
        family_series = data["History"].loc[data["History"].sku.isin(family_skus)].groupby("month").orders_l.sum().sort_index()
        _,family_trend,_,_ = _candidate(family_series.to_numpy(float),c["trend_threshold_pct"],c["min_history_months"])
        relative = trend-family_trend if np.isfinite(trend) and np.isfinite(family_trend) else np.nan
        rows.append(dict(sku=p.sku, product_name=p.product_name, family=p.family,
                         prior_stage=p.prior_stage, candidate_stage=candidate, stage=stage,
                         confidence=confidence, observability=observable, history_months=len(y),
                         trend_pct=trend, peak_ratio=peak, active_location_pct=100 * active / max(locations, 1),
                         breadth_change_locations=active-prior_active, persistence_count=persistence,
                         commercial_status=str(status), override_reason=override.get("reason", ""),
                         decision_reason="; ".join(reasons), availability_pct=availability,
                         recent_fill_pct=fill,category_trend_pct=family_trend,
                         category_relative_growth_pp=relative,archetype_context=archetype))
    return pd.DataFrame(rows)


def _round_pack(quantity, pack, moq=0):
    if quantity <= 1e-9:
        return 0.0
    return float(math.ceil(max(quantity, moq) / pack - 1e-10) * pack)


def _policies(data, c, classification, overrides, as_of):
    rows = []
    products = data["Products"].set_index("sku")
    classes = classification.set_index("sku")
    for pos in data["Positions"].itertuples():
        p = products.loc[pos.sku]
        cl = classes.loc[pos.sku]
        h = data["History"].loc[(data["History"].sku == pos.sku) & (data["History"].location == pos.location)].sort_values("month")
        batches = data["Batches"].loc[(data["Batches"].sku == pos.sku) & (data["Batches"].location == pos.location)]
        commitments = data["Commitments"].loc[(data["Commitments"].sku == pos.sku) & (data["Commitments"].location == pos.location)]
        usable_days = (batches.expiry_date - as_of).dt.days - p.min_customer_life_days - c["expiry_buffer_days"]
        stock = float(batches.quantity_l.sum())
        usable = float(batches.loc[usable_days > 0, "quantity_l"].sum())
        base_monthly = max(0.0, pos.forecast_next_month_l - pos.commitments_included_l)
        mu = base_monthly / 30.4375 * (1 + c["demand_shock_pct"] / 100)
        # Monthly forecast error SD converted using independent increments. Explicitly a proxy.
        errors = (h.orders_l - h.forecast_l).tail(12)
        sigma_daily = float(errors.std(ddof=1) / math.sqrt(30.4375)) if len(errors) >= 3 else 0.0
        sigma_daily = max(sigma_daily, math.sqrt(max(mu, 0.0)))
        lead = p.lead_time_days * (1 + c["lead_time_shock_pct"] / 100)
        lead_sd = p.lead_time_sd_days * (1 + c["lead_time_shock_pct"] / 100)
        review = math.ceil(c["review_days"] / 7) * 7
        protection = lead + review
        z = NormalDist().inv_cdf(c["design_cycle_service_pct"] / 100)
        safety = z * math.sqrt(sigma_daily**2 * protection + mu**2 * lead_sd**2)
        commitment_floor = float(commitments.loc[commitments.due_date <= as_of + pd.Timedelta(days=math.ceil(protection)), "quantity_l"].sum())
        service_design = mu * protection + safety + commitment_floor
        stage = cl.stage
        if stage == "Growth":
            proposed = service_design + mu * c["growth_cover_days"]
            action = "Review growth cover; preserve local service floor"
        elif stage == "Introduction":
            proposed = service_design
            action = "Small controlled launch replenishment; confirm observations"
        elif stage == "Maturity":
            proposed = service_design
            action = "Review replenishment against stable demand and local constraints"
        elif stage == "Decline":
            proposed = min(pos.current_order_up_to_l, max(service_design, mu * c["decline_cover_days"] + commitment_floor))
            action = "Reduce routine exposure only after local service and life checks"
        else:
            proposed = commitment_floor
            action = "Stop routine replenishment; preserve dated commitment deficits"
        if cl.commercial_status == "Discontinued":
            proposed = commitment_floor
            action = "Commercial stop: routine replenishment off; dated commitment deficits protected"
        elif cl.commercial_status == "Phase-out":
            proposed = min(proposed,pos.current_order_up_to_l)
            action += "; commercial phase-out prevents routine stock expansion"
        max_life = max(0, p.shelf_life_days - p.min_customer_life_days - c["expiry_buffer_days"] - lead)
        life_capacity = mu * max_life + float(commitments.quantity_l.sum())
        cap = min(pos.capacity_l, max(life_capacity, commitment_floor))
        proposed = min(_round_pack(proposed, p.pack_l), math.floor(cap / p.pack_l) * p.pack_l)
        proposed = max(0.0, proposed)
        override = overrides.get(pos.sku, {})
        approval = override.get("approved", False)
        gate = "Awaiting human approval"
        if approval:
            if cl.commercial_status == "Hold":
                approval = False
                gate = "Blocked: commercial Hold requires explicit status resolution"
            elif cl.confidence == "Suspended":
                approval = False
                gate = "Blocked: resolve supply observability before policy change"
            elif cl.confidence == "Insufficient" and override.get("stage_override", "Auto") == "Auto":
                approval = False
                gate = "Blocked: insufficient history; explicit launch-stage review required"
            else:
                gate = "Approved for local what-if simulation only"
        if proposed + 1e-6 < min(service_design, commitment_floor if stage == "Exit" else service_design):
            gate += "; service/MOQ/life/capacity trade-off requires review"
        floor_short = commitment_floor > proposed + 1e-6
        if floor_short:
            approval = False
            gate = "Blocked: capacity/usable life cannot protect commitment floor"
        total_demand_month = base_monthly * (1 + c["demand_shock_pct"] / 100) + float(commitments.loc[commitments.due_date <= as_of + pd.Timedelta(days=30), "quantity_l"].sum())
        cover = stock / (total_demand_month / 30.4375) if total_demand_month > 0 else np.nan
        positive = usable_days > 0
        weighted_horizon = float(np.average(usable_days[positive], weights=batches.loc[positive, "quantity_l"])) if usable > 0 else 0.0
        exposure_denominator = mu * weighted_horizon + float(commitments.loc[commitments.due_date <= as_of + pd.Timedelta(days=max(0, int(weighted_horizon))), "quantity_l"].sum())
        eri = stock / exposure_denominator if exposure_denominator > 0 else (np.inf if stock > 0 else 0)
        rows.append(dict(sku=pos.sku, location=pos.location, stage=stage, confidence=cl.confidence,
                         current_order_up_to_l=float(pos.current_order_up_to_l), proposed_order_up_to_l=proposed,
                         effective_order_up_to_l=proposed if approval else float(pos.current_order_up_to_l),
                         current_review_days=float(pos.current_review_days), effective_review_days=review if approval else float(pos.current_review_days),
                         safety_stock_l=safety, cycle_stock_l=mu*review/2, commitment_floor_l=commitment_floor,
                         usable_stock_l=usable, stock_l=stock, cover_days=cover, eri=eri,
                         service_floor_pct=float(pos.service_floor_pct), approved=bool(approval), gate=gate,
                         action=action, unit_cost_inr_l=float(p.unit_cost_inr_l), capacity_l=float(pos.capacity_l),
                         mean_daily_demand_l=mu, design_cycle_service_pct=c["design_cycle_service_pct"],
                         commercial_status=cl.commercial_status))
    return pd.DataFrame(rows)


def _batch_screen(data, c, policy, as_of):
    """Allocate deterministic residual demand + each dated commitment once in FEFO order."""
    rows = []
    products = data["Products"].set_index("sku")
    for pos in policy.itertuples():
        p = products.loc[pos.sku]
        batches = data["Batches"].loc[(data["Batches"].sku == pos.sku) & (data["Batches"].location == pos.location)].sort_values("expiry_date")
        obligations = data["Commitments"].loc[(data["Commitments"].sku == pos.sku) & (data["Commitments"].location == pos.location)]
        allocated = 0.0
        for b in batches.itertuples():
            horizon = max(0, int((b.expiry_date-as_of).days - p.min_customer_life_days - c["expiry_buffer_days"]))
            available_demand = pos.mean_daily_demand_l * horizon + float(obligations.loc[obligations.due_date <= as_of + pd.Timedelta(days=horizon), "quantity_l"].sum())
            consumed = min(float(b.quantity_l), max(0.0, available_demand - allocated))
            allocated += consumed
            exposed = float(b.quantity_l) - consumed
            rows.append(dict(batch_id=b.batch_id, sku=b.sku, location=b.location,
                             expiry_date=b.expiry_date.strftime("%Y-%m-%d"), quantity_l=float(b.quantity_l),
                             usable_days=horizon, expected_consumption_l=consumed, at_risk_l=exposed,
                             at_risk_value_inr=exposed*p.unit_cost_inr_l,
                             screen="No customer-usable life" if horizon == 0 else "Exposure" if exposed > 0 else "Covered by projected demand"))
    columns = "batch_id sku location expiry_date quantity_l usable_days expected_consumption_l at_risk_l at_risk_value_inr screen".split()
    return pd.DataFrame(rows, columns=columns)


def _transfer_screen(data, c, policy, batch_risk, as_of):
    """Greedy bounded candidate moves; no substitution, no optimization or benefit credit."""
    columns = "sku batch_id source destination quantity_l transit_days movement_cost_inr gross_book_exposure_inr status reason".split()
    rows = []
    products = data["Products"].set_index("sku")
    pp = policy.set_index(["sku", "location"])
    lane_remaining = {(r.source, r.destination): r.capacity_l for r in data["Lanes"].itertuples() if r.enabled}
    destination_added = {}
    source_remaining = {(r.sku,r.location):max(0.0,r.usable_stock_l-r.commitment_floor_l-r.safety_stock_l) for r in policy.itertuples()}
    for b in batch_risk.sort_values(["usable_days", "at_risk_l"], ascending=[True, False]).itertuples():
        p = products.loc[b.sku]
        source = pp.loc[(b.sku, b.location)]
        remaining = min(b.at_risk_l, source_remaining[(b.sku,b.location)])
        for lane in data["Lanes"].loc[(data["Lanes"].source == b.location) & data["Lanes"].enabled].sort_values("cost_inr_l").itertuples():
            if (b.sku, lane.destination) not in pp.index or remaining < p.pack_l:
                continue
            dest = pp.loc[(b.sku, lane.destination)]
            days = b.usable_days - lane.transit_days
            added = destination_added.get((b.sku, lane.destination), 0.0)
            # Conservative destination need: no credit for source decline at destination.
            destination_need = max(0.0, dest.mean_daily_demand_l*max(days, 0) - dest.stock_l - added)
            capacity = max(0.0, dest.capacity_l-dest.stock_l-added)
            quantity = math.floor(min(remaining, destination_need, capacity, lane_remaining[(lane.source, lane.destination)]) / p.pack_l) * p.pack_l
            if quantity <= 0 or days <= 0:
                continue
            rows.append(dict(sku=b.sku, batch_id=b.batch_id, source=b.location, destination=lane.destination,
                             quantity_l=quantity, transit_days=lane.transit_days,
                             movement_cost_inr=quantity*lane.cost_inr_l,
                             gross_book_exposure_inr=quantity*p.unit_cost_inr_l,
                             status="Candidate only; excluded from simulation",
                             reason="Same SKU; source buffer/commitments, destination demand, life and lane capacity screened. Economics unvalidated: compare expected avoided loss with movement cost."))
            remaining -= quantity
            source_remaining[(b.sku,b.location)] -= quantity
            lane_remaining[(lane.source, lane.destination)] -= quantity
            destination_added[(b.sku, lane.destination)] = added + quantity
    return pd.DataFrame(rows, columns=columns)


def _take_fefo(lots, requested, date, customer_life):
    served = 0.0
    for lot in sorted(lots, key=lambda x: x[0]):
        if lot[0] >= date + customer_life and requested > 0:
            take = min(lot[1], requested)
            lot[1] -= take
            served += take
            requested -= take
    return served


def _simulate(data, c, policy, as_of):
    weeks, runs = c["horizon_weeks"], c["runs"]
    products = data["Products"].set_index("sku")
    rng = np.random.default_rng(c["seed"])
    # Aggregate each run's weekly stock/flow outcomes and preserve local service evidence.
    keys = "stock_l inventory_value_inr demand_l served_l expired_l holding_cost_inr expiry_cost_inr shortage_cost_inr total_cost_inr commitment_due_l commitment_served_l ordered_l received_l pipeline_l pipeline_value_inr owned_inventory_value_inr".split()
    cube = np.zeros((2, runs, weeks, len(keys)), dtype=float)
    loc_rows = []
    for pos in policy.itertuples():
        p = products.loc[pos.sku]
        h = data["History"].loc[(data["History"].sku == pos.sku) & (data["History"].location == pos.location)].sort_values("month").tail(12)
        historic_mean = h.orders_l.mean()
        monthly_cv = float(h.orders_l.std(ddof=1)/historic_mean) if len(h)>1 and historic_mean>0 else 0.35
        weekly_cv = min(1.5, max(0.15, monthly_cv*math.sqrt(30.4375/7)))
        log_sd = math.sqrt(math.log(1+weekly_cv**2))
        residual_demand = rng.lognormal(-log_sd**2/2, log_sd, size=(runs, weeks))*pos.mean_daily_demand_l*7
        residual_demand = np.round(residual_demand/p.pack_l)*p.pack_l
        lt_random = rng.standard_normal((runs, weeks))
        schedule = np.zeros(weeks, dtype=float)
        obligations = data["Commitments"].loc[(data["Commitments"].sku == pos.sku) & (data["Commitments"].location == pos.location)]
        for ob in obligations.itertuples():
            index = max(0, math.ceil((ob.due_date-as_of).days/7)-1)
            if index < weeks:
                schedule[index] += ob.quantity_l
        starting = data["Batches"].loc[(data["Batches"].sku == pos.sku) & (data["Batches"].location == pos.location)]
        initial_lots = [[float((b.expiry_date-as_of).days), float(b.quantity_l)] for b in starting.itertuples()]
        for scenario in range(2):
            approved = scenario == 1 and pos.approved
            target = pos.effective_order_up_to_l if approved else pos.current_order_up_to_l
            review_days = pos.effective_review_days if approved else pos.current_review_days
            review_weeks = max(1, math.ceil(review_days/7))
            exit_policy = approved and (pos.stage == "Exit" or pos.commercial_status == "Discontinued")
            for run in range(runs):
                lots = [lot[:] for lot in initial_lots]
                pipeline = []
                local_demand = local_served = local_due = local_committed = 0.0
                for week in range(weeks):
                    start_day, end_day = week*7, (week+1)*7
                    expired = sum(lot[1] for lot in lots if lot[0] <= start_day)
                    lots = [lot for lot in lots if lot[0] > start_day and lot[1] > 1e-9]
                    received = 0.0
                    # Receipts have manufacturing life minus transport time; excess waits outside depot.
                    still_pending = []
                    for arrival, expiration, quantity in pipeline:
                        if expiration <= start_day:
                            expired += quantity
                        elif arrival <= week:
                            space = max(0.0, pos.capacity_l-sum(x[1] for x in lots))
                            accepted = min(quantity, math.floor(space/p.pack_l)*p.pack_l)
                            if accepted:
                                lots.append([expiration, accepted])
                                received += accepted
                            if quantity-accepted > 1e-9:
                                still_pending.append((week+1, expiration, quantity-accepted))
                        else:
                            still_pending.append((arrival, expiration, quantity))
                    pipeline = still_pending
                    ordered = 0.0
                    customer_life = p.min_customer_life_days + c["expiry_buffer_days"]
                    usable = sum(q for exp, q in lots if exp >= end_day+customer_life)
                    if week % review_weeks == 0:
                        lead_days = max(0.0, (p.lead_time_days+p.lead_time_sd_days*lt_random[run,week])*(1+c["lead_time_shock_pct"]/100))
                        lead_weeks = max(1, math.ceil(lead_days/7))
                        protect_end = min(weeks, week+lead_weeks+review_weeks)
                        if exit_policy:
                            target_now = float(schedule[week:protect_end].sum())
                        else:
                            # Forecast target already reserves initial protection-period commitments.
                            # Replace that dated floor with the current protection-period obligation.
                            target_now = target
                            if approved:
                                target_now = max(0.0, target-pos.commitment_floor_l) + float(schedule[week:protect_end].sum())
                        inventory_position = usable + sum(q for _, exp, q in pipeline if exp >= end_day+customer_life)
                        need = max(0.0, target_now-inventory_position)
                        ordered = _round_pack(need, p.pack_l, p.moq_l)
                        # Storage constraint covers on-hand and pipeline to avoid capacity over-ordering.
                        free = max(0.0, pos.capacity_l-sum(x[1] for x in lots)-sum(x[2] for x in pipeline))
                        if ordered > free:
                            ordered = math.floor(free/p.pack_l)*p.pack_l
                            if ordered+1e-9 < p.moq_l:
                                ordered = 0.0
                        if p.shelf_life_days <= lead_weeks*7+customer_life:
                            ordered = 0.0
                        if ordered > 0:
                            pipeline.append((week+lead_weeks, start_day+p.shelf_life_days, ordered))
                    due = schedule[week]
                    committed_served = _take_fefo(lots, due, end_day, customer_life)
                    ordinary = residual_demand[run,week]
                    # Preserve customer-usable stock required for known obligations before next receipt.
                    reserve_end = min(weeks, week+max(1, math.ceil(p.lead_time_days*(1+c["lead_time_shock_pct"]/100)/7)))
                    future_reserve = float(schedule[week+1:reserve_end+1].sum())
                    serviceable = sum(q for exp,q in lots if exp >= end_day+customer_life)
                    ordinary_served = _take_fefo(lots, min(ordinary,max(0.0,serviceable-future_reserve)), end_day, customer_life)
                    served = committed_served+ordinary_served
                    demand = due+ordinary
                    # Write-off when product actually expires; customer-life quarantine is not immediate write-off.
                    expired += sum(q for exp,q in lots if exp <= end_day)
                    lots = [[exp,q] for exp,q in lots if exp>end_day and q>1e-9]
                    stock = sum(q for _,q in lots)
                    value = stock*p.unit_cost_inr_l
                    pipeline_stock = sum(q for _,_,q in pipeline)
                    pipeline_value = pipeline_stock*p.unit_cost_inr_l
                    owned_value = value+pipeline_value
                    holding = owned_value*c["annual_holding_pct"]/100*7/365
                    expiry_cost = expired*p.unit_cost_inr_l
                    shortage_cost = max(0.0,demand-served)*p.unit_margin_inr_l*c["shortage_penalty_multiplier"]
                    total = holding+expiry_cost+shortage_cost
                    cube[scenario,run,week] += np.array([stock,value,demand,served,expired,holding,expiry_cost,shortage_cost,total,due,committed_served,ordered,received,pipeline_stock,pipeline_value,owned_value])
                    local_demand += demand
                    local_served += served
                    local_due += due
                    local_committed += committed_served
                loc_rows.append(dict(sku=pos.sku,location=pos.location,run=run+1,
                                     scenario="Proposed" if scenario else "Baseline",stage=pos.stage,
                                     demand_l=local_demand,served_l=local_served,
                                     fill_pct=100*local_served/local_demand if local_demand else 100.0,
                                     service_floor_pct=pos.service_floor_pct,commitment_due_l=local_due,
                                     commitment_served_l=local_committed))
    path_rows = []
    run_rows = []
    for scenario in range(2):
        for run in range(runs):
            block = cube[scenario,run]
            for week in range(weeks):
                row = dict(zip(keys,block[week]))
                row.update(run=run+1,scenario="Proposed" if scenario else "Baseline",week=week+1,
                           date=(as_of+pd.Timedelta(days=(week+1)*7)).strftime("%Y-%m-%d"))
                path_rows.append(row)
            sums = dict(zip(keys,block.sum(axis=0)))
            row = dict(run=run+1,scenario="Proposed" if scenario else "Baseline",
                       fill_pct=100*sums["served_l"]/sums["demand_l"] if sums["demand_l"] else 100.0,
                       average_stock_l=float(block[:,0].mean()), average_inventory_value_inr=float(block[:,1].mean()),
                       ending_inventory_value_inr=float(block[-1,1]),
                       average_owned_inventory_value_inr=float(block[:,-1].mean()),
                       ending_owned_inventory_value_inr=float(block[-1,-1]),
                       ending_pipeline_value_inr=float(block[-1,-2]),
                       expiry_l=sums["expired_l"],holding_cost_inr=sums["holding_cost_inr"],
                       expiry_cost_inr=sums["expiry_cost_inr"],shortage_cost_inr=sums["shortage_cost_inr"],
                       total_cost_inr=sums["total_cost_inr"],
                       commitment_fill_pct=100*sums["commitment_served_l"]/sums["commitment_due_l"] if sums["commitment_due_l"] else 100.0)
            run_rows.append(row)
    paths, run_results, local_results = pd.DataFrame(path_rows),pd.DataFrame(run_rows),pd.DataFrame(loc_rows)
    summary = []
    for metric in run_results.columns[2:]:
        base = run_results.loc[run_results.scenario=="Baseline",metric].to_numpy()
        proposed = run_results.loc[run_results.scenario=="Proposed",metric].to_numpy()
        higher = metric in {"fill_pct","commitment_fill_pct"}
        unit = "%" if metric.endswith("pct") else "INR" if metric.endswith("inr") else "L"
        summary.append(dict(metric=metric,unit=unit,baseline_mean=float(base.mean()),proposed_mean=float(proposed.mean()),
                            baseline_p10=float(np.quantile(base,.1)),baseline_p90=float(np.quantile(base,.9)),
                            proposed_p10=float(np.quantile(proposed,.1)),proposed_p90=float(np.quantile(proposed,.9)),
                            improvement_mean=float((proposed-base if higher else base-proposed).mean())))
    return pd.DataFrame(summary),paths,run_results,local_results


def _dated_coverage(data, policy, c, as_of):
    """Per-position dated RCR, allocating current eligible inventory only once."""
    columns = "sku location due_date commitment_l eligible_stock_l rcr served_from_current_stock_l gap_l".split()
    products = data["Products"].set_index("sku")
    rows = []
    for pos in policy.loc[policy.stage=="Exit"].itertuples():
        p = products.loc[pos.sku]
        batches = data["Batches"].loc[(data["Batches"].sku==pos.sku)&(data["Batches"].location==pos.location)]
        lots = [[(b.expiry_date-as_of).days,float(b.quantity_l)] for b in batches.itertuples()]
        obligations = data["Commitments"].loc[(data["Commitments"].sku==pos.sku)&(data["Commitments"].location==pos.location)].groupby("due_date").quantity_l.sum().sort_index()
        customer_life = p.min_customer_life_days+c["expiry_buffer_days"]
        for due,quantity in obligations.items():
            day = (due-as_of).days
            eligible = sum(q for exp,q in lots if exp>=day+customer_life)
            served = _take_fefo(lots,float(quantity),day,customer_life)
            rows.append(dict(sku=pos.sku,location=pos.location,due_date=due.strftime("%Y-%m-%d"),
                             commitment_l=float(quantity),eligible_stock_l=eligible,
                             rcr=eligible/quantity if quantity>0 else np.nan,
                             served_from_current_stock_l=served,gap_l=float(quantity)-served))
    return pd.DataFrame(rows,columns=columns)


def _metrics(data, policy, classification, local_results, batch_risk, dated_coverage, as_of):
    history = data["History"]
    recent = history.loc[history.month > as_of-pd.DateOffset(months=12)]
    cost_map = data["Products"].set_index("sku").unit_cost_inr_l
    recent = recent.assign(closing_value=recent.closing_stock_l*recent.sku.map(cost_map),
                           cost_shipped=recent.shipments_l*recent.sku.map(cost_map))
    avg_value = recent.groupby("month").closing_value.sum().mean()
    periods = recent.month.nunique()
    turns = recent.cost_shipped.sum()/avg_value *12/max(periods,1) if avg_value>0 else np.nan
    demand = recent.orders_l.sum()
    wape = 100*(recent.orders_l-recent.forecast_l).abs().sum()/demand if demand else np.nan
    observed_rows = [
        ["All","Observed quantity fill",100*recent.shipments_l.sum()/demand if demand else np.nan,"%","Total shipments / captured orders over trailing available 12 completed months"],
        ["All","Observed annualised inventory turns",turns,"x/year","Annualised shipped cost / mean monthly closing book inventory; month-end proxy"],
        ["All","Observed inventory days",365/turns if turns>0 else np.nan,"days","365 / annualised inventory turns; not lifecycle appropriateness"],
        ["All","Observed forecast WAPE",wape,"%","Sum absolute monthly forecast errors / total captured orders"],
        ["All","Observed forecast bias",100*(recent.forecast_l-recent.orders_l).sum()/demand if demand else np.nan,"%","Positive means overforecast; aggregate signed error / orders"],
        ["All","Current stock book value",float((policy.stock_l*policy.unit_cost_inr_l).sum()),"INR","Snapshot quantity × unit cost; principal is not recurring cost"]]
    metric_rows = []
    for stage in STAGES:
        sub = policy.loc[policy.stage==stage]
        if sub.empty:
            continue
        sims = local_results.loc[(local_results.stage==stage)&(local_results.scenario=="Proposed")]
        fill = 100*sims.served_l.sum()/sims.demand_l.sum() if sims.demand_l.sum()>0 else np.nan
        metric_rows += [[stage,"Current stock book value",float((sub.stock_l*sub.unit_cost_inr_l).sum()),"INR","Snapshot only; not realised savings"],
                        [stage,"Simulated quantity fill",fill,"%","Volume weighted across positions and paired simulation runs"],
                        [stage,"Positions with ERI > 1",int((sub.eri>1).sum()),"positions","Exposure screen; not certainty of expiry"],
                        [stage,"Approved what-if positions",int(sub.approved.sum()),"positions","Human-approved local policy changes only"]]
        skus = set(sub.sku)
        hh = history.loc[history.sku.isin(skus)].copy()
        national = hh.groupby("month").agg(stock=("closing_stock_l","sum"),demand=("orders_l","sum"))
        last3 = hh.loc[hh.month.isin(sorted(hh.month.unique())[-3:])]
        if stage=="Introduction":
            orders = last3.orders_l.sum()
            launch_fill = 100*last3.shipments_l.sum()/orders if orders>0 else np.nan
            metric_rows += [[stage,"Observed launch quantity fill",launch_fill,"%","Introduction-stage current cohort; latest 3 available completed months, shipments / orders"],
                            [stage,"Frozen launch-plan exposure",np.nan,"Not available","Requires a dated frozen launch plan and original launch-stock commitment; current forecast is not an approved baseline"],
                            [stage,"Launch forecast bias",100*(last3.forecast_l-last3.orders_l).sum()/orders if orders>0 else np.nan,"%","Latest available 3 months; current monthly forecast error, not frozen launch-plan bias"]]
        if stage=="Growth":
            repeat = last3.assign(positive=last3.orders_l>0,service_ok=last3.availability_pct>=90).groupby(["sku","location"]).agg(months=("month","nunique"),positive=("positive","sum"),observable=("service_ok","sum"),orders=("orders_l","sum"),shipments=("shipments_l","sum"))
            floors = sub.set_index(["sku","location"]).service_floor_pct
            qualified = sum(r.months>=2 and r.positive>=2 and r.observable>=2 and (100*r.shipments/r.orders if r.orders>0 else 0)>=floors.loc[key] for key,r in repeat.iterrows())
            metric_rows += [[stage,"Repeat serviced depot reach proxy",100*qualified/max(len(sub),1),"% of SKU-depot positions","Positive orders in at least 2 of latest 3 months, at least 2 months availability>=90%, and aggregate fill>=local floor. Depot proxy; not dealer-level commercial qualification."],
                            [stage,"Added-node inventory attribution",np.nan,"Not available","Requires approved node-expansion dates and a frozen before/after cohort; no attribution inferred from current stock alone"]]
        if stage=="Maturity":
            stage_recent = recent.loc[recent.sku.isin(skus)]
            value = stage_recent.groupby("month").closing_value.sum().mean()
            count = stage_recent.month.nunique()
            stage_turns = stage_recent.cost_shipped.sum()/value*12/max(count,1) if value>0 else np.nan
            metric_rows += [[stage,"Observed annualised turns",stage_turns,"x/year","Trailing available 12 completed months shipped litres × current unit cost / mean month-end inventory at same cost; accounting COGS ledger not supplied"],
                            [stage,"Observed days on hand",365/stage_turns if stage_turns>0 else np.nan,"days","365 / stage annualised turns; matched cost and observation horizon"]]
        if stage=="Decline" and len(national)>=6:
            early,late = national.iloc[-6:-3].mean(),national.iloc[-3:].mean()
            demand_decline = 1-late.demand/early.demand if early.demand>0 else 0
            stock_decline = 1-late.stock/early.stock if early.stock>0 else 0
            metric_rows.append([stage,"Inventory Decline Ratio",stock_decline/demand_decline if demand_decline>0 else np.nan,"ratio","% inventory decline / % captured demand decline: latest vs prior 3 months; undefined without demand decline"])
            metric_rows.append([stage,"FEFO exposed book value",float(batch_risk.loc[batch_risk.sku.isin(skus),"at_risk_value_inr"].sum()),"INR","Deterministic dated batch-consumption screen; not expected write-off or realised savings"])
        if stage=="Exit":
            ratios = dated_coverage.rcr.dropna()
            metric_rows += [[stage,"Minimum dated Residual Coverage Ratio",float(ratios.min()) if len(ratios) else np.nan,"ratio","Lowest per-SKU/location/due-date current eligible stock / committed quantity after earlier obligations consume stock FEFO. No pooling; undefined without dated obligations."],
                            [stage,"Dated obligation tranches with RCR < 1",int((dated_coverage.rcr<1).sum()),"tranches","Current-stock gaps by due date; inspect exit_coverage evidence. Planned replenishment is excluded from this snapshot diagnostic."],
                            [stage,"Current-stock dated commitment gaps",float(dated_coverage.gap_l.sum()),"L","Sum due-date gaps after FEFO allocation; same inventory cannot cover multiple commitments twice"]]
    cols = ["stage","metric","value","unit","definition"]
    return pd.DataFrame(observed_rows,columns=cols),pd.DataFrame(metric_rows,columns=cols)


def analyze(data, controls=None, overrides=None):
    data = validate_data(data)
    c = _controls(controls)
    overrides = _override_map(overrides,set(data["Products"].sku))
    as_of = pd.Timestamp(_settings(data)["as_of_date"]).normalize()
    classification = _classify(data,c,overrides)
    policy = _policies(data,c,classification,overrides,as_of)
    batch_risk = _batch_screen(data,c,policy,as_of)
    transfers = _transfer_screen(data,c,policy,batch_risk,as_of)
    summary,paths,runs,local = _simulate(data,c,policy,as_of)
    dated_coverage = _dated_coverage(data,policy,c,as_of)
    observed,stage_metrics = _metrics(data,policy,classification,local,batch_risk,dated_coverage,as_of)
    means = summary.set_index("metric")
    base_cost = runs.loc[runs.scenario=="Baseline","total_cost_inr"].to_numpy()
    prop_cost = runs.loc[runs.scenario=="Proposed","total_cost_inr"].to_numpy()
    benefit = base_cost-prop_cost
    local_means = local.groupby(["sku","location","scenario"],as_index=False).agg(demand_l=("demand_l","sum"),served_l=("served_l","sum"),service_floor_pct=("service_floor_pct","first"))
    local_means["fill_pct"] = np.where(local_means.demand_l>0,100*local_means.served_l/local_means.demand_l,100)
    breaches = local_means.loc[(local_means.scenario=="Proposed")&(local_means.fill_pct+1e-6<local_means.service_floor_pct)]
    warnings = []
    if len(breaches):
        warnings.append(f"{len(breaches)} proposed-scenario SKU/locations miss their volume-fill floor. Do not scale those policies; inspect Service evidence.")
    if not policy.approved.any():
        warnings.append("No policy changes are approved: baseline and proposed paths are identical by construction.")
    if c["transfer_approval"]:
        warnings.append("Transfer approval is acknowledged only as a review intent. Transfers remain screened recommendations and are excluded from simulation and benefit totals.")
    if classification.confidence.isin(["Suspended","Insufficient","Low"]).any():
        warnings.append("Some classifications have limited/suspended evidence; prior stages are retained unless explicitly overridden, and supply-constrained policy changes remain blocked.")
    # Snapshot inconsistencies are surfaced rather than inventing reconciliation transactions.
    current_batches = data["Batches"].groupby(["sku","location"]).quantity_l.sum()
    latest = data["History"].sort_values("month").groupby(["sku","location"]).tail(1)
    if as_of.is_month_end:
        mismatch = sum(abs(float(current_batches.get((r.sku,r.location),0))-r.closing_stock_l)>1e-6 for r in latest.itertuples() if r.month==as_of)
        if mismatch:
            warnings.append(f"{mismatch} latest closing-stock rows do not reconcile to current batches. Simulation uses Batches; resolve before live use.")
    if c["horizon_weeks"]*7 < data["Products"].shelf_life_days.max():
        warnings.append("Simulation horizon is shorter than at least one SKU shelf life. Ending inventory/exposure is not a realised saving; expiry validation requires the full usable-life horizon.")
    origin = str(_settings(data).get("data_origin","Unspecified; verify provenance"))
    assumptions = [
        "Source status: "+origin+". Synthetic/demo results are not Asian Paints facts or measured savings.",
        "Five lifecycle stages are demand-evidence outputs; commercial status remains an independent human field. Thresholds and persistence are configurable team design assumptions.",
        "Demand signal is captured orders. Missing calendar months are never zero-filled; supply-observability failures suspend automatic policy changes.",
        "Trend uses recent 3 months against the same 3 months a year ago with at least 15 observations; otherwise adjacent 3-month windows and reduced confidence. Broader seasonal/multipeak archetypes remain hypotheses.",
        "Periodic order-up-to policies are evaluated weekly; review and stochastic lead times round up to whole weeks, minimum lead one week. Opening pipeline/backlogs are assumed zero because not supplied.",
        "Design cycle service percentile is only an approximate normal safety-stock input. It is not quantity fill. Actual simulated volume fill is checked separately against each local service floor.",
        "Monthly forecast-error SD is converted to a daily independent-increment proxy; stochastic demand is a pack-rounded lognormal scenario with historical CV. No fitted forecast accuracy or empirical probability claim is made.",
        "Residual demand rate is (next-month forecast minus included commitments)/30.4375 and persists over the horizon with the chosen shock. Every dated commitment is added once and given service priority. No automatic trend extrapolation into demand scenarios.",
        "Each baseline/proposed pair uses identical sampled demand and lead-time drivers. No human approval means identical policies and outcomes; causal attribution still requires a controlled live comparator.",
        "FEFO eligibility includes customer minimum remaining life plus the chosen buffer. Quarantined stock remains book inventory until physical expiry; residual demand is lost, not backordered. No substitution across SKUs.",
        "Replenishment is pack/MOQ constrained; warehouse capacity includes on-hand plus ordered pipeline. Incoming product life and ownership begin at order placement, explicit proxies in the absence of manufacturing/contract data. No production capacity or shared supplier allocation model.",
        "Cost is holding on on-hand plus on-order owned value, actual expiry write-off, and assumed lost-margin penalty. Inventory principal, unspent procurement and book-value reduction are never added as recurring savings. On-hand, pipeline and total-owned values are separately reported; no cash release is inferred. Freight is excluded because transfers are not simulated.",
        "P10/P90 are scenario percentiles across simulations, not confidence intervals. Sample averages are decision-support hypotheses, and a favourable mean cannot override a local service-floor failure.",
        "ERI uses weighted customer-usable life and residual demand plus dated obligations. Batch FEFO exposure is the stronger expiry screen; neither is certainty of write-off. Only ERI>1 is treated as a structural escalation signal.",
        "Transfers are conservative same-SKU FEFO candidates screened against source commitments/buffer, destination demand, remaining life, pack size and lane capacity; excluded from all simulated benefits. Network pooling percentages are not asserted.",
    ]
    kpis = dict(sku_count=len(classification),location_count=data["Positions"].location.nunique(),
                stock_value_inr=float((policy.stock_l*policy.unit_cost_inr_l).sum()),
                at_risk_value_inr=float(batch_risk.at_risk_value_inr.sum()),
                approved_positions=int(policy.approved.sum()),
                baseline_fill_pct=float(means.loc["fill_pct","baseline_mean"]),
                proposed_fill_pct=float(means.loc["fill_pct","proposed_mean"]),
                simulated_net_benefit_inr=float(benefit.mean()),benefit_p10_inr=float(np.quantile(benefit,.1)),
                benefit_p90_inr=float(np.quantile(benefit,.9)),service_floor_breaches=len(breaches),
                expiry_avoided_l=float(means.loc["expiry_l","improvement_mean"]))
    return dict(classification=classification,policy=policy,batch_risk=batch_risk,transfers=transfers,
                observed=observed,simulation_summary=summary,simulation_paths=paths,stage_metrics=stage_metrics,
                run_results=runs,service_evidence=local_means,service_breaches=breaches,exit_coverage=dated_coverage,
                kpis=kpis,assumptions=assumptions,warnings=warnings,controls=c,as_of=as_of.strftime("%Y-%m-%d"))
