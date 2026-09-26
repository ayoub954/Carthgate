"""AI ECONOMIC OUTLOOK — forecasting with temporal validation.

Series: INS monthly imports / exports of goods (MTND), official, 2021 → latest month.
Candidates: seasonal naive (baseline), ARIMA, SARIMA, Gradient Boosting, XGBoost (lag features).
Validation: rolling-origin backtest (12-month horizons). Selection by MAPE (MAE/RMSE reported).
Uncertainty: 500 simulated paths → annual sums → 10th/90th percentiles (80% interval).
A forecast is NOT a certain future: every output carries lower / upper bounds.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ..models import EconomicIndicator, Forecast

warnings.filterwarnings("ignore")
HORIZON_END = 2035
N_PATHS = 500
RNG = np.random.default_rng(42)


def monthly_series(db: Session, indicator: str) -> pd.Series:
    rows = db.query(EconomicIndicator.period, EconomicIndicator.value).filter(
        EconomicIndicator.indicator == indicator).all()
    s = pd.Series({pd.Timestamp(p + "-01"): v for p, v in rows if v is not None}).sort_index()
    if s.empty:
        return s
    s = s.asfreq("MS")
    return s


# ------------------------------------------------------------------ models
def _lag_frame(y: pd.Series):
    df = pd.DataFrame({"y": y})
    for l in (1, 2, 3, 12):
        df[f"lag{l}"] = df.y.shift(l)
    df["month"] = df.index.month
    df["t"] = np.arange(len(df))
    return df.dropna()


def _fit_tree(kind: str, y_log: pd.Series):
    df = _lag_frame(y_log)
    X, t = df.drop(columns="y"), df.y
    if kind == "xgboost":
        from xgboost import XGBRegressor
        m = XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.9, random_state=42)
    else:
        from sklearn.ensemble import GradientBoostingRegressor
        m = GradientBoostingRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, random_state=42)
    # model the change vs lag12 (seasonal difference) so trees can extrapolate the level
    m.fit(X, t - X["lag12"])
    resid = (t - X["lag12"]) - m.predict(X)
    return m, resid.values


def _tree_paths(kind, y_log: pd.Series, h: int, n_paths: int) -> np.ndarray:
    m, resid = _fit_tree(kind, y_log)
    hist = np.tile(y_log.values, (n_paths, 1))
    start_t = len(y_log) - 12  # t index consistent with _lag_frame after dropna
    idx = y_log.index
    out = np.zeros((n_paths, h))
    for k in range(h):
        cur = hist.shape[1]
        month = (idx[-1] + pd.DateOffset(months=k + 1)).month
        X = pd.DataFrame({"lag1": hist[:, cur - 1], "lag2": hist[:, cur - 2], "lag3": hist[:, cur - 3],
                          "lag12": hist[:, cur - 12], "month": month, "t": start_t + k + 12})
        pred = X["lag12"].values + m.predict(X)
        if n_paths > 1:
            pred = pred + RNG.choice(resid, size=n_paths)
        out[:, k] = pred
        hist = np.column_stack([hist, pred])
    return out


def _sarimax_paths(order, seasonal, y_log: pd.Series, h: int, n_paths: int, trend: str = "n") -> np.ndarray:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    res = SARIMAX(y_log, order=order, seasonal_order=seasonal, trend=trend,
                  enforce_stationarity=False, enforce_invertibility=False).fit(disp=False)
    if n_paths == 1:
        return res.forecast(h).values.reshape(1, -1)
    sims = res.simulate(nsimulations=h, repetitions=n_paths, anchor="end")
    return np.asarray(sims).reshape(h, -1).T


def _snaive_paths(y_log: pd.Series, h: int, n_paths: int) -> np.ndarray:
    """Seasonal random walk with drift: y_t = y_{t-12} + drift + e_t, e_t bootstrapped from history."""
    sd = (y_log - y_log.shift(12)).dropna().values
    drift = float(sd.mean()) if len(sd) else 0.0
    resid = sd - drift if len(sd) else np.zeros(1)
    hist = np.tile(y_log.values, (n_paths, 1))
    out = np.zeros((n_paths, h))
    for k in range(h):
        nxt = hist[:, -12] + drift + (RNG.choice(resid, size=n_paths) if n_paths > 1 else 0.0)
        out[:, k] = nxt
        hist = np.column_stack([hist, nxt])
    return out


MODELS = {
    "Seasonal naive + drift (baseline)": lambda y, h, n: _snaive_paths(y, h, n),
    "ARIMA(1,1,1)": lambda y, h, n: _sarimax_paths((1, 1, 1), (0, 0, 0, 0), y, h, n),
    "SARIMA(1,0,0)(0,1,1,12) + drift": lambda y, h, n: _sarimax_paths((1, 0, 0), (0, 1, 1, 12), y, h, n, trend="c"),
    "Gradient Boosting (lags)": lambda y, h, n: _tree_paths("gbr", y, h, n),
    "XGBoost (lags)": lambda y, h, n: _tree_paths("xgboost", y, h, n),
}


def backtest(y: pd.Series, horizon: int = 12) -> dict:
    """Rolling-origin backtest on the log series; metrics computed on the original scale."""
    y_log = np.log(y)
    origins = [len(y) - 2 * horizon, len(y) - horizon]
    origins = [o for o in origins if o >= 36]
    res = {}
    for name, fn in MODELS.items():
        errs = []
        try:
            for o in origins:
                pred = np.exp(fn(y_log.iloc[:o], horizon, 1)[0])
                actual = y.iloc[o:o + horizon].values
                errs.append((actual, pred[:len(actual)]))
        except Exception as e:
            res[name] = {"error": str(e)[:200]}
            continue
        a = np.concatenate([e[0] for e in errs])
        p = np.concatenate([e[1] for e in errs])
        res[name] = {"MAE": float(np.mean(np.abs(a - p))), "RMSE": float(np.sqrt(np.mean((a - p) ** 2))),
                     "MAPE": float(np.mean(np.abs((a - p) / a)) * 100), "folds": len(errs), "horizon_months": horizon}
    return res


def forecast_indicator(db: Session, indicator: str, label: str, log=print) -> dict:
    y = monthly_series(db, indicator + "_monthly")
    y = y.dropna()
    if len(y) < 48:
        return {"indicator": indicator, "status": "INSUFFICIENT DATA", "points": len(y)}
    # keep only the contiguous tail (no gaps)
    gaps = y.index.to_series().diff().dt.days.gt(31)
    if gaps.any():
        y = y[y.index >= y.index[gaps.values].max()]
    metrics = backtest(y)
    valid = {k: v for k, v in metrics.items() if "MAPE" in v}
    best = min(valid, key=lambda k: valid[k]["MAPE"])
    last = y.index[-1]
    h = (HORIZON_END - last.year) * 12 + (12 - last.month)
    paths = np.exp(MODELS[best](np.log(y), h, N_PATHS))
    if paths.shape[0] == 1:
        paths = paths.repeat(N_PATHS, 0)
    fidx = pd.date_range(last + pd.DateOffset(months=1), periods=h, freq="MS")
    pdf = pd.DataFrame(paths.T, index=fidx)
    # annual aggregation; current year = actual months + simulated remaining months
    actual_cur = y[y.index.year == last.year].sum()
    out = []
    for year, g in pdf.groupby(pdf.index.year):
        tot = g.sum(axis=0).values + (actual_cur if year == last.year else 0)
        out.append({"year": int(year), "predicted": float(np.median(tot)), "lower": float(np.percentile(tot, 10)),
                    "upper": float(np.percentile(tot, 90)),
                    "kind": "ACTUAL + NOWCAST" if year == last.year else "FORECAST",
                    "actual_months": int((y.index.year == year).sum())})
    db.query(Forecast).filter(Forecast.indicator == indicator).delete()
    for r in out:
        db.add(Forecast(indicator=indicator, model=best, period=str(r["year"]), predicted=r["predicted"], lower=r["lower"],
                        upper=r["upper"], unit="MTND", metrics={"backtest": metrics, "kind": r["kind"],
                                                                 "actual_months": r["actual_months"],
                                                                 "train_period": f"{y.index[0]:%Y-%m} → {last:%Y-%m}",
                                                                 "interval": "80% (P10–P90 of 500 simulated paths)"}))
    db.flush()
    return {"indicator": indicator, "label": label, "model": best, "metrics": metrics, "annual": out,
            "train_period": f"{y.index[0]:%Y-%m} → {last:%Y-%m}"}


def run_forecasts(db: Session, log=print) -> str:
    msgs = []
    for ind, label in (("ins_imports", "Imports of goods"), ("ins_exports", "Exports of goods")):
        r = forecast_indicator(db, ind, label, log)
        msgs.append(f"{ind}: {r.get('model', r.get('status'))}")
    return "; ".join(msgs)
