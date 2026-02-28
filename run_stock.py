import streamlit as st
import pandas as pd
import numpy as np
import datetime

# ==============================
# 0. 頁面與樣式設定
# ==============================
st.set_page_config(layout="wide", page_title="TWTrend Pro RS Dashboard")

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: white; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("📈 TWTrend Pro | RS 強勢股 + 爆發股雷達")
st.info("💡 目前運作於：模擬數據模式 (Mock Mode)。已加入中文股票名稱對照。")

# ==============================
# 1. 模擬數據與中文名產生器
# ==============================
@st.cache_data
def get_mock_data():
    # 建立中文對照表
    tw_names = {
        "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電", 
        "2382": "廣達", "2301": "光寶科", "3231": "緯創", "2376": "技嘉", 
        "2603": "長榮", "2609": "陽明", "2881": "富邦金", "2882": "國泰金",
        "1101": "台泥", "1301": "台塑", "2002": "中鋼", "2412": "中華電"
    }
    
    # 模擬 500 檔股票代號
    tickers = [f"{i}" for i in range(1101, 1601)] 
    dates = pd.date_range(end=datetime.date.today(), periods=260)
    
    price_data = []
    for t in tickers:
        name = tw_names.get(t, f"模擬股-{t}")
        start_price = np.random.uniform(20, 500)
        volatility = np.random.uniform(0.01, 0.05)
        # 模擬隨機漫步走勢
        prices = start_price * (1 + np.random.randn(len(dates)) * volatility).cumsum()
        for i, date in enumerate(dates):
            price_data.append({
                "stock_id": t, 
                "name": name, 
                "trade_date": date, 
                "close": max(prices[i], 1)
            })
            
    df_p = pd.DataFrame(price_data)
    
    # 模擬大盤
    idx_prices = 18000 * (1 + np.random.randn(len(dates)) * 0.005).cumsum()
    df_i = pd.DataFrame({"trade_date": dates, "close": idx_prices})
    
    return df_p, df_i

# ==============================
# 2. RS 加權計算邏輯
# ==============================
def calculate_rs_logic(df_p):
    results = []
    for (stock_id, name), group in df_p.groupby(["stock_id", "name"]):
        group = group.sort_values("trade_date")
        curr_p = group.iloc[-1]["close"]
        prev_p = group.iloc[-2]["close"]
        
        # 加權 RS (近3個月兩倍權重)
        r3 = curr_p / group.iloc[-60]["close"]
        r6 = curr_p / group.iloc[-120]["close"]
        r9 = curr_p / group.iloc[-180]["close"]
        r12 = curr_p / group.iloc[0]["close"]
        weighted_val = (r3 * 2) + r6 + r9 + r12
        
        # 技術指標：MA
        ma50 = group["close"].rolling(50).mean().iloc[-1]
        ma200 = group["close"].rolling(200).mean().iloc[-1]
        
        results.append({
            "代號": stock_id,
            "名稱": name,
            "現在價": round(curr_p, 2),
            "今日漲跌%": round(((curr_p - prev_p) / prev_p) * 100, 2),
            "RS加權值": weighted_val,
            "一年高點": group["close"].max(),
            "MA50": ma50,
            "MA200": ma200
        })
    
    res_df = pd.DataFrame(results)
    res_df["RS評分"] = (res_df["RS加權值"].rank(pct=True) * 100).astype(int)
    return res_df

# ==============================
# 3. 畫面顯示與過濾
# ==============================
df_p, df_i = get_mock_data()
full_df = calculate_rs_logic(df_p)

# 篩選爆發股
def get_labels(row):
    labels = []
    if row["RS評分"] >= 90: labels.append("🔥RS強勢")
    if row["現在價"] >= row["一年高點"] * 0.98: labels.append("🚀創高")
    if row["現在價"] > row["MA50"] > row["MA200"]: labels.append("📈多頭趨勢")
    return " | ".join(labels)

full_df["分類標籤"] = full_df.apply(get_labels, axis=1)

# 顏色顯示邏輯 (漲紅跌綠)
def color_change(val):
    color = '#ff4b4b' if val > 0 else '#00ff00' if val < 0 else 'white'
    return f'color: {color}'

# 儀表板指標
c1, c2, c3 = st.columns(3)
c1.metric("監控總檔數", f"{len(full_df)} 檔")
c2.metric("RS強勢股 (RS>90)", f"{len(full_df[full_df['RS評分']>=90])} 檔")
c3.metric("趨勢噴發中", f"{len(full_df[full_df['今日漲跌%'] > 2])} 檔")

st.subheader("🚀 最終爆發潛力股 (RS > 90 + 趨勢向上)")
radar_df = full_df[full_df["RS評分"] >= 90].sort_values("RS評分", ascending=False).head(10)
st.table(radar_df[["代號", "名稱", "現在價", "今日漲跌%", "RS評分", "分類標籤"]])

st.subheader("🔥 全市場 RS 評分排名")
st.dataframe(
    full_df[["代號", "名稱", "現在價", "今日漲跌%", "RS評分", "分類標籤"]]
    .sort_values("RS評分", ascending=False)
    .style.applymap(color_change, subset=['今日漲跌%']),
    use_container_width=True,
    height=600
)
