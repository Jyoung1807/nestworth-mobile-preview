# Nestworth — fictional mobile preview

**Demo only. No sign-in, Supabase connection, bank connection or real household records.**

A Streamlit preview of Nestworth — *Your household. Your future.* All financial figures, people, transactions and schedules in the populated household are fictional. Data stays in each browser's server session and is not persisted across sessions or devices.

## Run locally

Use Python 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run preview_app.py
```

## Explore the demo

The app opens a complete, approved fictional household using its financial calculation services. Scenario date: **19 November 2026**.

- **Load Demo Household** opens/resumes the populated fictional household.
- **Reset Demo Household** asks for confirmation, then restores the same deterministic demo state.
- **Start Fresh Setup** creates a separate empty fictional household without deleting the populated demo.
- **DEMO MODE** identifies the fictional session. “Return to default demo” returns only to the preview's fictional base; there are no real households in this application.

Groceries has a $900 weekly allocation and $935 recorded spending, producing a $35 category overspend. Scheduled payments in the scenario's next seven days total $3,560. Compare Budget/Forecast, tap a category, inspect cash views and test the existing recovery workflow.

This is an **early development checkpoint**, not a complete financial product. Custom budget periods, incoming-money modelling, revised contingency, total-savings accounts and broader refinements are not implemented in this exported version. Its reserve still uses the existing positive-monthly-surplus policy. Values are household projections, not verified bank or savings balances.

Do not enter real financial information, upload real statements, enter credentials or add production secrets. Optional CSV testing is for fictional/anonymised examples only. No durable storage, bank feeds or real account creation is provided.

## Deploy as a separate Streamlit Community Cloud app

Use a dedicated repository for this preview. Create a NEW app with `preview_app.py` as the main file, Python 3.12 and **no Secrets**. Keep any existing live application unchanged. Dependencies are limited to Streamlit, pandas and Altair.

## Source layout

`preview_app.py` is the only entry point. `populated_demo.py` builds the fictional household; `test_households.py` controls isolated sessions. Other Python modules are the UI and financial domain dependencies needed by those demo flows. `navigation_layout.js` is a local presentation component. `.streamlit/config.toml` contains visual theme settings only.

There are no production authentication modules, database migrations, private repository history, external API credentials, production URLs or customer data in this package.
