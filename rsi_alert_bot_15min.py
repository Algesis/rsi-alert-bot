import os
from datetime import datetime, timezone
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# ========= CONFIG =========
TICKERS = [
    "AAPL", "TSLA", "SPY", "QQQ", "NVDA",
    "MES=F", "MNQ=F", "MGC=F", "MCL=F", "MHG=F", "SIL=F",
    "EURUSD=X", "GBPUSD=X", "JPY=X", "USDJPY=X", "USDCAD=X", "AUDUSD=X"
]
WEBHOOK_URL = os.getenv("RSI_DISCORD_WEBHOOK")
LOG_FILE = "rsi_alert_log.txt"        # de-dup store
INTERVAL = "15m"
LOOKBACK_PERIOD = "7d"                # enough 15m bars for RSI(14)

# Map some common symbols to their TradingView exchange
TRADINGVIEW_EXCHANGES = {
    "AAPL": "NASDAQ", "TSLA": "NASDAQ",
    "AMZN": "NASDAQ", "SPY": "AMEX", "QQQ": "NASDAQ", "NVDA": "NASDAQ",
    "MES=F": "CME_MINI", "MNQ=F": "CME_MINI", "MGC=F": "COMEX", "MCL=F": "NYMEX", 
    "MHG=F": "COMEX", "SIL=F": "COMEX"
}

# ========= HELPERS =========
def get_tradingview_link(ticker: str) -> str:
    # FX (Yahoo: EURUSD=X) -> TradingView: FX:EURUSD
    if ticker.endswith("=X"):
        return f"https://www.tradingview.com/chart/?symbol=FX:{ticker.replace('=X','')}"
    # Futures (Yahoo: MES=F) -> TV continuous: MES1! on exchange
    if ticker.endswith("=F"):
        exch = TRADINGVIEW_EXCHANGES.get(ticker, "CME_MINI")
        tv_ticker = ticker.replace("=F", "1!")
        return f"https://www.tradingview.com/chart/?symbol={exch}:{tv_ticker}"
    # Stocks/ETFs
    exch = TRADINGVIEW_EXCHANGES.get(ticker, "NASDAQ")
    return f"https://www.tradingview.com/chart/?symbol={exch}:{ticker}"

def compute_rsi_wilder(series: pd.Series, period: int = 14) -> pd.Series:
    """Classic RSI using Wilder's smoothing (EMA with alpha=1/period)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder’s smoothing = EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def load_alerted_log(path: str = LOG_FILE) -> set:
    try:
        with open(path, "r") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()

def append_alert_log(keys: list, path: str = LOG_FILE):
    with open(path, "a") as f:
        for k in keys:
            f.write(k + "\n")

def send_discord_alert(tickers_triggered: list, bar_time_iso: str):
    if not WEBHOOK_URL:
        print("❌ Discord webhook not configured.")
        return
    lines = []
    for t in tickers_triggered:
        lines.append(f"• **{t}** → [Chart]({get_tradingview_link(t)})")
    msg = (
        "📈 **RSI(14) crossed ABOVE 30** on the **15-minute** chart\n"
        + "\n".join(lines)
        + f"\n🕒 Bar time: `{bar_time_iso}`"
    )
    try:
        r = requests.post(WEBHOOK_URL, json={"content": msg})
        print(f"✅ Discord alert sent (status {r.status_code}).")
    except Exception as e:
        print(f"❌ Discord send error: {e}")

def check_rsi_cross_15m(ticker: str):
    """Return tuple (triggered: bool, prev_rsi, last_rsi, bar_time) for diagnostics."""
    df = yf.download(ticker, period=LOOKBACK_PERIOD, interval=INTERVAL, progress=False)
    if df.empty or len(df) < 20:
        return (False, None, None, None)

    # Use only fully closed bars: last row is the most recent closed 15m candle in yfinance
    df["RSI"] = compute_rsi_wilder(df["Close"])
    rsi = df["RSI"].dropna()
    if len(rsi) < 2:
        return (False, None, None, None)

    # Take last two CLOSED bars
    last_time = rsi.index[-1]          # Timestamp of last closed bar
    prev_rsi = float(rsi.iloc[-2])
    last_rsi = float(rsi.iloc[-1])

    # Cross-up condition from <=30 to >30
    triggered = (prev_rsi <= 30.0) and (last_rsi > 30.0)
    return (triggered, prev_rsi, last_rsi, last_time)

# ========= MAIN =========
if __name__ == "__main__":
    print(f"🔍 Run at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} | interval={INTERVAL}")
    already = load_alerted_log()
    to_alert = []
    alert_keys = []
    bar_time_for_message = None

    for t in TICKERS:
        try:
            triggered, rsi_prev, rsi_now, bar_time = check_rsi_cross_15m(t)
            if rsi_prev is None:
                print(f"… {t}: no RSI yet (insufficient data)")
                continue

            # Log diagnostics
            bar_iso = bar_time.tz_convert("UTC").strftime("%Y-%m-%d %H:%M:%S %Z") if hasattr(bar_time, "tz_convert") else str(bar_time)
            print(f"… {t}: RSI[-2]={rsi_prev:.2f}, RSI[-1]={rsi_now:.2f} @ {bar_iso}")

            if triggered:
                # de-dup key uses ticker + the specific bar timestamp
                key = f"{t}|{bar_iso}"
                if key not in already:
                    to_alert.append(t)
                    alert_keys.append(key)
                    # remember one bar time to show in message
                    bar_time_for_message = bar_iso
        except Exception as e:
            print(f"❌ {t}: error {e}")

    if to_alert:
        send_discord_alert(to_alert, bar_time_for_message or "")
        append_alert_log(alert_keys)
    else:
        print("📉 No RSI cross-ups this run.")
