# Data provenance and source boundaries

Checked 6 September 2026. The supplied input workbook is **entirely synthetic**. It contains no Asian Paints operational records and no financial result should be attributed to Asian Paints. Synthetic records are generated reproducibly by `make_demo.py`, default seed 2608, with a snapshot dated 31 August 2026.

## Original-data search result

The search covered official Asian Paints investor/product resources, publicly indexed paint-demand research, Kaggle and Mendeley. I did not locate a publicly accessible, verifiably original Indian paint dataset with the combined SKU-by-depot order/forecast history, dated batch inventory, commitments, lead times, capacity and lane economics required by this model. This is a bounded search finding, not a claim that no such dataset exists.

Public reports and product sheets are original company sources, but they cannot supply missing transactional observations. Generic retail datasets should not be relabelled as paint data. Real operational use requires an authorised ERP/WMS/demand-planning extract with the workbook schema. A real sales-only file would still require explicit assumptions for inventory, availability, batches, forecasts and supply constraints; it would not make the complete model an empirical validation.

## Verified primary industry sources

1. **Asian Paints, Apcolite Premium Emulsion product information sheet**, page 1. [Official PDF](https://www.asianpaints.com/content/dam/asian_paints/restricted/apcolite-premium-emulsion.pdf). The sheet lists 1, 4, 10 and 20 litre packs and a three-year unopened shelf life under specified storage conditions. Used only to ground familiar liquid-coatings pack sizes and the distinction between product full shelf life and batch remaining life. The downloaded endpoint contains an older version label; it is not a source for current prices or every product's specifications. No synthetic demand, unit cost, margin or policy parameter is taken from this sheet.

2. **Asian Paints, SmartCare Damp Proof product information**. [Official product page](https://www.asianpaints.com/waterproofing-products/smartcare-damp-proof.html). Identifies the product as a liquid waterproofing membrane and specifies a 36-month shelf life with appropriate storage. Used to support inclusion of liquid waterproofing as a coatings family. It does not support the demo's 270-day shelf-life assumption or any sales pattern.

3. **Asian Paints, Integrated Annual Report 2025–26**. [Official report portal](https://www.asianpaints.com/content/annualreport/annual-report-25-26.html). Provides company-level business/product and financial context, with links to original statements. The exposed report material is aggregate; it does not supply the SKU-depot batch and demand records required here. No report aggregate has been disaggregated into fabricated company transactions.

4. **Asian Paints, Integrated Annual Report 2024–25**. [Official report portal](https://www.asianpaints.com/content/annualreport/annual-report-24-25.html). Its product-family descriptions support the industry's interior/exterior finishes, waterproofing, enamels and undercoat context. Again, this is contextual evidence, not input transaction data.

These are publicly readable copyrighted materials. The dashboard links to the sources; it does not claim an open-data licence for Asian Paints' underlying business data or reproduce the reports as a dataset.

## Public candidates considered and excluded

- **Dataset and Code for SKU-Level Demand Forecasting Using ML–PPCP Framework**, Mendeley Data, version 1, 30 January 2026, DOI 10.17632/t4kbxgm7my.1. [Dataset publisher page](https://data.mendeley.com/datasets/t4kbxgm7my/1). The publisher explicitly describes the released data as synthetic because real industrial data are confidential. It lists CC BY 4.0. It was not substituted for an original paint data file and is not used in the demo.
- **Historical Sales and Active Inventory**, Kaggle. [Uploader's dataset card](https://www.kaggle.com/flenderson/sales-analysis/activity). Product-level six-month sale/activity indicators, with an “Other” licence label. It is not a paint SKU-depot time series with batch expiry. It is not used or redistributed.
- **Inventory Optimization**, Kaggle competition. [Competition data page](https://www.kaggle.com/competitions/inventory-optimization/data). The data description identifies LED televisions and access subject to competition rules. It is unsuitable for a paint-specific model and is not used.

## What is assumed in the synthetic workbook

All product identities/names, local demand levels, lifecycle trajectories, costs, margins, service floors, MOQs, lead times, capacities, order-up-to levels, remaining-life distributions, commercial statuses and commitment quantities are demonstration assumptions. Mumbai, Delhi NCR, Bengaluru and Kolkata are geographic labels for fictional depots; they do not assert Asian Paints facility locations or lane costs.

The 180/270/365-day full shelf-life values deliberately form a short-life stress case consistent with the team's expiry-oriented problem framing. **They are not manufacturer-certified shelf lives and must be replaced for real products.** Public liquid-emulsion/waterproofing examples above have materially longer stated lives. Historical stock balances are synthetic snapshots; only the final month is reconciled to the supplied batch register. No historical receipt/write-off ledger is supplied.

Seasonality is a small, repeatable sinusoid used to test separation of seasonal movement from lifecycle movement. It is not a fitted estimate of Indian monsoon/festival demand. The cohort mix deliberately exercises all five stages, plus insufficient-history, supply-censoring, recovery and stable-niche review cases; it is not an estimated market mix. Historical forecasts use lagged generated order observations and are not in-sample fitted predictions. A prior lifecycle stage is a human starting input and never a hidden ground-truth evaluation label.

The output is a controlled demonstration of the submitted decision framework. Simulation differences are conditional scenario results, not forecasted company savings, validated causal effects or evidence of model accuracy on real operational data.
