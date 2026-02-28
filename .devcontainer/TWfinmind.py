import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
from FinMind.data import DataLoader

st.set_page_config(page_title="台股 RS 強勢股排名 - FinMind", layout="wide")

# ────────────────────────────────────────────────
# Sidebar - FinMind Token
# ────────────────────────────────────────────────
st.sidebar.title("⚙️ FinMind 設定")
token = st.sidebar.text_input(
    "輸入 FinMind API Token",
    type="password",
    help="免費註冊：https://finmindtrade.com/analysis/#/account/register"
)

if token:
    st.sidebar.success("Token 已輸入")
else:
    st.sidebar.warning("未輸入 Token → 使用免費額度（較慢）")

# ────────────────────────────────────────────────
# 取得所有台股清單
# ────────────────────────────────────────────────
@st.cache_data(ttl=86400 * 7)
def get_all_stocks(_dl):
    try:
        df = _dl.taiwan_stock_info()
        # 只保留上市、上櫃、ETF（股票代碼 4 位數或 00xx）
        df = df[df['stock_id'].str.match(r'^\d{4}$|^00\d{2}$')]
        return df.sort_values('stock_id')
    except:
        # 備用清單（當 Token 無效或網路問題）
        return pd.DataFrame({
            'stock_id': ['2330','2317','2454','2308','2412','0050','006208','2303','2881','2882']
        })

# ────────────────────────────────────────────────
# 載入股價資料
# ────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner="正在從 FinMind 載入台股歷史資料...")
def load_price_data(token_input):
    dl = DataLoader(token=token_input) if token_input else DataLoader()

    stock_info = get_all_stocks(dl)
    all_ids = stock_info['stock_id'].tolist()

    # 使用者控制載入數量，避免超過 API 限制
    max_load = st.sidebar.slider("載入股票數量（建議 100~300）", 50, 500, 200)
    stock_list = all_ids[:max_load]

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=1000)).strftime("%Y-%m-%d")  # ≈ 2.7 年

    data_list = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, sid in enumerate(stock_list):
        try:
            df = dl.taiwan_stock_daily(
                stock_id=sid,
                start_date=start_date,
                end_date=end_date
            )
            if not df.empty and 'close' in df.columns:
                df = df[['date', 'stock_id', 'close']].copy()
                df['date'] = pd.to_datetime(df['date'])
                data_list.append(df)
        except:
            pass

        progress_bar.progress((i + 1) / len(stock_list))
        status_text.text(f"處理中：{i+1}/{len(stock_list)} → {sid}")

        time.sleep(0.3)  # 避免超過速率限制

    if not data_list:
        st.error("無法取得任何資料，請檢查 Token 或網路")
        return pd.DataFrame()

    price_df = pd.concat(data_list, ignore_index=True)
    price_df = price_df.sort_values(['stock_id', 'date']).rename(columns={'date': 'trade_date'})
    return price_df

price_df = load_price_data(token)

if price_df.empty:
    st.stop()

# ────────────────────────────────────────────────
# RS 計算函式
# ────────────────────────────────────────────────
def calc_rs(df):
    if df.empty:
        return pd.DataFrame(columns=["stock_id", "RS", "r3", "r6", "r9", "r12"])

    df = df.copy()
    df["r3"]  = df.groupby("stock_id")["close"].pct_change(60)
    df["r6"]  = df.groupby("stock_id")["close"].pct_change(120)
    df["r9"]  = df.groupby("stock_id")["close"].pct_change(180)
    df["r12"] = df.groupby("stock_id")["close"].pct_change(240)

    latest = df.dropna(subset=["r3"]).groupby("stock_id").tail(1).copy()

    if latest.empty:
        st.warning("沒有足夠資料計算 RS（至少需 60 交易日）")
        return pd.DataFrame(columns=["stock_id", "RS", "r3", "r6", "r9", "r12"])

    for col in ["r6", "r9", "r12"]:
        latest[col] = latest[col].fillna(0)

    latest["rs_raw"] = latest["r3"] * 2 + latest["r6"] + latest["r9"] + latest["r12"]
    latest["RS"] = latest["rs_raw"].rank(pct=True) * 100
    latest = latest.sort_values("RS", ascending=False)

    return latest[["stock_id", "RS", "r3", "r6", "r9", "r12"]]

rs_df = calc_rs(price_df)

# ────────────────────────────────────────────────
# 主畫面
# ────────────────────────────────────────────────
st.title("📈 台股 RS 強勢股排名（FinMind 版）")

col_left, col_right = st.columns([3, 1])

with col_right:
    top_n = st.slider("顯示前 N 名", 10, 300, 50)
    rs_min = st.slider("最低 RS 門檻", 0, 100, 70)

filtered = rs_df[rs_df["RS"] >= rs_min].head(top_n)

with col_left:
    st.subheader("🏆 RS 強勢股排名")

    if filtered.empty:
        st.info("目前沒有符合條件的股票")
    else:
        disp = filtered.copy()
        for c in ["r3", "r6", "r9", "r12"]:
            disp[c] = disp[c].map(lambda x: f"{x:.2%}" if pd.notna(x) else "-")
        disp["RS"] = disp["RS"].round(1)

        # 簡單樣式（無 matplotlib 依賴）
        def highlight_rs(val):
            color = '#d4edda' if val >= 90 else '#fff3cd' if val >= 70 else 'white'
            return f'background-color: {color}'

        styled = disp.style.applymap(highlight_rs, subset=['RS'])

        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True
        )

# ────────────────────────────────────────────────
# 個股走勢
# ────────────────────────────────────────────────
st.markdown("---")
st.subheader("📊 個股走勢檢視")

stock_options = ["-- 請選擇股票 --"] + rs_df["stock_id"].tolist()
selected_stock = st.selectbox("選擇股票代碼", stock_options)

if selected_stock != "-- 請選擇股票 --":
    stock_data = price_df[price_df["stock_id"] == selected_stock]
    if not stock_data.empty:
        st.line_chart(stock_data.set_index("trade_date")["close"])
    else:
        st.warning(f"暫無 {selected_stock} 的價格資料")

# ────────────────────────────────────────────────
# 除錯資訊
# ────────────────────────────────────────────────
with st.expander("🔧 資料狀態"):
    st.write(f"總資料筆數：{len(price_df):,}")
    st.write(f"獨立股票數：{price_df['stock_id'].nunique()}")
    st.write(f"日期範圍：{price_df['trade_date'].min().date()} ～ {price_df['trade_date'].max().date()}")
    st.write(f"RS 最高分：{rs_df['RS'].max():.1f}")
