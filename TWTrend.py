import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine

# ====== Supabase PostgreSQL 連線 ======
DB_URL = "postgresql://postgres:twtrend@db.TWTrend.supabase.co:5432/tw_market"  # Updated with provided password and project ref
try:
    engine = create_engine(DB_URL)
except Exception as e:
    st.error(f"Database connection failed: {str(e)}")
    st.stop()

st.set_page_config(layout="wide", page_title="TWTrend Pro RS Dashboard")
st.title("📈 TWTrend Pro | RS強勢股 + 爆發股雷達")

# ==============================
# 讀取資料
# ==============================
@st.cache_data(ttl=3600)
def load_price_data():
    query = """
    SELECT stock_id, trade_date, close
    FROM daily_price
    ORDER BY stock_id, trade_date
    """
    try:
        df = pd.read_sql(query, engine)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df
    except Exception as e:
        st.error(f"Error loading price data: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_index_data():
    query = """
    SELECT trade_date, close
    FROM tw_index
    ORDER BY trade_date
    """
    try:
        idx = pd.read_sql(query, engine)
        idx["trade_date"] = pd.to_datetime(idx["trade_date"])
        return idx
    except Exception as e:
        st.error(f"Error loading index data: {str(e)}")
        return pd.DataFrame()

# ==============================
# RS 計算
# ==============================
def calculate_rs(price_df, index_df):
    merged = price_df.merge(index_df, on="trade_date", suffixes=("", "_index"))
    merged["stock_ret_252"] = merged.groupby("stock_id")["close"].pct_change(252)
    merged["index_ret_252"] = merged["close_index"].pct_change(252)
    merged["RS"] = (merged["stock_ret_252"] / merged["index_ret_252"]) * 100

    latest = merged.sort_values("trade_date").groupby("stock_id").tail(1)
    latest = latest[["stock_id", "RS", "close"]]
    latest.rename(columns={"stock_id": "Stock", "close": "Price"}, inplace=True)
    latest["RS Score"] = latest["RS"].rank(pct=True) * 100
    return latest.sort_values("RS Score", ascending=False)

# ==============================
# 爆發股技術條件
# ==============================
def detect_explosive(price_df):
    results = []
    for stock, data in price_df.groupby("stock_id"):
        data = data.sort_values("trade_date").copy()
        if len(data) < 200:
            continue

        data["MA50"] = data["close"].rolling(50).mean()
        data["MA150"] = data["close"].rolling(150).mean()
        data["MA200"] = data["close"].rolling(200).mean()

        last = data.iloc[-1]
        cond = (
            last["close"] > last["MA50"] and
            last["MA50"] > last["MA150"] and
            last["MA150"] > last["MA200"]
        )

        results.append({"Stock": stock, "Explosive Setup": cond})
    return pd.DataFrame(results)

# ==============================
# 財報動能
# ==============================
def add_revenue_growth(rs_df):
    query = """
    SELECT stock_id, year_month, revenue
    FROM monthly_revenue
    ORDER BY stock_id, year_month
    """
    try:
        rev = pd.read_sql(query, engine)
    except Exception as e:
        st.error(f"Error loading revenue data: {str(e)}")
        return rs_df
    rev["YoY"] = rev.groupby("stock_id")["revenue"].pct_change(12)
    latest = rev.sort_values("year_month").groupby("stock_id").tail(1)
    latest = latest[["stock_id","YoY"]]

    rs_df = rs_df.merge(latest, left_on="Stock", right_on="stock_id", how="left")
    rs_df["YoY%"] = (rs_df["YoY"]*100).round(2)
    rs_df["Revenue>30%"] = rs_df["YoY"] >= 0.3
    rs_df.drop(columns=["stock_id","YoY"], inplace=True)
    return rs_df

# ==============================
# 法人籌碼
# ==============================
def add_institutional_flow(rs_df):
    query = """
    SELECT stock_id, trade_date, foreign_buy, trust_buy
    FROM institutional_flow
    ORDER BY stock_id, trade_date
    """
    try:
        flow = pd.read_sql(query, engine)
    except Exception as e:
        st.error(f"Error loading institutional flow: {str(e)}")
        return rs_df
    flow["trade_date"] = pd.to_datetime(flow["trade_date"])

    def streak(series):
        s = (series > 0).astype(int)
        return s.groupby((s != s.shift()).cumsum()).cumsum().max()

    res = []
    for stock, data in flow.groupby("stock_id"):
        data = data.tail(5)
        res.append({
            "Stock": stock,
            "Foreign Streak": streak(data["foreign_buy"]),
            "Trust Streak": streak(data["trust_buy"])
        })

    inst = pd.DataFrame(res)
    inst["Inst Buy Sync"] = (inst["Foreign Streak"]>=3) & (inst["Trust Streak"]>=3)

    rs_df = rs_df.merge(inst, on="Stock", how="left")
    return rs_df

# ==============================
# 回測引擎
# ==============================
def backtest(price_df, explosive_df):
    returns = []
    explosive_list = explosive_df[explosive_df["Explosive Setup"]==True]["Stock"]

    for stock in explosive_list:
        data = price_df[price_df["stock_id"]==stock].sort_values("trade_date")
        if len(data) < 21:  # Need at least 21 rows for ~20-day return
            continue
        entry = data.iloc[-21]["close"]  # ~20 days ago
        future = data.iloc[-1]["close"]  # Today
        ret = (future - entry) / entry
        returns.append(ret)

    if not returns:
        return 0,0

    avg_ret = np.mean(returns)
    win_rate = np.mean([r>0 for r in returns])
    return avg_ret, win_rate

# ==============================
# 主流程
# ==============================
price_df = load_price_data()
index_df = load_index_data()

if price_df.empty or index_df.empty:
    st.stop()

rs_df = calculate_rs(price_df, index_df)
explosive_df = detect_explosive(price_df)
rs_df = rs_df.merge(explosive_df, on="Stock", how="left")

rs_df = add_revenue_growth(rs_df)
rs_df = add_institutional_flow(rs_df)

# 最終爆發股條件
final_df = rs_df[
    (rs_df["RS Score"] > 90) &
    (rs_df["Explosive Setup"]) &
    (rs_df["Revenue>30%"]) &
    (rs_df["Inst Buy Sync"])
]

# 回測
avg_ret, win_rate = backtest(price_df, explosive_df)

# ==============================
# 儀表板輸出
# ==============================
col1, col2 = st.columns(2)
col1.metric("爆發股20日平均報酬", f"{avg_ret*100:.2f}%")
col2.metric("策略勝率", f"{win_rate*100:.1f}%")

st.subheader("🔥 RS強勢股排名")
st.dataframe(rs_df.sort_values("RS Score", ascending=False), use_container_width=True)

st.subheader("🚀 最終爆發潛力股（10倍股雷達）")
st.dataframe(final_df, use_container_width=True)
