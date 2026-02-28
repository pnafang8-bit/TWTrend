import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
from FinMind.data import DataLoader

st.set_page_config(page_title="台股 RS + 趨勢模板八點準則（含中文名稱）", layout="wide")

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
# 取得台股清單（含中文名稱）
# ────────────────────────────────────────────────
@st.cache_data(ttl=86400 * 7)
def get_all_stocks(_dl):
    try:
        df = _dl.taiwan_stock_info()
        # 保留需要的欄位：股票代碼 + 中文名稱 + 產業別（可選）
        df = df[['stock_id', 'stock_name']].drop_duplicates()
        df = df[df['stock_id'].str.match(r'^\d{4}$|^00\d{2}$')]
        return df.sort_values('stock_id')
    except:
        # 備用清單（含中文名稱）
        fallback = [
            {'stock_id': '2330', 'stock_name': '台積電'},
            {'stock_id': '2317', 'stock_name': '鴻海'},
            {'stock_id': '2454', 'stock_name': '聯發科'},
            {'stock_id': '2308', 'stock_name': '台達電'},
            {'stock_id': '2412', 'stock_name': '中華電'},
            {'stock_id': '0050', 'stock_name': '元大台灣50'},
        ]
        return pd.DataFrame(fallback)

# ────────────────────────────────────────────────
# 載入股價資料（含成交量）
# ────────────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner="從 FinMind 載入資料...")
def load_price_data(token_input):
    dl = DataLoader(token=token_input) if token_input else DataLoader()

    stock_info = get_all_stocks(dl)
    stock_list = stock_info['stock_id'].tolist()[:max_load]

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
        return pd.DataFrame(), pd.DataFrame()

    price_df = pd.concat(data_list, ignore_index=True)
    price_df = price_df.sort_values(['stock_id', 'date']).rename(columns={'date': 'trade_date', 'Trading_Volume': 'volume'})

    # 合併中文名稱
    stock_info = stock_info.set_index('stock_id')
    price_df['stock_name'] = price_df['stock_id'].map(stock_info['stock_name'])

    return price_df, stock_info.reset_index()

price_df, stock_info_df = load_price_data(token)

if price_df.empty:
    st.stop()

# ────────────────────────────────────────────────
# 計算 RS + 趨勢模板八點 + 總得分
# ────────────────────────────────────────────────
def calc_rs_and_trend_template(df, stock_info):
    if df.empty:
        return pd.DataFrame()

    df = df.copy()

    # 移動平均線
    df['ma50']  = df.groupby('stock_id')['close'].rolling(50).mean().reset_index(0, drop=True)
    df['ma150'] = df.groupby('stock_id')['close'].rolling(150).mean().reset_index(0, drop=True)
    df['ma200'] = df.groupby('stock_id')['close'].rolling(200).mean().reset_index(0, drop=True)

    # RS 計算
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

    # 合併中文名稱
    latest = latest.merge(stock_info[['stock_id', 'stock_name']], on='stock_id', how='left')

    # 趨勢模板八點
    def check_trend_template(row):
        checks = []

        checks.append(row['close'] > row['ma150'] and row['close'] > row['ma200'])  # 1
        checks.append(row['ma150'] > row['ma200'])  # 2
        ma200_series = df[df['stock_id'] == row['stock_id']]['ma200'].tail(20)
        checks.append(ma200_series.is_monotonic_increasing if len(ma200_series) >= 10 else False)  # 3
        dist_200 = (row['close'] - row['ma200']) / row['ma200']
        checks.append(dist_200 <= 0.25)  # 4
        high_52w = df[df['stock_id'] == row['stock_id']]['close'].tail(252).max()
        checks.append(row['close'] >= high_52w * 0.85)  # 5
        checks.append(row['RS'] >= 70)  # 6
        checks.append(row['close'] > row['ma50'])  # 7
        recent_vol = df[df['stock_id'] == row['stock_id']]['volume'].tail(20).mean()
        prior_vol = df[df['stock_id'] == row['stock_id']]['volume'].tail(40).head(20).mean()
        checks.append(recent_vol > prior_vol * 1.1 if not np.isnan(prior_vol) else False)  # 8

        score = sum(checks)
        marks = ['✓' if c else '✗' for c in checks]
        return score, marks

    results = latest.apply(check_trend_template, axis=1, result_type='expand')
    latest['total_score'], latest['checks'] = results[0], results[1]

    for i in range(8):
        latest[f'item_{i+1}'] = latest['checks'].apply(lambda x: x[i])

    latest = latest.sort_values(['total_score', 'RS'], ascending=False)

    return latest

rs_df = calc_rs_and_trend_template(price_df, stock_info_df)

# ────────────────────────────────────────────────
# 主畫面顯示
# ────────────────────────────────────────────────
st.title("台股 RS + 趨勢模板八點準則（含中文名稱）")

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
        disp = filtered[['stock_id', 'stock_name', 'RS', 'r3', 'total_score',
                         'item_1', 'item_2', 'item_3', 'item_4',
                         'item_5', 'item_6', 'item_7', 'item_8']].copy()

        disp['RS'] = disp['RS'].round(1)
        disp['r3'] = disp['r3'].map(lambda x: f"{x:.2%}" if pd.notna(x) else "-")
        disp['股票'] = disp['stock_id'] + ' ' + disp['stock_name'].fillna('未知')

        # 綠勾紅叉顏色
        def color_check(val):
            if val == '✓':
                return 'color: green; font-weight: bold'
            elif val == '✗':
                return 'color: red; font-weight: bold'
            return ''

        styled = disp.style.applymap(color_check, subset=[f'item_{i}' for i in range(1,9)])

        st.dataframe(
            styled[['股票', 'RS', 'r3', 'total_score', 'item_1', 'item_2', 'item_3', 'item_4',
                    'item_5', 'item_6', 'item_7', 'item_8']],
            column_config={
                '股票': st.column_config.TextColumn("股票（代碼 + 名稱）", width="medium"),
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
selected = st.selectbox("選擇股票", ["-- 請選擇 --"] + (rs_df["stock_id"] + " " + rs_df["stock_name"].fillna('')).tolist())

if selected != "-- 請選擇 --":
    sid = selected.split()[0]
    stock_data = price_df[price_df["stock_id"] == sid]
    if not stock_data.empty:
        st.line_chart(stock_data.set_index("trade_date")["close"])

with st.expander("資料狀態"):
    st.write(f"總資料筆數：{len(price_df):,}")
    st.write(f"股票數：{price_df['stock_id'].nunique()}")
    st.write(f"總得分分佈：")
    st.write(rs_df["total_score"].value_counts().sort_index(ascending=False))
