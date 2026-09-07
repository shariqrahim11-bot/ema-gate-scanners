import os
import time
import ccxt
import pandas as pd

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEFRAME = "4h"
MAX_SPREAD = 0.50       # 4 EMAs max 0.50% apart
NEAR_EMAS = 0.35        # price must be near EMA gate
MIN_BARS = 220

exchange = ccxt.bybit({
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})


def send_telegram(message):
    import requests

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(message)
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        },
        timeout=20
    )


def check_gate(symbol):
    try:
        candles = exchange.fetch_ohlcv(
            symbol,
            timeframe=TIMEFRAME,
            limit=MIN_BARS
        )

        if len(candles) < MIN_BARS:
            return None

        df = pd.DataFrame(
            candles,
            columns=[
                "time",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

        # Ignore currently forming candle
        df = df.iloc[:-1].copy()

        for length in [20, 50, 100, 200]:
            df[f"ema{length}"] = (
                df["close"].ewm(
                    span=length,
                    adjust=False
                ).mean()
            )

        e20 = df["ema20"]
        e50 = df["ema50"]
        e100 = df["ema100"]
        e200 = df["ema200"]

        # Current EMA spread
        current = df.iloc[-1]

        emas = [
            current["ema20"],
            current["ema50"],
            current["ema100"],
            current["ema200"]
        ]

        spread = (
            (max(emas) - min(emas))
            / current["close"]
            * 100
        )

        # Previous EMA spread
        previous = df.iloc[-2]

        previous_emas = [
            previous["ema20"],
            previous["ema50"],
            previous["ema100"],
            previous["ema200"]
        ]

        previous_spread = (
            (max(previous_emas) - min(previous_emas))
            / previous["close"]
            * 100
        )

        # Gate must be getting tighter
        tightening = spread < previous_spread

        # Bullish direction
        bullish = (
            current["close"] > current["ema200"]
            and current["ema200"] > previous["ema200"]
        )

        # Bearish direction
        bearish = (
            current["close"] < current["ema200"]
            and current["ema200"] < previous["ema200"]
        )

        # Price near EMA gate
        gate_high = max(emas)
        gate_low = min(emas)

        near_gate = (
            current["close"] >= gate_low * (1 - NEAR_EMAS / 100)
            and
            current["close"] <= gate_high * (1 + NEAR_EMAS / 100)
        )

        if (
            spread <= MAX_SPREAD
            and tightening
            and near_gate
            and bullish
        ):
            return (
                f"🟢 CRYPTO EMA GATE FORMING\n\n"
                f"Symbol: {symbol}\n"
                f"Timeframe: 4H\n"
                f"Direction: BULLISH\n"
                f"EMA: 20 / 50 / 100 / 200\n"
                f"Spread: {spread:.3f}%\n\n"
                f"⚠️ Gate forming BEFORE breakout."
            )

        if (
            spread <= MAX_SPREAD
            and tightening
            and near_gate
            and bearish
        ):
            return (
                f"🔴 CRYPTO EMA GATE FORMING\n\n"
                f"Symbol: {symbol}\n"
                f"Timeframe: 4H\n"
                f"Direction: BEARISH\n"
                f"EMA: 20 / 50 / 100 / 200\n"
                f"Spread: {spread:.3f}%\n\n"
                f"⚠️ Gate forming BEFORE breakout."
            )

    except Exception as e:
        print(f"{symbol}: {e}")

    return None


def main():

    markets = exchange.load_markets()

    symbols = []

    for symbol, market in markets.items():

        if (
            market.get("spot")
            and market.get("active")
            and market.get("quote") == "USDT"
            and "/" in symbol
        ):
            symbols.append(symbol)

    print(f"Scanning {len(symbols)} crypto pairs...")

    for symbol in symbols:

        alert = check_gate(symbol)

        if alert:
            print(alert)
            send_telegram(alert)

        time.sleep(0.15)


if __name__ == "__main__":
    main()
