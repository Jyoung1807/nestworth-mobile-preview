# Nestworth 4.8 — fictional UAT preview

**DEMO MODE · fictional households only · no sign-in, Supabase, bank connection or durable storage.**

Nestworth — *Your household. Your future.* This preview is prepared from private checkpoint `8e479d4` for owner-led mobile and desktop acceptance. Automated checks support acceptance; they do not constitute product acceptance. No 5.0 or bank-import expansion is included.

## Stage 1: populated household

The app opens Nora and Sam's complete fictional household, with a fixed **19 November 2026** scenario date. Its new fictional approval uses 1 November 2026–31 October 2027, date-based allowances, the 10% normal-spending contingency method, **$12,000 identified opening savings within $18,000 opening cash**, and a $40,000 total-savings target. These are explicit dummy inputs, not inferred account balances or changes to any private approved budget.

Groceries: **$900 weekly allowance, $935 recorded, $35 over**. Review the prominent alert, select the spending bar and use the real review/recovery services. Try partial/full funding, the current/revised source amounts, acceptance, reversal and verification. Future commitments are not realised savings. Payments in the fictional 19–25 November window total **$3,560**.

Completed features included: proactive category alerts/shared action counts, interactive category drilldowns, transaction review, recovery and funding previews, budget/forecast comparisons, period-aware savings/targets, upcoming payments, safe payment rescheduling, and percentage or fixed scheduled contingency. Explore Home's Overview, Spending Analysis, Cash Flow, Cash Position and Upcoming Payments; Transactions; Adjust Forecast; To Do; and Settings. Monetary projections are not verified bank balances.

- **Load Demo Household** resumes this populated fictional household.
- **Reset Demo Household** requires confirmation and restores its deterministic starting state.
- **Start Fresh Setup** creates an independent, empty household.
- **Return to default demo** never opens a real household.

For forecast contingency, use **Adjust Forecast → Change contingency**. New settings are prospective from the next calendar month, protecting approved snapshots and earned reserve. Fixed weekly/fortnightly/monthly/annual amounts count their actual contribution dates. Targets are distinct from funded availability; earmarks add no expense or cash outflow.

## Stage 2: fresh household

Use Start Fresh Setup. It starts with no income, expenses, plans, observations, completed stages or approvals. Suggested expenses remain unreviewed. Follow the genuine workflow: household/dates → income → fixed spending → variable spending → plans → historical review or explicit skip → review/approve → Home. Test 3/6/12-month or custom dates, income entry, Back/Edit/Resume, opening savings/cash and targets. Then amend the forecast and check Home. The populated household is preserved independently. Resetting the active test household also requires confirmation.

## Stage 3: owner refinement

Review every major screen and workflow on a real phone and desktop. Record feedback in batches: screen, steps, expected/actual behaviour, device/width and screenshot if useful. Findings are 4.8 refinement work until the owner explicitly accepts 4.8. No automatic-test count implies commercial or usability acceptance.

## Scope and safe use

**Do not enter real financial data, upload real statements, enter credentials or configure production secrets.** CSV historical-review controls are for fictional examples only. Incoming-money/refund/transfer reconciliation, additional seasonal/provision refinements, durable persistence, real account management and bank connections are not completed by this preview. Login/authentication is deliberately excluded and cannot be accepted through this public demo. Session data can disappear on refresh, restart or disconnect and is not synchronised between devices.

There are no production authentication modules, database migrations, credentials, production endpoints or private Git history in this repository. The only identity is a local fictional session namespace. Reset cannot access a production household.

## Run locally

Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run preview_app.py
```

## Existing Streamlit Community Cloud app

Retain the existing app and URL. Repository `Jyoung1807/nestworth-mobile-preview`, branch `main`, entry point **`preview_app.py`**, Python **3.12**, requirements **`requirements.txt`**, **no Secrets**. An approved update to this repository's `main` will rebuild the existing preview; do not create or repoint the private production app. This prepared bundle must be reviewed and explicitly approved before any public push.

Source modules are only this fictional entry point's dependency closure. Dependencies: Streamlit, pandas and Altair at the pinned versions in requirements.txt. Theme configuration disables usage telemetry. No real financial data should be entered even though editable forms are available for fictional testing.
