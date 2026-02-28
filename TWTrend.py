import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import pytz

# 設定時區為台北
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)

# 頁面配置
st.set_page_config(layout="wide", page_title=f"TWTrend | 台股起漲K線 ({now_tw.strftime('%Y-%m-%d')})")

# --- 起漲K線 & 尼克萊 RS 顏色設定 ---
UP_COLOR = '#EB3323'    # 漲：紅 (起漲K線風格)
DOWN_COLOR = '#26A69A'  # 跌：綠 (起漲K線風格)
RS_LINE_COLOR = '#2196F3' # RS強度：藍
MA50_COLOR = '#FF9800'  
MA150_COLOR = '#9C27B0' 
MA200_COLOR = '#F44336' 

@st.cache_data(ttl=3600) # 每小時自動更新一次快取
def fetch_auto_data(ticker):
    # 自動抓取從兩年前到「今天」的所有開盤資料
    # yfinance 會自動處理週末與國定假日，只回傳有開盤的日期
    df = yf.download(ticker, start=(now_tw - timedelta(days=730)).strftime('%Y-%m-%d'))
    return df

def calculate_rs(stock_df, market_df):
    # 尼克萊 RS 相對強度公式: (個股/大盤) 之比率
    # 我們採用 63 日 (一季) 的移動平均來平滑 RS 曲線
    rs_raw = stock_df['Close'] / market_df['Close']
    rs_normalized = (rs_raw / rs_raw.iloc[0]) * 100
    return rs_normalized

# --- UI 介面 ---
st.title("🚀 TWTrend 台股自動化分析儀表板")
st.caption(f"📅 目前台北時間：{now_tw.strftime('%Y-%m-%d %H:%M:%S')} (自動抓取最新開盤數據)")

# 側邊欄輸入
stock_id = st.sidebar.text_input("輸入台股代碼 (例如: 2330.TW 或 2603.TW)", "2330.TW")
market_id = "^TWII" # 加權指數

try:
    with st.spinner('正在從伺服器同步最新交易日數據...'):
        # 抓取個股與大盤
        df = fetch_auto_data(stock_id)
        m_df = fetch_auto_data(market_id)
        
        # 確保日期對齊
        common_idx = df.index.intersection(m_df.index)
        df = df.loc[common_idx].copy()
        m_df = m_df.loc[common_idx].copy()

        # 計算指標
        df['MA50'] = ta.sma(df['Close'], length=50)
        df['MA150'] = ta.sma(df['Close'], length=150)
        df['MA200'] = ta.sma(df['Close'], length=200)
        df['RS_Line'] = calculate_rs(df, m_df)
        df['H_52W'] = df['High'].rolling(window=252).max()
        df['L_52W'] = df['Low'].rolling(window=252).min()

    # --- 頂部摘要 ---
    last_price = df['Close'].iloc[-1]
    prev_price = df['Close'].iloc[-2]
    change_pct = ((last_price - prev_price) / prev_price) * 100
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("最新收盤價", f"{last_price:.2f}", f"{change_pct:.2f}%")
    c2.metric("RS 強度指數", f"{df['RS_Line'].iloc[-1]:.2f}")
    c3.metric("52週高點距離", f"{((last_price/df['H_52W'].iloc[-1])-1)*100:.1f}%")
    c4.metric("成交量 (張)", f"{int(df['Volume'].iloc[-1]/1000):,}")

    # --- 繪製起漲K線圖 ---
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, 
                        row_heights=[0.5, 0.2, 0.3],
                        subplot_titles=("K線與均線系統", "成交量 (量能倍率)", "尼克萊 RS 相對強度"))

    # 1. K線圖
    fig.add_trace(go.Candlestick(
        x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
        increasing_line_color=UP_COLOR, decreasing_line_color=DOWN_COLOR, name="K線"
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", line=dict(color=MA50_COLOR, width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], name="MA200", line=dict(color=MA200_COLOR, width=2)), row=1, col=1)

    # 2. 成交量
    v_colors = [UP_COLOR if df['Close'].iloc[i] >= df['Open'].iloc[i] else DOWN_COLOR for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=v_colors, name="成交量"), row=2, col=1)

    # 3. RS 強度
    fig.add_trace(go.Scatter(x=df.index, y=df['RS_Line'], line=dict(color=RS_LINE_COLOR, width=2), name="RS相對強度"), row=3, col=1)

    fig.update_layout(height=850, template='plotly_dark', xaxis_rangeslider_visible=False, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    # --- Minervini 趨勢準則檢核 ---
    st.subheader("🏁 趨勢模板篩選 (Mark Minervini)")
    
    curr = df.iloc[-1]
    results = [
        curr['Close'] > curr['MA150'] and curr['Close'] > curr['MA200'], # 1
        curr['MA150'] > curr['MA200'],                                  # 2
        df['MA200'].iloc[-1] > df['MA200'].iloc[-22],                  # 3
        curr['MA50'] > curr['MA150'] and curr['MA50'] > curr['MA200'],  # 4
        curr['Close'] > curr['MA50'],                                   # 5
        curr['Close'] >= (curr['L_52W'] * 1.30),                       # 6
        curr['Close'] >= (curr['H_52W'] * 0.75),                       # 7
        df['RS_Line'].iloc[-1] > df['RS_Line'].iloc[-22]               # 8 (RS趨勢向上)
    ]
    
    labels = [
        "股價在 $$MA_{150}$$ 與 $$MA_{200}$$ 之上",
        "$$MA_{150}$$ 高於 $$MA_{200}$$",
        "$$MA_{200}$$ 正在向上趨勢 (一個月對比)",
        "$$MA_{50}$$ 位於 $$MA_{150}$$ 與 $$MA_{200}$$ 之上",
        "股價在 $$MA_{50}$$ 之上",
        "股價高於 52週低點 30%",
        "股價距離 52週高點 25% 以內",
        "尼克萊 RS 指標呈現上升趨勢"
    ]

    cols = st.columns(2)
    for i, (label, res) in enumerate(zip(labels, results)):
        with cols[i % 2]:
            st.info(f"{'✅' if res else '❌'} {label}")

except Exception as e:
    st.warning(f"目前無法取得 {stock_id} 的數據，請確認代碼是否正確 (需包含 .TW 或 .TWO)。")
    st.error(f"錯誤訊息: {e}")
