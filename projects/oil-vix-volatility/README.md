# Oil Market Volatility → U.S. Financial Market Volatility

**Financial Econometrics — semester project (group 3)**

Does oil-market volatility (CBOE OVX) predict U.S. equity-market volatility
(VIX) through instantaneous comovement?

## Contents
- [`Financial_Econ_groupe_3.pdf`](./Financial_Econ_groupe_3.pdf) — the written paper
- [`oil_vix_volatility.py`](./oil_vix_volatility.py) — the analysis code

## Method
Daily FRED data from 2010 onward. The script builds a ~30-series panel
(oil, volatility, credit spreads, term structure, macro controls, FX,
liquidity, uncertainty), then runs:

1. Simple OLS (OVX → VIX)
2. OLS with macro controls
3. HAC (Newey-West) standard errors for heteroskedasticity + autocorrelation
4. Control selection via a correlation matrix (drop collinear regressors)
5. Interaction terms (OVX × stress / dollar / 3M yield / uncertainty)
6. A quadratic term test
7. A PE test selecting a log-linear specification

Main finding: a 1% rise in oil-price volatility is associated with a
~0.69% rise in market volatility (log-linear, HAC-robust).

## Run it
```bash
pip install fredapi pandas statsmodels matplotlib seaborn numpy
export FRED_API_KEY=your_free_key   # https://fred.stlouisfed.org/docs/api/api_key.html
python oil_vix_volatility.py
```

> The FRED API key is read from the `FRED_API_KEY` environment variable — no secrets in the code.
