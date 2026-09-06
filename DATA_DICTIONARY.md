# Input workbook dictionary

Upload one `.xlsx` workbook containing the seven named data sheets below. Keep exact sheet/column names and put headers on row 1. A separate Guide sheet is explanatory and is not model input. One workbook may contain many worksheets: do not flatten the linked entities into one table.

All demand, inventory, commitments, capacity and policy quantities use **litres**. `pack_l` converts a sealed-pack SKU to litres; each SKU is one exact formulation/shade/pack combination. Do not mix kilograms, number of tins and litres. Unit cost and margin use INR per litre. Percentage fields use 0–100, not fractions. Dates use ISO `YYYY-MM-DD` or ordinary Excel dates; no formulas/macros are required.

## Products — one row per SKU

| Column | Meaning / expected input |
|---|---|
| sku | Unique stable SKU key, used in every other product table. |
| product_name | Readable generic/real product and pack description. |
| family | Product family used for filters and management summaries. |
| pack_l | Litres in a sealed saleable pack; positive. |
| unit_cost_inr_l | Inventory book cost per litre. Use consistent valuation scope. |
| unit_margin_inr_l | Contribution margin per litre; an input to shortage economics, not selling price. |
| shelf_life_days | Full shelf life of a newly manufactured/received batch under the prototype's fresh-receipt assumption. Replace with a conservative actual receipt life where upstream ageing is material. |
| min_customer_life_days | Minimum remaining days a customer accepts when stock is delivered; below product full life. |
| moq_l | Minimum replenishment order in litres; respect pack multiples. |
| lead_time_days | Mean replenishment lead time in days. |
| lead_time_sd_days | Lead-time standard deviation in days; non-negative. |
| prior_stage | Previous approved stage: Introduction, Growth, Maturity, Decline or Exit. It is the initial governance state, not a generated answer key. |
| commercial_status | Active, Phase-out or Discontinued. Commercial decision remains separate from demand evidence. |
| successor_sku | Optional successor product key; blank if none. This is contextual: no automatic product substitution is authorised. |
| data_origin | Provenance, e.g. ERP extract plus extract date, or explicit SYNTHETIC DEMONSTRATION. |

## History — one row per month × SKU × depot

| Column | Meaning / expected input |
|---|---|
| month | Completed month represented by its month-end date, no later than `as_of_date`. |
| sku / location | Product and depot keys. |
| orders_l | Captured customer requested quantity. The demo assumes orders are an uncensored demand proxy; disclose if order capture fails during stock-outs. |
| shipments_l | Quantity fulfilled against the month's orders, no greater than orders in this simplified lost-sales schema. If ERP shipments include old backorders, reconcile them before upload. |
| forecast_l | Forecast frozen before the month began, covering the same demand definition as orders. Required for forecast-error measurement. |
| availability_pct | Share of time the item was available; use an operationally consistent monthly measure, 0–100. |
| closing_stock_l | Physical inventory at month end. At the snapshot date, reconcile this to all Batches rows for the same SKU/depot. |

Do not replace absent months with zero unless zero demand was genuinely observed. Pre-launch periods are omitted rather than filled with invented zero sales. The demo includes 3–8 months for new products and 30 months for established ones. Historical closing stocks do not replace a receipt/write-off transaction ledger.

## Positions — one row per SKU × depot, at the snapshot date

| Column | Meaning / expected input |
|---|---|
| sku / location | Product and depot keys, unique jointly. |
| current_order_up_to_l | Current approved inventory-position target: the explicit baseline policy. It is not current on-hand stock. |
| current_review_days | Current periodic review interval in days. |
| service_floor_pct | Minimum desired quantity-fill service for review/scenario evaluation. A cycle-service quantile is not automatically an achieved fill rate. |
| capacity_l | Assigned storage capacity for this SKU/depot. The prototype cannot infer shared building capacity across rows. |
| forecast_next_month_l | Total demand forecast for the next 30-day window, including the commitments counted below. |
| commitments_included_l | Amount of dated next-30-day commitments already included in that forecast; must not exceed forecast. Prevents double counting. |
| data_origin | Provenance of snapshot/policy inputs. |

Starting on-hand inventory comes from Batches. The input does not include open inbound purchase orders; reconcile/exclude them deliberately before operational use or extend the schema and simulation. A lower order-up-to target releases cash only through fewer future purchases and actual consumption; it is not a cash receipt on the simulation date.

## Batches — one row per physical batch holding at a depot

| Column | Meaning / expected input |
|---|---|
| batch_id | Unique holding identifier. Use distinct IDs if one manufacturer batch is held at several depots. |
| sku / location | Exact product/depot identity. |
| quantity_l | Physical on-hand quantity; non-negative and in sealed-pack multiples. |
| expiry_date | Actual labelled expiry date. Remaining life is calculated from this date, not assumed equal to full shelf life. |

Stock that fails customer minimum life can still have a later physical expiry. Keep that distinction visible; it cannot be counted as normally saleable simply because it has not chemically expired. All demo batches physically expire after the snapshot, including several that have already crossed the assumed customer-life boundary.

## Commitments — one row per dated outstanding obligation

| Column | Meaning / expected input |
|---|---|
| commitment_id | Unique obligation identifier. |
| sku / location | Required product and fulfilment depot. |
| due_date | Customer due date after the snapshot. |
| quantity_l | Remaining quantity to fulfil in litres. |

Use remaining outstanding quantities only, not full original order quantities. Next-30-day amounts must reconcile to `commitments_included_l` when fully forecast-embedded, as in the demo. Later commitments are separate dated obligations. Exit status does not cancel a commitment.

## Lanes — one row per directed depot transfer route

| Column | Meaning / expected input |
|---|---|
| source / destination | Depot keys; opposite directions are separate rows. |
| transit_days | Travel/handling lead time in days. |
| cost_inr_l | Incremental all-in transfer cost per litre; the demo assumes linear cost, no fixed-trip charge. |
| capacity_l | Maximum permitted litres over the planning/transfer allocation represented by one recommendation run. |
| enabled | TRUE/FALSE authorisation to consider this lane. |

Lane permissions alone do not approve a move. Compatibility, customer life at receipt, destination demand, obligations and capacity must also pass. The prototype recommends transfers; whether they are simulated is explicitly disclosed in the app.

## Settings — one row per parameter

| parameter | value |
|---|---|
| as_of_date | Snapshot date; demo `2026-08-31`. |
| data_origin | Overall provenance. Demo explicitly says synthetic and not Asian Paints operational data. |
| seed | Reproducible data-generation seed; demo 2608. |

The `explanation` column contains human-readable definitions. Model choices and scenario shocks are editable in the dashboard; they are not silently inferred from the data. A stage override and any policy approval are separate human actions with an audit reason.

## Built-in synthetic data checks

`validate_demo()` verifies unique keys, 36 products/144 positions, non-negative demand, shipments no greater than orders, availability bounds, completed history dates, customer-life below full shelf-life, future commitments and physical expiry, final stock-to-batch reconciliation, physical stock within capacity, forecast commitment inclusion and sealed-pack multiples. Passing these checks demonstrates internal consistency, not industry representativeness or economic validity.
