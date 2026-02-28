import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz

# 時區設定
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)

st.set_page_config(layout="wide", page_title="TWTrend | 台股趨勢修正版")

# 配色
UP_COLOR = '#EB3323'
DOWN_COLOR = '#26A69A'

@st.cache_data(ttl=3600)
def fetch_auto_data(ticker):
    # 下載數據
    df = yf.download(ticker, start=(now_tw - timedelta(days=730)).strftime('%Y-%m-%d'), auto_adjust=True)
    # 關鍵修正：如果是多重索引，只取第一層名稱，避免欄位歧義
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

def calculate_rs(stock_close, market_close):
    # 確保兩者都是 Series 且長度一致
    rs_raw = stock_close / market_close
    rs_normalized = (rs_raw / rs_raw.iloc[0]) * 100
    return rs_normalized

st.title("🚀 TWTrend 台股自動化分析儀表板")
st.caption(f"📅 數據同步時間：{now_tw.strftime('%Y-%m-%d %H:%M:%S')}")

stock_id = st.sidebar.text_input("輸入台股代碼 (例如: 2330.TW)", "2330.TW")
market_id = "^TWII"

try:
    with st.spinner('正在處理數據...'):
        df = fetch_auto_data(stock_id)
        m_df = fetch_auto_data(market_id)
        
        common_idx = df.index.intersection(m_df.index)
        df = df.loc[common_idx].copy()
        m_df = m_df.loc[common_idx].copy()

        # 強制轉換為單一 Series 並移除可能的 NaN
        close_s = df['Close'].squeeze()
        high_s = df['High'].squeeze()
        low_s = df['Low'].squeeze()
        m_close_s = m_df['Close'].squeeze()

        # 計算指標
        df['MA50'] = ta.sma(close_s, length=50)
        df['MA150'] = ta.sma(close_s, length=150)
        df['MA200'] = ta.sma(close_s, length=200)
        df['RS_Line'] = calculate_rs(close_s, m_close_s)
        df['H_52W'] = high_s.rolling(window=252).max()
        df['L_52W'] = low_s.rolling(window=252).min()

    # --- 取得最後一天的數值 (確保轉換為純數字 float) ---
    last_p = float(close_s.iloc[-1])
    prev_p = float(close_s.iloc[-2])
    ma50_last = float(df['MA50'].iloc[-1])
    ma150_last = float(df['MA150'].iloc[-1])
    ma200_last = float(df['MA200'].iloc[-1])
    ma200_prev = float(df['MA200'].iloc[-22]) # 一個月前
    rs_last = float(df['RS_Line'].iloc[-1])
    rs_prev = float(df['RS_Line'].iloc[-22])
    h52 = float(df['H_52W'].iloc[-1])
    l52 = float(df['L_52W'].iloc[-1])

    # --- 頂部摘要 ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最新收盤價", f"{last_p:.2f}", f"{((last_p-prev_p)/prev_p)*100:.2f}%")
    c2.metric("RS 強度指數", f"{rs_last:.2f}")
    c3.metric("52週高點距離", f"{((last_p/h52)-1)*100:.1f}%")
    c4.metric("成交量 (張)", f"{int(df['Volume'].iloc[-1].squeeze()/1000):,}")

    # --- 圖表 ---
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.2, 0.3])
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'].squeeze(), high=high_s, low=low_s, close=close_s,
                                increasing_line_color=UP_COLOR, decreasing_line_color=DOWN_COLOR, name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", line=dict(color='#FF9800')), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], name="MA200", line=dict(color='#F44336')), row=1, col=1)
    
    v_colors = [UP_COLOR if close_s.iloc[i] >= df['Open'].squeeze().iloc[i] else DOWN_COLOR for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'].squeeze(), marker_color=v_colors, name="成交量"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['RS_Line'], line=dict(color='#2196F3', width=2), name="RS"), row=3, col=1)
    fig.update_layout(height=800, template='plotly_dark', xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # --- 檢核表 (Minervini 趨勢模板) ---
    st.subheader("🏁 趨勢模板篩選 (Mark Minervini)")
    
    # 這裡的所有比較現在都是針對單一數值 (float)，不會再報錯
    results = [
        last_p > ma150_last and last_p > ma200_last,
        ma150_last > ma200_last,
        ma200_last > ma200_prev,
        ma50_last > ma150_last and ma50_last > ma200_last,
        last_p > ma50_last,
        last_p >= (l52 * 1.30),
        last_p >= (h52 * 0.75),
        rs_last > rs_prev
    ]
    
    labels = ["價格 > $$MA_{150}/200$$", "$$MA_{150} > MA_{200}$$", "$$MA_{200}$$ 向上趨勢", "$$MA_{50} > MA_{150}/200$$", 
              "價格 > $$MA_{50}$$", "較 52週低點反彈 > 30%", "距離 52週高點 25% 以內", "RS 指標一月內呈上升趨勢"]

    cols = st.columns(2)
    for i, (label, res) in enumerate(zip(labels, results)):
        with cols[i % 2]:
            st.info(f"{'✅' if res else '❌'} {label}")

except Exception as e:
    st.error(f"發生錯誤：{e}")
