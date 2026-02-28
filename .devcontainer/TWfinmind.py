import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
from FinMind.data import DataLoader

st.set_page_config(page_title="台股 RS + 趨勢模板八點準則", layout="wide")

# ────────────────────────────────────────────────
# Sidebar 設定
# ────────────────────────────────────────────────
st.sidebar.title("⚙️ 設定")
token = st.sidebar.text_input("FinMind API Token", type="password",
                             help="免費註冊：https://finmindtrade.com/analysis/#/account/register")

max_load = st.sidebar.slider("載入股票數量（建議 100~300）", 50, 500, 200)
top_n_default = st.sidebar.slider("預設顯示前 N 名", 10, 100, 50)
min_score = st.sidebar.slider("最低總得分門檻（滿分8）", 0, 8, 5)

if token:
    st.sidebar.success("Token 已設定")
else:
    st.sidebar.warning("未輸入 Token → 使用免費額度")

# ────────────────────────────────────────────────
# 取得台股清單
# ────────────────────────────────────────────────
@st.cache_data(ttl=86400 * 7)
def get_all_stocks(_dl):
    try:
        df = _dl.taiwan_stock_info()
        df = df[df['stock_id'].str.match(r'^\d{4}$|^00\d{2}$')]
        return df.sort_values('stock_id')
    except:
        return pd.DataFrame({'stock_id': ['2330','2317','2454','2308','2412','0050','006208']})

# ────────────────────────────────────────────────
# 載入股價資料（含成交量）
# ────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner="從 FinMind 載入資料...")
def load_price_data(token_input):
    dl = DataLoader(token=token_input) if token_input else DataLoader()

    stock_info = get_all_stocks(dl)
    all_ids = stock_info['stock_id'].tolist()
    stock_list = all_ids[:max_load]

    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=1000)).strftime("%Y-%m-%d")

    data_list = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, sid in enumerate(stock_list):
        try:
            df = dl.taiwan_stock_daily(stock_id=sid, start_date=start_date, end_date=end_date)
            if not df.empty:
                df = df[['date', 'stock_id', 'close', 'Trading_Volume']].copy()
                df['date'] = pd.to_datetime(df['date'])
                data_list.append(df)
        except:
            pass

        progress_bar.progress((i + 1) / len(stock_list))
        status_text.text(f"處理 {i+1}/{len(stock_list)} → {sid}")
        time.sleep(0.3)

    if not data_list:
        st.error("無法取得資料，請檢查 Token 或網路")
        return pd.DataFrame()

    price_df = pd.concat(data_list, ignore_index=True)
    price_df = price_df.sort_values(['stock_id', 'date']).rename(columns={'date': 'trade_date', 'Trading_Volume': 'volume'})
    return price_df

price_df = load_price_data(token)

if price_df.empty:
    st.stop()

# ────────────────────────────────────────────────
# 計算 RS + 趨勢模板八點 + 總得分
# ────────────────────────────────────────────────
def calc_rs_and_trend_template(df):
    if df.empty:
        return pd.DataFrame()

    df = df.copy()

    # 計算移動平均線
    df['ma50']  = df.groupby('stock_id')['close'].rolling(50).mean().reset_index(0, drop=True)
    df['ma150'] = df.groupby('stock_id')['close'].rolling(150).mean().reset_index(0, drop=True)
    df['ma200'] = df.groupby('stock_id')['close'].rolling(200).mean().reset_index(0, drop=True)

    # 計算 RS（簡化版：近240日漲幅排名）
    df["r3"]  = df.groupby("stock_id")["close"].pct_change(60)
    df["r6"]  = df.groupby("stock_id")["close"].pct_change(120)
    df["r9"]  = df.groupby("stock_id")["close"].pct_change(180)
    df["r12"] = df.groupby("stock_id")["close"].pct_change(240)

    latest = df.dropna(subset=["r3", "ma50", "ma150", "ma200"]).groupby("stock_id").tail(1).copy()

    if latest.empty:
        st.warning("資料不足，無法計算")
        return pd.DataFrame()

    for col in ["r6", "r9", "r12"]:
        latest[col] = latest[col].fillna(0)

    latest["rs_raw"] = latest["r3"] * 2 + latest["r6"] + latest["r9"] + latest["r12"]
    latest["RS"] = latest["rs_raw"].rank(pct=True) * 100
    latest = latest.sort_values("RS", ascending=False)

    # ── 趨勢模板八點準則 ──
    def check_trend_template(row):
        checks = []

        # 1. 股價 > 150日 & 200日均線
        checks.append(row['close'] > row['ma150'] and row['close'] > row['ma200'])

        # 2. 150日均線 > 200日均線
        checks.append(row['ma150'] > row['ma200'])

        # 3. 200日均線上升（最近一個月 ma200 > 前值）
        ma200_series = df[df['stock_id'] == row['stock_id']]['ma200'].tail(20)
        checks.append(ma200_series.is_monotonic_increasing if len(ma200_series) >= 10 else False)

        # 4. 股價距離200日均線 ≤ 25%
        dist_200 = (row['close'] - row['ma200']) / row['ma200']
        checks.append(dist_200 <= 0.25)

        # 5. 股價接近52週新高（距離 ≤ 15%）
        high_52w = df[df['stock_id'] == row['stock_id']]['close'].tail(252).max()
        checks.append(row['close'] >= high_52w * 0.85)

        # 6. RS ≥ 70
        checks.append(row['RS'] >= 70)

        # 7. 股價 > 50日均線
        checks.append(row['close'] > row['ma50'])

        # 8. 成交量放大（近20日平均量 > 前20日平均量）
        recent_vol = df[df['stock_id'] == row['stock_id']]['volume'].tail(20).mean()
        prior_vol = df[df['stock_id'] == row['stock_id']]['volume'].tail(40).head(20).mean()
        checks.append(recent_vol > prior_vol * 1.1 if not np.isnan(prior_vol) else False)

        # 計算總分 & 綠勾/紅X
        score = sum(checks)
        marks = ['✓' if c else '✗' for c in checks]
        return score, marks

    results = latest.apply(check_trend_template, axis=1, result_type='expand')
    latest['total_score'], latest['checks'] = results[0], results[1]

    # 展開八點檢查為欄位
    for i in range(8):
        latest[f'item_{i+1}'] = latest['checks'].apply(lambda x: x[i])

    latest = latest.sort_values(['total_score', 'RS'], ascending=False)

    return latest

rs_df = calc_rs_and_trend_template(price_df)

# ────────────────────────────────────────────────
# 主畫面顯示
# ────────────────────────────────────────────────
st.title("台股 RS + 趨勢模板八點準則篩選")

col_left, col_right = st.columns([4, 1])

with col_right:
    top_n = st.slider("顯示前 N 名", 10, 300, top_n_default)
    min_score_filter = st.slider("最低總得分", 0, 8, min_score)

filtered = rs_df[rs_df["total_score"] >= min_score_filter].head(top_n)

with col_left:
    st.subheader(f"強勢股排名（總得分 ≥ {min_score_filter}，滿分8分）")

    if filtered.empty:
        st.info("目前沒有符合條件的股票")
    else:
        disp = filtered[['stock_id', 'RS', 'r3', 'total_score', 'item_1', 'item_2', 'item_3', 'item_4',
                         'item_5', 'item_6', 'item_7', 'item_8']].copy()

        disp['RS'] = disp['RS'].round(1)
        disp['r3'] = disp['r3'].map(lambda x: f"{x:.2%}" if pd.notna(x) else "-")

        # 綠勾紅X 顏色
        def color_check(val):
            if val == '✓':
                return 'color: green; font-weight: bold'
            elif val == '✗':
                return 'color: red; font-weight: bold'
            return ''

        styled = disp.style.applymap(color_check, subset=[f'item_{i}' for i in range(1,9)])

        st.dataframe(
            styled,
            column_config={
                'stock_id': '股票代碼',
                'RS': 'RS分數',
                'r3': '3月漲幅',
                'total_score': st.column_config.NumberColumn('總得分', format="%d"),
                'item_1': '1. 股價 > 150/200 MA',
                'item_2': '2. 150MA > 200MA',
                'item_3': '3. 200MA 上升',
                'item_4': '4. 距200MA ≤25%',
                'item_5': '5. 接近52週高',
                'item_6': '6. RS ≥70',
                'item_7': '7. 股價 > 50MA',
                'item_8': '8. 量能放大',
            },
            hide_index=True,
            use_container_width=True
        )

# ────────────────────────────────────────────────
# 個股走勢
# ────────────────────────────────────────────────
st.markdown("---")
st.subheader("個股走勢檢視")
selected = st.selectbox("選擇股票", ["-- 請選擇 --"] + rs_df["stock_id"].tolist())

if selected != "-- 請選擇 --":
    stock_data = price_df[price_df["stock_id"] == selected]
    if not stock_data.empty:
        st.line_chart(stock_data.set_index("trade_date")["close"])

with st.expander("資料狀態"):
    st.write(f"總資料筆數：{len(price_df):,}")
    st.write(f"股票數：{price_df['stock_id'].nunique()}")
    st.write(f"總得分分佈：")
    st.write(rs_df["total_score"].value_counts().sort_index(ascending=False))
