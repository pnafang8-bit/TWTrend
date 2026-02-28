import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz

# 設定時區
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)

st.set_page_config(layout="wide", page_title="TWTrend | 台股趨勢儀表板")

# 配色
UP_COLOR = '#EB3323'
DOWN_COLOR = '#26A69A'
RS_LINE_COLOR = '#2196F3'

@st.cache_data(ttl=3600)
def fetch_auto_data(ticker):
    # 下載數據，使用 auto_adjust=True 確保格式統一
    df = yf.download(ticker, start=(now_tw - timedelta(days=730)).strftime('%Y-%m-%d'), auto_adjust=True)
    return df

def calculate_rs(stock_df, market_df):
    # 修正重點：使用 .squeeze() 確保抓到的是 Series (單一序列)
    s_close = stock_df['Close'].squeeze()
    m_close = market_df['Close'].squeeze()
    
    # 計算比率並標準化
    rs_raw = s_close / m_close
    rs_normalized = (rs_raw / rs_raw.iloc[0]) * 100
    return rs_normalized

st.title("🚀 TWTrend 台股自動化分析儀表板")
st.caption(f"📅 數據同步時間：{now_tw.strftime('%Y-%m-%d %H:%M:%S')}")

stock_id = st.sidebar.text_input("輸入台股代碼 (例如: 2330.TW)", "2330.TW")
market_id = "^TWII"

try:
    with st.spinner('正在修正資料格式並計算...'):
        # 抓取數據
        df_raw = fetch_auto_data(stock_id)
        m_df_raw = fetch_auto_data(market_id)
        
        # 確保日期對齊
        common_idx = df_raw.index.intersection(m_df_raw.index)
        df = df_raw.loc[common_idx].copy()
        m_df = m_df_raw.loc[common_idx].copy()

        # 安全抓取收盤價序列 (處理多重欄位問題)
        close_series = df['Close'].squeeze()
        high_series = df['High'].squeeze()
        low_series = df['Low'].squeeze()
        volume_series = df['Volume'].squeeze()

        # 計算指標
        df['MA50'] = ta.sma(close_series, length=50)
        df['MA150'] = ta.sma(close_series, length=150)
        df['MA200'] = ta.sma(close_series, length=200)
        df['RS_Line'] = calculate_rs(df, m_df)
        df['H_52W'] = high_series.rolling(window=252).max()
        df['L_52W'] = low_series.rolling(window=252).min()

    # --- 頂部摘要 ---
    last_p = close_series.iloc[-1]
    prev_p = close_series.iloc[-2]
    change_pct = ((last_p - prev_p) / prev_p) * 100
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最新收盤價", f"{last_p:.2f}", f"{change_pct:.2f}%")
    c2.metric("RS 強度指數", f"{df['RS_Line'].iloc[-1]:.2f}")
    c3.metric("52週高點距離", f"{((last_p/df['H_52W'].iloc[-1])-1)*100:.1f}%")
    c4.metric("成交量 (張)", f"{int(volume_series.iloc[-1]/1000):,}")

    # --- 圖表 ---
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.2, 0.3])

    # K線
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'].squeeze(), high=high_series, low=low_series, close=close_series,
        increasing_line_color=UP_COLOR, decreasing_line_color=DOWN_COLOR, name="K線"
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", line=dict(color='#FF9800')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], name="MA200", line=dict(color='#F44336')), row=1, col=1)

    # 成交量
    v_colors = [UP_COLOR if close_series.iloc[i] >= df['Open'].squeeze().iloc[i] else DOWN_COLOR for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=volume_series, marker_color=v_colors, name="成交量"), row=2, col=1)

    # RS
    fig.add_trace(go.Scatter(x=df.index, y=df['RS_Line'], line=dict(color=RS_LINE_COLOR, width=2), name="RS相對強度"), row=3, col=1)

    fig.update_layout(height=800, template='plotly_dark', xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # --- 檢核表 ---
    st.subheader("🏁 趨勢模板篩選 (Mark Minervini)")
    curr = df.iloc[-1]
    
    # 邏輯判斷
    results = [
        last_p > curr['MA150'] and last_p > curr['MA200'],
        curr['MA150'] > curr['MA200'],
        df['MA200'].iloc[-1] > df['MA200'].iloc[-22],
        curr['MA50'] > curr['MA150'] and curr['MA50'] > curr['MA200'],
        last_p > curr['MA50'],
        last_p >= (curr['L_52W'] * 1.30),
        last_p >= (curr['H_52W'] * 0.75),
        df['RS_Line'].iloc[-1] > df['RS_Line'].iloc[-22]
    ]
    
    labels = ["價格 > $$MA_{150}/200$$", "$$MA_{150} > MA_{200}$$", "$$MA_{200}$$ 向上", "$$MA_{50} > MA_{150}/200$$", 
              "價格 > $$MA_{50}$$", "高於低點 30%", "接近高點 25%", "RS 趨勢向上"]

    cols = st.columns(2)
    for i, (label, res) in enumerate(zip(labels, results)):
        with cols[i % 2]:
            st.info(f"{'✅' if res else '❌'} {label}")

except Exception as e:
    st.error(f"發生錯誤：{e}")
    st.info("建議檢查代碼格式，例如台積電請輸入 2330.TW")
