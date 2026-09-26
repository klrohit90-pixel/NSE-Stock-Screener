import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta
import plotly.graph_objects as go

st.set_page_config(page_title="NSE Strategy Screener", layout="wide")

WATCHLIST_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "LICI.NS", "HINDUNILVR.NS",
    "LT.NS", "TATAMOTORS.NS", "AXISBANK.NS", "SUNPHARMA.NS", "TITAN.NS"
]

def fetch_and_calculate(symbol, interval_key="1d"):
    period = "2y" if interval_key == "1d" else ("5y" if interval_key == "1wk" else "10y")
    df = yf.download(symbol, period=period, interval=interval_key, progress=False)
    if df.empty or len(df) < 50:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    for p in [5, 9, 20, 50, 100, 200]:
        df[f"SMA_{p}"] = ta.sma(df["Close"], length=p)
        df[f"EMA_{p}"] = ta.ema(df["Close"], length=p)

    for p in [20, 50, 200]:
        df[f"WMA_{p}"] = ta.wma(df["Close"], length=p)

    df["RSI_14"] = ta.rsi(df["Close"], length=14)
    df["RSI_9"] = ta.rsi(df["Close"], length=9)
    df["EMA_3_RSI_9"] = ta.ema(df["RSI_9"], length=3)
    df["WMA_21_RSI_9"] = ta.wma(df["RSI_9"], length=21)
    df["WMA_21_RSI_14"] = ta.wma(df["RSI_14"], length=21)

    bb = ta.bbands(df["Close"], length=20, std=2)
    if bb is not None and not bb.empty:
        df["BB_Upper"] = bb.iloc[:, 0]
        df["BB_Middle"] = bb.iloc[:, 1]
        df["BB_Lower"] = bb.iloc[:, 2]

    macd = ta.macd(df["Close"], fast=12, slow=26, signal=9)
    if macd is not None and not macd.empty:
        df["MACD"] = macd.iloc[:, 0]
        df["MACD_Histogram"] = macd.iloc[:, 1]
        df["MACD_Signal"] = macd.iloc[:, 2]

    adx = ta.adx(df["High"], df["Low"], df["Close"], length=14)
    if adx is not None and not adx.empty:
        df["ADX_14"] = adx.iloc[:, 0]
        df["DMP_14"] = adx.iloc[:, 1]
        df["DMN_14"] = adx.iloc[:, 2]

    st_val = ta.supertrend(df["High"], df["Low"], df["Close"], length=7, multiplier=3)
    if st_val is not None and not st_val.empty:
        df["SUPERTREND"] = st_val.iloc[:, 0]
        df["SUPERT_DIR"] = st_val.iloc[:, 1]

    df["Vol_20_SMA"] = ta.sma(df["Volume"], length=20)
    df["Volume_Ratio"] = df["Volume"] / df["Vol_20_SMA"]

    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    body = (c - o).abs()
    rng = h - l
    df["Pattern_Hammer"] = (c > o) & ((l < (o - 2 * body)) & (h - c <= 0.1 * body))
    df["Pattern_Doji"] = body <= (0.1 * rng)
    df["Pattern_Marubozu"] = (c > o) & (body >= 0.85 * rng)
    df["Pattern_Bullish_Engulfing"] = (c > o) & (c.shift(1) < o.shift(1)) & (c >= o.shift(1)) & (o <= c.shift(1))

    return df

st.title("🏹 NSE Live Technical Strategy Screener")
tabs = st.tabs(["📊 Screener & Strategy Builder", "📈 Single Stock Deep Dive"])

with tabs[0]:
    st.subheader("Filter Stocks by Technical Indicators")
    col1, col2, col3 = st.columns(3)
    with col1:
        timeframe = st.selectbox("Select Timeframe", ["Daily (1D)", "Weekly (1W)", "Monthly (1M)"])
        tf_code = "1d" if "Daily" in timeframe else ("1wk" if "Weekly" in timeframe else "1mo")
    with col2:
        condition_trend = st.selectbox(
            "Trend / Moving Average Strategy",
            ["Any", "Close > 200 EMA (Long-term Bullish)", "Close > 20 SMA & 20 SMA > 50 SMA", "Supertrend Bullish (7, 3)", "Golden Cross (50 EMA > 200 EMA)"]
        )
    with col3:
        condition_momentum = st.selectbox(
            "Momentum & Oscillators",
            ["Any", "RSI(14) > 60 (Strong Momentum)", "RSI(9) > WMA(21) on RSI", "MACD Line > Signal Line", "ADX(14) > 25 & +DI > -DI"]
        )

    col4, col5 = st.columns(2)
    with col4:
        condition_pattern = st.selectbox("Candlestick & Volume Patterns", ["Any", "Volume > 2x 20-Day Avg Volume", "Hammer Pattern", "Bullish Engulfing", "Marubozu"])
    with col5:
        compare_nifty = st.checkbox("Only stocks outperforming Nifty 50 (Past 1 Month)", value=True)

    if st.button("🚀 Run Live Scan"):
        results = []
        progress_bar = st.progress(0)
        bench_df = yf.download("^NSEI", period="1mo", interval="1d", progress=False)
        bench_ret = ((bench_df["Close"].iloc[-1] / bench_df["Close"].iloc[0]) - 1) * 100 if not bench_df.empty else 0

        for i, sym in enumerate(WATCHLIST_STOCKS):
            progress_bar.progress((i + 1) / len(WATCHLIST_STOCKS))
            df = fetch_and_calculate(sym, interval_key=tf_code)
            if df is None:
                continue

            last = df.iloc[-1]
            prev = df.iloc[-2]
            stock_ret = ((last["Close"] / df["Close"].iloc[-21]) - 1) * 100 if len(df) >= 21 else 0

            pass_trend = True
            if condition_trend == "Close > 200 EMA (Long-term Bullish)":
                pass_trend = last["Close"] > last["EMA_200"]
            elif condition_trend == "Close > 20 SMA & 20 SMA > 50 SMA":
                pass_trend = (last["Close"] > last["SMA_20"]) and (last["SMA_20"] > last["SMA_50"])
            elif condition_trend == "Supertrend Bullish (7, 3)":
                pass_trend = last["SUPERT_DIR"] == 1
            elif condition_trend == "Golden Cross (50 EMA > 200 EMA)":
                pass_trend = (last["EMA_50"] > last["EMA_200"]) and (prev["EMA_50"] <= prev["EMA_200"])

            pass_mom = True
            if condition_momentum == "RSI(14) > 60 (Strong Momentum)":
                pass_mom = last["RSI_14"] > 60
            elif condition_momentum == "RSI(9) > WMA(21) on RSI":
                pass_mom = last["RSI_9"] > last["WMA_21_RSI_9"]
            elif condition_momentum == "MACD Line > Signal Line":
                pass_mom = last["MACD"] > last["MACD_Signal"]
            elif condition_momentum == "ADX(14) > 25 & +DI > -DI":
                pass_mom = (last["ADX_14"] > 25) and (last["DMP_14"] > last["DMN_14"])

            pass_pat = True
            if condition_pattern == "Volume > 2x 20-Day Avg Volume":
                pass_pat = last["Volume_Ratio"] >= 2.0
            elif condition_pattern == "Hammer Pattern":
                pass_pat = bool(last["Pattern_Hammer"])
            elif condition_pattern == "Bullish Engulfing":
                pass_pat = bool(last["Pattern_Bullish_Engulfing"])
            elif condition_pattern == "Marubozu":
                pass_pat = bool(last["Pattern_Marubozu"])

            pass_bench = (stock_ret > bench_ret) if compare_nifty else True

            if pass_trend and pass_mom and pass_pat and pass_bench:
                results.append({
                    "Symbol": sym.replace(".NS", ""),
                    "LTP": round(float(last["Close"]), 2),
                    "RSI (14)": round(float(last["RSI_14"]), 1),
                    "Supertrend": "Bullish" if last["SUPERT_DIR"] == 1 else "Bearish",
                    "ADX (14)": round(float(last["ADX_14"]), 1),
                    "Vol Ratio": round(float(last["Volume_Ratio"]), 2),
                    "1M Return %": round(float(stock_ret), 2),
                    "Outperf. Nifty %": round(float(stock_ret - bench_ret), 2)
                })

        st.success(f"Scanning Complete! Found {len(results)} matches.")
        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True)
        else:
            st.warning("Koi stock match nahi hua. Filter ko thoda loose karein.")

with tabs[1]:
    sel_stock = st.selectbox("Select Stock to Compare with Nifty", WATCHLIST_STOCKS)
    st_df = yf.download(sel_stock, period="1y", interval="1d", progress=False)
    idx_df = yf.download("^NSEI", period="1y", interval="1d", progress=False)
    if isinstance(st_df.columns, pd.MultiIndex): st_df.columns = st_df.columns.get_level_values(0)
    if isinstance(idx_df.columns, pd.MultiIndex): idx_df.columns = idx_df.columns.get_level_values(0)

    norm_stock = (st_df["Close"] / st_df["Close"].iloc[0]) * 100
    norm_nifty = (idx_df["Close"] / idx_df["Close"].iloc[0]) * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=norm_stock.index, y=norm_stock, name=sel_stock, line=dict(color='#00E676', width=2)))
    fig.add_trace(go.Scatter(x=norm_nifty.index, y=norm_nifty, name="Nifty 50 Index", line=dict(color='#2979FF', width=2, dash='dash')))
    fig.update_layout(title=f"Relative Performance: {sel_stock} vs Nifty 50", template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
  
