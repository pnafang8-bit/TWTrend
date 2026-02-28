# TWTrend.py
import streamlit as st
import pandas as pd
import pandas_ta as ta
import requests
from datetime import datetime, timedelta
import pytz
import time

# ---------------------------
# 基本設定
# ---------------------------
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)

st.set_page_config(layout="wide", page_title="TWTrend | 多週期 RS 強勢股分析")
st.title("💹 TWTrend 強勢股分析 (TWSE 官方資料版)")

# ---------------------------
# TWSE API 抓取函式
# ---------------------------
def fetch_twii_data(days=750):
    closes = []
    dates = [(now_tw - timedelta(days=i)).strftime('%Y%m%d') for i in range(days)]

    for d in dates[::-1]:
        url = f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&date={d}&type=ALLBUT0999"
        try:
            r = requests.get(url, timeout=10)
            js = r.json()
            if 'data9' in js and js['data9']:
                idx_close = float(js['data9'][0][1].replace(',', ''))
                closes.append(idx_close)
        except:
            continue
        time.sleep(0.2)

    return pd.Series(closes)


def fetch_stock_data_twse(stock_id, days=750):
    dfs = []
    months = pd.date_range(end=now_tw, periods=int(days/30)+2, freq='M')

    for m in months:
        date_str = m.strftime('%Y%m01')
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={stock_id}"
        try:
            r = requests.get(url, timeout=10)
            js = r.json()
            if 'data' in js:
                df = pd.DataFrame(js['data'], columns=[
                    'Date','Volume','Turnover','Open','High','Low','Close','Change','Transaction'
                ])
                df['Date'] = pd.to_datetime(df['Date'].str.replace('/', '-'))
                df['Close'] = df['Close'].str.replace(',', '').astype(float)
                df['High'] = df['High'].str.replace(',', '').astype(float)
                df['Low'] = df['Low'].str.replace(',', '').astype(float)
                dfs.append(df[['Date','Close','High','Low']])
        except:
            continue
        time.sleep(0.2)

    if dfs:
        out = pd.concat(dfs).sort_values('Date').drop_duplicates('Date')
        out.set_index('Date', inplace=True)
        return out.tail(750)
    return None


def fetch_bulk_data(tickers, days=750):
    data_dict = {}
    for t in tickers:
        sid = t.replace('.TW','').strip()
        df = fetch_stock_data_twse(sid, days)
        if df is not None:
            data_dict[t] = df
    return data_dict

# ---------------------------
# 分析邏輯
# ---------------------------
def analyze_stock(ticker, full_df, market_close):
    try:
        stock_df = full_df.get(ticker)
        if stock_df is None or len(stock_df) < 250:
            return None

        close_s = stock_df['Close']
        high_s = stock_df['High']
        low_s = stock_df['Low']

        ma50 = ta.sma(close_s, length=50)
        ma150 = ta.sma(close_s, length=150)
        ma200 = ta.sma(close_s, length=200)

        stock_perf_1y = close_s.iloc[-1] / close_s.iloc[-252]
        mkt_perf_1y = market_close.iloc[-1] / market_close.iloc[-252]
        rs_1y = round((stock_perf_1y / mkt_perf_1y) * 100, 2)

        stock_perf_3m = close_s.iloc[-1] / close_s.iloc[-63]
        mkt_perf_3m = market_close.iloc[-1] / market_close.iloc[-63]
        rs_3m = round((stock_perf_3m / mkt_perf_3m) * 100, 2)

        q_return = round(((stock_perf_3m - 1) * 100), 2)

        rs_line = (close_s / market_close.loc[stock_df.index]) * 100

        last_p = float(close_s.iloc[-1])
        m50 = float(ma50.iloc[-1])
        m150 = float(ma150.iloc[-1])
        m200 = float(ma200.iloc[-1])
        m200_prev = float(ma200.iloc[-22])
        rs_now = float(rs_line.iloc[-1])
        rs_prev = float(rs_line.iloc[-22])
        curr_h52 = float(high_s.rolling(window=252).max().iloc[-1])
        curr_l52 = float(low_s.rolling(window=252).min().iloc[-1])

        cond = [
            last_p > m150 and last_p > m200,
            m150 > m200,
            m200 > m200_prev,
            m50 > m150 and m50 > m200,
            last_p > m50,
            last_p >= (curr_l52 * 1.30),
            last_p >= (curr_h52 * 0.75),
            rs_now > rs_prev
        ]

        score = sum(cond)
        if score == 0:
            return None

        return {
            "總得分": score,
            "代號": ticker.replace('.TW',''),
            "現價": round(last_p, 2),
            "季報酬(%)": q_return,
            "RS年強度": rs_1y,
            "RS季強度": rs_3m
        }
    except:
        return None

# ---------------------------
# UI
# ---------------------------
st.sidebar.header("分析清單")
input_str = st.sidebar.text_area("輸入台股代號 (例: 2330.TW, 2454.TW)")
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("執行完整計算"):
    if not ticker_list:
        st.error("請輸入股票代號")
    else:
        with st.spinner("抓取 TWSE 官方資料中..."):
            m_close = fetch_twii_data()
            all_data = fetch_bulk_data(ticker_list)

            results = []
            for ticker in ticker_list:
                res = analyze_stock(ticker, all_data, m_close)
                if res:
                    results.append(res)

            if not results:
                st.warning("無符合條件股票")
            else:
                df_res = pd.DataFrame(results)
                df_res = df_res.sort_values(
                    by=["總得分", "RS年強度", "RS季強度"],
                    ascending=[False, False, False]
                )

                st.success(f"完成！共 {len(df_res)} 檔強勢股")
                st.dataframe(df_res, use_container_width=True, height=600)

                csv = df_res.to_csv(index=False).encode('utf-8-sig')
                st.download_button("下載CSV", csv, f"TW_RS_{now_tw.strftime('%Y%m%d')}.csv", "text/csv")
else:
    st.info("請輸入股票代號並執行分析")
