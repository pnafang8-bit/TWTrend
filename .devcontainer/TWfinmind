import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
from FinMind.data import DataLoader

st.set_page_config(page_title="台股 RS 強勢股排名 - FinMind", layout="wide")

# =========================
# 1. FinMind Token 設定
# =========================
st.sidebar.title("⚙️ FinMind 設定")
token = st.sidebar.text_input(
    "輸入 FinMind Token（免費註冊取得）",
    type="password",
    help="https://finmindtrade.com/analysis/#/account/register"
)

if token:
    st.sidebar.success("✅ Token 已設定")
else:
    st.sidebar.warning("⚠️ 未輸入 Token → 免費額度較低（每小時 300 次）")

# =========================
# 2. 取得所有台股清單
# =========================
@st.cache_data(ttl=86400 * 7)  # 每週更新一次
def get_all_stocks(_dl):
    try:
        df = _dl.taiwan_stock_info()
        # 過濾上市 + 上櫃 + ETF（股票代碼為 4 位數或 0050 系列）
        df = df[df['stock_id'].str.match(r'^\d{4}$|^\d{4}\.TW$|00\d{2}')]
        return df.sort_values('stock_id')
    except:
        # 備用熱門清單
        return pd.DataFrame({
            'stock_id': ['2330','2317','2454','2308','2412','0050','006208','2303','2881','2882']
        })

# =========================
# 3. 載入價格資料（FinMind）
# =========================
@st.cache_data(ttl=86400, show_spinner="從 FinMind 抓取台股歷史資料...")
def load_price_data(token_input):
    dl = DataLoader(token=token_input) if token_input else DataLoader()

    # 取得股票清單
    stock_info = get_all_stocks(dl)
    all_stock_ids = stock_info['stock_id'].tolist()

    # 使用者可選擇要載入多少檔（避免一次抓太多）
    max_stocks = st.sidebar.slider("載入股票數量（建議 100~300）", 50, 500, 200)

    stock_list = all_stock_ids[:max_stocks]

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=1000)).strftime("%Y-%m-%d")  # 約 2.7 年

    data_list = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, stock_id in enumerate(stock_list):
        try:
            df = dl.taiwan_stock_daily(
                stock_id=stock_id,
                start_date=start_date,
                end_date=end_date
            )
            if not df.empty:
                df = df[['date', 'stock_id', 'close']].copy()
                df['date'] = pd.to_datetime(df['date'])
                data_list.append(df)
        except Exception as e:
            pass  # 跳過錯誤股票

        progress_bar.progress((i + 1) / len(stock_list))
        status_text.text(f"已處理 {i+1}/{len(stock_list)} 檔 → {stock_id}")

        time.sleep(0.25)  # 避免超過速率限制

    if not data_list:
        st.error("無法取得資料，請確認 Token 是否正確或稍後再試。")
        return pd.DataFrame()

    price_df = pd.concat(data_list, ignore_index=True)
    price_df = price_df.sort_values(['stock_id', 'date']).rename(columns={'date': 'trade_date'})
    return price_df

price_df = load_price_data(token)

if price_df.empty:
    st.stop()

# =========================
# 4. RS 計算
# =========================
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
        st.warning("資料不足，無法計算 RS")
        return pd.DataFrame(columns=["stock_id", "RS", "r3", "r6", "r9", "r12"])

    for col in ["r6", "r9", "r12"]:
        latest[col] = latest[col].fillna(0)

    latest["rs_raw"] = latest["r3"] * 2 + latest["r6"] + latest["r9"] + latest["r12"]
    latest["RS"] = latest["rs_raw"].rank(pct=True) * 100
    latest = latest.sort_values("RS", ascending=False)

    return latest[["stock_id", "RS", "r3", "r6", "r9", "r12"]]

rs_df = calc_rs(price_df)

# =========================
# 5. 顯示介面
# =========================
st.title("📈 台股 RS 強勢股排名 Dashboard（FinMind 版）")

col1, col2 = st.columns([3, 1])

with col2:
    top_n = st.slider("顯示前 N 名", 10, 300, 50)
    rs_filter = st.slider("最低 RS 篩選", 0, 100, 70)

filtered = rs_df[rs_df["RS"] >= rs_filter].head(top_n)

with col1:
    st.subheader("🏆 RS 強勢股排名")
    if filtered.empty:
        st.info("目前沒有符合條件的股票")
    else:
        display = filtered.copy()
        for c in ["r3", "r6", "r9", "r12"]:
            display[c] = display[c].map(lambda x: f"{x:.2%}" if pd.notna(x) else "-")
        display["RS"] = display["RS"].round(1)

        st.dataframe(
            display.style
                .background_gradient(subset=["RS"], cmap="YlGn")
                .highlight_max(subset=["RS"], color="#d4edda"),
            use_container_width=True,
            hide_index=True
        )

st.markdown("---")
st.subheader("📊 個股趨勢檢視")
stock_list = ["-- 請選擇股票 --"] + rs_df["stock_id"].tolist()
selected = st.selectbox("選擇股票", stock_list)

if selected != "-- 請選擇股票 --":
    stock_df = price_df[price_df["stock_id"] == selected]
    st.line_chart(stock_df.set_index("trade_date")["close"])

with st.expander("🔧 資料狀態"):
    st.write(f"總資料筆數：{len(price_df):,}")
    st.write(f"股票數量：{price_df['stock_id'].nunique()}")
    st.write(f"日期範圍：{price_df['trade_date'].min().date()} ～ {price_df['trade_date'].max().date()}")
    st.write(f"RS 最高：{rs_df['RS'].max():.1f}")
