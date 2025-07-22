import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime
from dotenv import load_dotenv


# Load .env variables (including webhook URL)
load_dotenv()
WEBHOOK_URL = os.getenv('RSI_DISCORD_WEBHOOK')


# Ticker list
tickers = [
'GLD', 'SLV', 'USO', 'SPY', 'QQQ',
'MGC=F', 'MCL=F', 'MES=F',
'EURUSD=X', 'JPY=X', 'GBPUSD=X'
]


# RSI calculator
def compute_rsi(data, period=14):
    close = data['close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# RSI crossover detection
def check_rsi_rebound_15m(ticker):
    df = yf.download(ticker, period="5d", interval="15m", progress=False)
    if df.empty or len(df) < 15:
        return False
    df['RSI'] = compute_rsi(df['Close'])
    return df['RSI'].iloc[-2] < 30 and df['RSI'].iloc[-1] > 30


# Duplicate alert log
def load_alerted_log(log_file="rsi_alert_log.txt"):
    try:
        with open(log_file, "r") as file:
            return set(line.strip() for line in file.readlines())
    except FileNotFoundError:
        # Create the file for future use
        with open(log_file, "w") as file:
            pass
        return set()


def update_alert_log(tickers_triggered, log_file="rsi_alert_log.txt"):
    with open(log_file, "a") as file:
    for ticker in tickers_triggered:
    file.write(f"{ticker}-{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")


# Send Discord alert with TradingView links
def send_discord_alert(tickers_triggered):
    if not WEBHOOK_URL:
    print(" Webhook URL is missing.")
    return


lines = []
for ticker in tickers_triggered:
tv_ticker = ticker.replace("=F", "") # Futures
if ticker.endswith("=X"):
tv_symbol = ticker.replace("=X", "")
tv_link = f"https://www.tradingview.com/chart/?symbol=FX:{tv_symbol}"
else:
tv_link = f"https://www.tradingview.com/chart/?symbol={tv_ticker.upper()}"
lines.append(f"• `{ticker}` → [View Chart]({tv_link})")


content = (
f" **RSI(14) crossed ABOVE 30** on the 15-minute chart:\n"
+ "\n".join(lines) +
f"\n {datetime.now().strftime('%Y-%m-%d %H:%M')}"
)


try:
response = requests.post(WEBHOOK_URL, json={"content": content})
if response.status_code == 204:
print(" Discord alert sent.")
else:
print(f" Webhook failed with status code {response.status_code}")
except Exception as e:
print(" Error sending Discord alert:", e)


# Main logic
def main():
    print(f" RSI scan started at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    alerted = load_alerted_log()
    new_signals = []


for ticker in tickers:
try:
if check_rsi_rebound_15m(ticker):
alert_id = f"{ticker}-{datetime.now().strftime('%Y-%m-%d %H:%M')}"
if not any(alert_id.startswith(f"{ticker}-") for alert_id in alerted):
new_signals.append(ticker)
except Exception as e:
print(f" Error checking {ticker}: {e}")


if new_signals:
send_discord_alert(new_signals)
update_alert_log(new_signals)
else:
print("No new RSI signals.")


if __name__ == "__main__":
main()






