# Chain Reaction — Streamlit MVP

A compact, local-Python decision dashboard for the E100 / IIM Mumbai lifecycle inventory solution. Upload one Excel workbook, review human inputs, simulate current versus proposed policy and download the dashboard and supporting evidence.

## Run locally

Use Python 3.12. Extract the ZIP and open a terminal in its folder:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
# source .venv/bin/activate
pip install -r requirements.txt
streamlit run streamlit_app.py
```

No API key, database, paid service or GPU is required. The only network dependency is installing packages and serving the app; uploaded records are processed by the Python host. Downloaded HTML reports embed their chart library and work offline.

## Deploy to Streamlit Community Cloud

1. Put the extracted files in a GitHub repository. Include `.streamlit/config.toml` and the synthetic sample workbook; exclude any private operational input file.
2. Open https://share.streamlit.io/ and choose **Create app**.
3. Select your repository/branch and set the main file to `streamlit_app.py`.
4. Select Python **3.12** in the advanced settings, then deploy. `requirements.txt` installs the dependencies.

Official deployment instructions: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app

This is a Streamlit server app. Cloudflare Pages cannot serve these Python callbacks as a static site; use the Streamlit deployment for this MVP. No hosting account has been created or deployment performed on your behalf.

## A three-minute demonstration

1. Leave the supplied synthetic example loaded, or upload `Chain_Reaction_Input.xlsx`.
2. Select **Decline / exit proposals** in the sidebar. This is a group what-if approval using prior lifecycle stages; the reason is recorded. For individual decisions, expand **Human inputs**, edit the rows, and choose **My SKU decisions**.
3. Click **Simulate**. The default is 20 paired scenarios over 26 weeks; choose 5 runs for a faster demonstration. View Overview, D1, D2 and D3.
4. Download **dashboard HTML** and **evidence ZIP**. Open the HTML without a server; its Print / save PDF button produces a printable copy.

**Current policy only** is an intentional control: it must show zero incremental policy benefit. Changes to inputs mark the previous result stale and disable downloads until you simulate again. Each browser session has separate input/result state; refreshing or ending the host session can lose unsaved decisions. Export evidence before leaving.

## What is covered

- **D1:** five lifecycle stages, candidate versus effective stage, supply observability, persistence/confidence, archetype context, commercial status and reasons for overrides; SKU demand-history drilldown.
- **D2:** suggested/current/approved inventory targets, review interval, safety/cycle-stock assumptions, expiry and assigned capacity constraints, pack/MOQ checks, dated commitments, local policy register, batch exposure, conservative network transfer candidates and dated Exit coverage.
- **D3:** observed quantity fill and inventory metrics, stage scorecard, matched baseline/proposed demand scenarios, holding/expiry/shortage cost bridge, local service floors, commitment service and scenario ranges.

The model consumes supplied forecasts and a current periodic inventory-position target. It is not a reproduction of the company's optimiser, a calibrated forecasting model or an empirical proof of savings. A positive average benefit can coexist with poor local service, which the dashboard flags.

## Input and provenance

One workbook contains a Guide and seven data tabs: Products, History, Positions, Batches, Commitments, Lanes and Settings. This keeps master data, monthly observations and dated obligations separate without uploading multiple files. Exact headers and units are documented in `DATA_DICTIONARY.md` and the app.

The sample has 36 generic liquid-coatings SKUs, four fictional Indian depots, 3,612 monthly rows, 144 stock positions, 432 batches and 262 commitments. **All operational data and costs are synthetic.** Industry sources support familiar product families and pack sizes; they do not supply the sample transactions. Demo full shelf lives of 180–365 days are short-life stress assumptions, not Asian Paints specifications. Original public product sheets can have materially longer lives. See `SOURCES.md` for the bounded original-data search and source boundaries.

## MVP boundaries

- Weekly FEFO simulation with captured orders as demand proxy; residual unserved demand is lost rather than backordered.
- No opening purchase-order pipeline, production scheduling, cross-SKU capacity allocation, automatic substitution, pricing or competitor response.
- New stock life and pipeline ownership use explicit order-placement assumptions. Owned stock includes on-hand plus modeled pipeline; inventory principal is not added to recurring cost benefits.
- Network moves are screened recommendations. They are not simulated, economically approved or credited as savings.
- P10/P90 are scenario percentiles, not confidence intervals. Missing launch/cohort ledgers produce an unavailable metric instead of an invented result.
- Approvals affect only this simulation. No ERP write, purchase order, transfer or liquidation is executed.
- Public deployment is intended for synthetic demonstrations. Configure access appropriately before uploading confidential company records; exports include those inputs and approvals.

## Files

- `streamlit_app.py`: entry point and interface.
- `engine.py`: input validation, lifecycle/policy logic and paired simulator.
- `views.py`: charts and offline exports.
- `make_demo.py`: reproducible synthetic data generator.
- `Chain_Reaction_Input.xlsx`: input example/template.
- `requirements.txt` and `.streamlit/config.toml`: deployment settings.
- `SOURCES.md` and `DATA_DICTIONARY.md`: provenance and schema.
- `test_engine.py`, `test_review.py`, `test_streamlit.py`: repeatable checks.

Run checks from the extracted folder:

```bash
python -m unittest test_engine test_review test_streamlit -v
```
