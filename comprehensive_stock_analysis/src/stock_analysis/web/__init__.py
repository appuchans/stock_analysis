"""Local single-user web UI for the stock analysis app.

A FastAPI backend (`app.py`) wraps the blocking `StockAnalysisApp.analyze_stock`
in a single-worker job queue (`jobs.py`) so runs are serialized — required
because `token_meter`/`llm_budget` use process-global state. The frontend is a
no-build SPA served from `static/` + `templates/`.
"""
