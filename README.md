# Nestworth — fictional owner UAT preview

Your household. Your future.

This is a separate, fictional-only Nestworth 4.8 UAT Round 1 candidate. It is not
production and is not a bank, accounting record or financial advice service.
No real household data, credentials, Supabase SDK, production authentication or
private Git history is included. All changes are in the current browser session;
reloading/reconnecting can lose them. Do not enter real personal or financial data.

## Run locally

Use Python 3.12, install `requirements.txt`, then run:

```
python -m streamlit run preview_app.py
```

The populated Nora & Sam household loads automatically. The fictional review date
is 19 November 2026, including $935 Groceries against a $900 weekly allowance.
Opening savings is explicitly $12,000 within $18,000 opening cash. All figures are
fictional. Financial confirmations use the same budget, forecast, observation,
recovery and reserve services as the application; there is no separate fake engine.

## Test safely

The sidebar's **Demo / Testing Controls** provides:

- **Load Demo Household**: return to the populated fictional household.
- **Reset Demo Household**: confirm discarding that fixture's session changes.
- **Start Fresh Setup**: create an independent empty fictional household and use
  the genuine guided setup and approval workflow.
- **Reset test household only**: confirmation-protected reset of the active fresh
  test household. It cannot reset another namespace or the populated fixture.
- **Return to default demo**: leave the separate test household.

Use Settings → Fictional simulator & calendar settings to create observations.
Overview, Spending, Upcoming Payments and More provide the primary navigation.
All secondary financial workflows remain accessible in More and the sidebar.

## Separate Streamlit Community Cloud deployment

Only after the owner approves this candidate, update this public repository.
Existing separate preview settings:

- Repository: `Jyoung1807/nestworth-mobile-preview`
- Branch: `main`
- Main file: `preview_app.py`
- Python: `3.12`
- Secrets: **none**. Do not copy any production secrets/configuration.
- Preview URL: `https://nestworth-mobile-preview.streamlit.app/`

This repository must never be deployed over the existing private/live app.

## UAT limitations

This is an owner-UAT build, not product acceptance. Session-only persistence does
not test production accounts, invitations, cross-device persistence or bank imports.
Actual bank balances are not inferred from projections. Unavailable coverage stays
unknown. Forecast commitments are not realised savings. Desktop/phone viewport
checks do not substitute for owner testing on physical devices or hosted latency.
Some local warmed navigation timings remain above the 500 ms product target.
