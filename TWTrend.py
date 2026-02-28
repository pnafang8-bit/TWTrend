import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# 頁面配置
st.set_page_config(layout="wide", page_title="TWTrend | 台股趨勢儀表板")

# --- 配色定義 ---
UP_COLOR = '#EB3323'    # 起漲K線：紅漲
DOWN_COLOR = '#26A69A'  # 起漲K線：綠跌
RS_LINE_COLOR = '#2196F3' # 尼克萊 RS：專業藍
MA50_COLOR = '#FF9800'  
MA150_COLOR = '#9C27B0' 
MA200_COLOR = '#F44336' 

def fetch_data(ticker):
    # 下載數據
    df = yf.download(ticker, start=(datetime.now() - timedelta(days=730)))
    return df

def process_indicators(df, market_df):
    # 1. 均線系統
    df['MA50'] = ta.sma(df['Close'], length=50)
    df['MA150'] = ta.sma(df['Close'], length=150)
    df['MA200'] = ta.sma(df['Close'], length=200)
    
    # 2. 52 週區間
    df['H_52W'] = df['High'].rolling(window=252).max()
    df['L_52W'] = df['Low'].rolling(window=252).min()
    
    # 3. 尼克萊 RS 強度 (以 63 日為基準)
    period = 63
    stock_ret = df['Close'] / df['Close'].shift(period)
    market_ret = market_df['Close'] / market_df['Close'].shift(period)
    df['RS_Score'] = (stock_ret / market_ret) * 100
    
    return df

def get_minervini_status(df):
    if len(df) < 252: return [False] * 8
    curr = df.iloc[-1]
    ma200_prev = df['MA200'].shift(20).iloc[-1]
    
    c1 = curr['Close'] > curr['MA150'] and curr['Close'] > curr['MA200']
    c2 = curr['MA150'] > curr['MA200']
    c3 = curr['MA200'] > ma200_prev
    c4 = curr['MA50'] > curr['MA150'] and curr['MA50'] > curr['MA200']
    c5 = curr['Close'] > curr['MA50']
    c6 = curr['Close'] >= (curr['L_52W'] * 1.30)
    c7 = curr['Close'] >= (curr['H_52W'] * 0.75)
    c8 = curr['RS_Score'] > 100
    return [c1, c2, c3, c4, c5, c6, c7, c8]

# --- UI 介面 ---
st.title("📈 TWTrend 台股趨勢分析儀表板")

stock_id = st.sidebar.text_input("輸入台股代碼 (例如: 2330.TW)", "2330.TW")
market_id = "^TWII" 

try:
    with st.spinner('數據計算中...'):
        raw_stock = fetch_data(stock_id)
        raw_market = fetch_data(market_id)
        common_idx = raw_stock.index.intersection(raw_market.index)
        df = process_indicators(raw_stock.loc[common_idx], raw_market.loc[common_idx])
        
    # 頂部指標
    c_price = df['Close'].iloc[-1]
    p_change = (df['Close'].pct_change().iloc[-1]) * 100
    
    col1, col2, col3 = st.columns(3)
    col1.metric("當前股價", f"{c_price:.2f}", f"{p_change:.2f}%")
    col2.metric("RS 強度分數", f"{df['RS_Score'].iloc[-1]:.2f}")
    col3.metric("量能倍率", f"{(df['Volume'].iloc[-1]/df['Volume'].rolling(5).mean().iloc[-1]):.2f}x")

    # 圖表繪製
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.02, 
                        row_heights=[0.5, 0.2, 0.3],
                        subplot_titles=("起漲K線圖", "成交量", "尼克萊 RS 相對強度"))

    # K線與均線
    fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                                 increasing_line_color=UP_COLOR, decreasing_line_color=DOWN_COLOR, name="K線"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA50'], name="MA50", line=dict(color=MA50_COLOR)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df.index, y=df['MA200'], name="MA200", line=dict(color=MA200_COLOR)), row=1, col=1)

    # 成交量
    v_colors = [UP_COLOR if df['Close'].iloc[i] >= df['Open'].iloc[i] else DOWN_COLOR for i in range(len(df))]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=v_colors, name="成交量"), row=2, col=1)

    # RS 線
    fig.add_trace(go.Scatter(x=df.index, y=df['RS_Score'], line=dict(color=RS_LINE_COLOR, width=2), fill='tozeroy', name="RS強度"), row=3, col=1)

    fig.update_layout(height=800, template='plotly_dark', xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    # 檢核表
    st.subheader("🏆 Mark Minervini 趨勢準則檢核")
    results = get_minervini_status(df)
    labels = ["價格 > $$MA_{150}/200$$", "$$MA_{150} > MA_{200}$$", "$$MA_{200}$$ 向上", "$$MA_{50} > MA_{150}/200$$", 
              "價格 > $$MA_{50}$$", "高於52週低點 30%", "接近52週高點 25%", "RS 強度 > 100"]
    
    cols = st.columns(2)
    for i, (label, res) in enumerate(zip(labels, results)):
        with cols[i % 2]:
            st.write(f"{'✅' if res else '❌'} {label}")

except Exception as e:
    st.error(f"請輸入正確代碼 (如 2330.TW)。訊息: {e}")
