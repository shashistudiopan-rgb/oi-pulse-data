"""
================================================================================
INSTITUTIONAL FOOTPRINT SCANNER — AUTO MODE (for GitHub Actions)
================================================================================
Ye version GitHub Actions ke through roz automatically chalta hai. Isko haath
se chalane ki zaroorat nahi — workflow file (.github/workflows/daily-scan.yml)
isse har trading day market band hone ke baad khud trigger karti hai.

Kya karta hai:
  1. NSE F&O stocks ka price, volume, OI fetch karta hai
  2. oi_history.csv me roz ka data append karta hai (ye repo me commit hoti hai)
  3. Institutional action (Long Buildup / Short Covering / etc.) classify karta hai
  4. Final ranked result ko scan_result.json me likh deta hai
     -> Dashboard (oi_scanner_auto.html) seedha isi JSON file ko GitHub se
        fetch karke dikhata hai. Kisi manual paste ki zaroorat nahi.

DISCLAIMER: Ye ek educational/technical screening tool hai, investment advice
nahi. Institutional activity ka estimate hai, confirmation nahi.
================================================================================
"""

import pandas as pd
import numpy as np
import os
import json
import time
from datetime import datetime

try:
    from nsepython import nse_eq, nse_fno
except ImportError:
    raise SystemExit("Pehle ye run karein: pip install nsepython pandas numpy")

# nsepython ka fnolist() function abhi NSE ke site-structure change ki wajah se
# fail ho raha hai, isliye popular F&O stocks ki apni fixed list use kar rahe hain.
# Zaroorat ho to isme aur symbols add/remove kar sakte hain.
FNO_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL",
    "KOTAKBANK", "LT", "AXISBANK", "ITC", "HINDUNILVR", "BAJFINANCE", "MARUTI",
    "TATASTEEL", "TATAMOTORS", "SUNPHARMA", "TITAN", "ADANIENT", "ADANIPORTS",
    "ULTRACEMCO", "NTPC", "POWERGRID", "M&M", "WIPRO", "HCLTECH", "TECHM",
    "BAJAJFINSV", "ONGC", "JSWSTEEL", "GRASIM", "INDUSINDBK", "COALINDIA",
    "CIPLA", "DRREDDY", "EICHERMOT", "HEROMOTOCO", "BAJAJ-AUTO", "BPCL",
    "DIVISLAB", "SBILIFE", "HDFCLIFE", "APOLLOHOSP", "NESTLEIND", "BRITANNIA",
    "TATACONSUM", "UPL", "VEDL", "PIDILITIND", "DLF", "SIEMENS", "GODREJCP",
    "HAVELLS", "AMBUJACEM", "SHREECEM", "ICICIGI", "ICICIPRULI", "BANKBARODA",
    "PNB", "IDFCFIRSTB", "FEDERALBNK", "CANBK", "AUROPHARMA", "LUPIN",
    "BIOCON", "MOTHERSON", "BOSCHLTD", "MRF", "TVSMOTOR", "ASHOKLEY",
    "ZOMATO", "NYKAA", "PAYTM", "IRCTC", "TATAPOWER", "ADANIGREEN",
    "ADANIPOWER", "JINDALSTEL", "SAIL", "NMDC", "HINDALCO", "NATIONALUM",
    "GAIL", "IOC", "PETRONET", "CONCOR", "BEL", "HAL", "BHEL",
]

HISTORY_FILE = "oi_history.csv"
RESULT_FILE = "scan_result.json"
LOOKBACK_DAYS = 5
VOLUME_SPIKE_THRESHOLD = 1.5
MIN_OI_CHANGE_PCT = 5


def fetch_today_snapshot(symbols):
    rows = []
    for sym in symbols:
        try:
            eq = nse_eq(sym)
            fno = nse_fno(sym)

            ltp = float(eq["priceInfo"]["lastPrice"])
            prev_close = float(eq["priceInfo"]["previousClose"])
            price_change_pct = round((ltp - prev_close) / prev_close * 100, 2)

            volume = int(eq["preOpenMarket"].get("totalTradedVolume", 0) or
                         eq["securityWiseDP"].get("quantityTraded", 0))

            stock_futures = [
                c for c in fno["stocks"]
                if c["metadata"]["instrumentType"] == "Stock Futures"
            ]
            if not stock_futures:
                continue
            near_month = stock_futures[0]
            oi = int(near_month["marketDeptOrderBook"]["tradeInfo"]["openInterest"])
            oi_change = int(near_month["marketDeptOrderBook"]["tradeInfo"]["changeinOpenInterest"])
            oi_change_pct = round(oi_change / (oi - oi_change) * 100, 2) if (oi - oi_change) != 0 else 0

            rows.append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "symbol": sym,
                "ltp": ltp,
                "price_change_pct": price_change_pct,
                "volume": volume,
                "oi": oi,
                "oi_change_pct": oi_change_pct,
            })
            time.sleep(0.4)
        except Exception as e:
            print(f"  [skip] {sym}: {e}")
            continue
    return pd.DataFrame(rows)


def update_history(today_df):
    if os.path.exists(HISTORY_FILE):
        hist = pd.read_csv(HISTORY_FILE)
        hist = hist[hist["date"] != today_df["date"].iloc[0]]
        hist = pd.concat([hist, today_df], ignore_index=True)
    else:
        hist = today_df
    hist.to_csv(HISTORY_FILE, index=False)
    return hist


def get_oi_trend(hist, symbol, days=LOOKBACK_DAYS):
    sub = hist[hist["symbol"] == symbol].sort_values("date").tail(days)
    return [round(x, 1) for x in sub["oi_change_pct"].tolist()]


def classify_action(price_change_pct, oi_change_pct):
    if price_change_pct > 0 and oi_change_pct > 0:
        return "Long Buildup", "bull"
    elif price_change_pct > 0 and oi_change_pct < 0:
        return "Short Covering", "bull"
    elif price_change_pct < 0 and oi_change_pct > 0:
        return "Short Buildup", "bear"
    elif price_change_pct < 0 and oi_change_pct < 0:
        return "Long Unwinding", "bear"
    return "Neutral", "neutral"


def score_row(row, avg_volume_map, oi_trend):
    score = 0
    avg_vol = avg_volume_map.get(row["symbol"], row["volume"])
    vol_ratio = row["volume"] / avg_vol if avg_vol else 1

    if vol_ratio >= VOLUME_SPIKE_THRESHOLD:
        score += 2
    if abs(row["oi_change_pct"]) >= MIN_OI_CHANGE_PCT:
        score += 2

    action, bias = classify_action(row["price_change_pct"], row["oi_change_pct"])
    if action == "Long Buildup":
        score += 3
    elif action == "Short Covering":
        score += 1
    elif action == "Short Buildup":
        score -= 3
    elif action == "Long Unwinding":
        score -= 1

    if len(oi_trend) >= 3 and all(x > 0 for x in oi_trend[-3:]):
        score += 2

    return score, action, bias, round(vol_ratio, 2)


def scan_market():
    symbols = FNO_SYMBOLS
    print(f"Total {len(symbols)} F&O stocks ke saath scan shuru ho raha hai...")

    today_df = fetch_today_snapshot(symbols)
    if today_df.empty:
        print("Koi data nahi mila.")
        return None

    hist = update_history(today_df)
    avg_volume_map = hist.groupby("symbol")["volume"].mean().to_dict()

    results = []
    for _, row in today_df.iterrows():
        oi_trend = get_oi_trend(hist, row["symbol"])
        score, action, bias, vol_ratio = score_row(row, avg_volume_map, oi_trend)
        results.append({
            "symbol": row["symbol"],
            "ltp": row["ltp"],
            "priceChgPct": row["price_change_pct"],
            "volRatio": vol_ratio,
            "oiChgPct": row["oi_change_pct"],
            "trend": oi_trend,
            "action": action,
            "bias": bias,
            "score": score,
        })

    results.sort(key=lambda r: r["score"], reverse=True)

    output = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "daysTracked": hist["date"].nunique(),
        "results": results,
    }
    with open(RESULT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved {RESULT_FILE} with {len(results)} stocks.")
    return output


if __name__ == "__main__":
    scan_market()
