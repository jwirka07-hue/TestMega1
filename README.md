# Southeast Property Value Estimator

Four tabs (Home, Apartments, Industrial, Office). Owner uploads a rent roll and answers a few
questions -> estimated value range. 13 Southeast markets.

## Files
- app.py           the website (Streamlit) — all three tabs
- home.py          single-family homes: comparable-sales adjustment grid
- engine.py        all valuation math (direct cap with tax reset, NNN vs gross)
- rentroll.py      reads apartment and commercial tenant rent rolls (CSV/Excel)
- market_data.py   cap rates, tax rates, standard assumptions, with sources (update quarterly)
- test_engine.py   math checks — run: python -m pytest -q
- sample_*.csv     test rent rolls for each tab

## Add a market
Copy any block in MARKETS in market_data.py, change the name and numbers, keep a source.

## Run locally
    pip install -r requirements.txt
    streamlit run app.py

## Deploy
Upload all files to your GitHub repo (replace the old ones). Streamlit redeploys automatically.
