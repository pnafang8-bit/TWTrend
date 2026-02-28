import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

st.set_page_config(page_title="TW RS Trend Dashboard", layout="wide")

# =========================
# 1. Database Connection
# =========================
@st.cache_resource(show_spinner=False)
def get_engine():
    try:
        db_str = st.secrets["DB_STR"]
        engine = create_engine(
            db_str,
            connect_args={"sslmode": "require"},
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        return engine
    except KeyError:
        st.error("❌ Secrets 未設定：請在 Streamlit Cloud → Settings → Secrets 加入 DB_STR")
        st.stop()
    except Exception as e:
        st.error(f"❌ DB Engine 建立失敗: {e}")
        st.stop()

engine = get_engine()

# =========================
# 2. Load Price Data
# =========================
@st.cache_data(ttl=3600, show_spinner=True)
def load_price_data():
    query = """
        SELECT stock_id, trade_date, close
        FROM daily_price
        WHERE trade_date > CURRENT_DATE - INTERVAL '12 months'
        ORDER BY stock_id, trade_date
    """
    try:
        df = pd.read_sql(query, engine)
        if df.empty:
            st.warning("⚠️ 資料庫沒有回傳任何資料")
        return df
    except SQLAlchemyError as e:
        st.error(f"❌ 資料庫查詢錯誤: {e}")
        st.stop()

price_df = load_price_data()

if price_df.empty:
    st.stop()

price_df["trade_date"] = pd.to_datetime(price_df["trade_date"])
price_df = price_df.sort_values(["stock_id", "trade_date"])

# =========================
# 3. RS Calculation (Vectorized)
# =========================
def calc_rs(df: pd.DataFrame):
    df = df.copy()
    df["r3"] = df.groupby("stock_id")["close"].pct_change(60)
    df["r6"] = df.groupby("stock_id")["close"].pct_change(120)
    df["r9"] = df.groupby("stock_id")["close"].pct_change(180)
    df["r12"] = df.groupby("stock_id")["close"].pct_change(240)

    latest = df.dropna().groupby("stock_id").tail(1).copy()

    # O'Neil weighted RS score
    latest["rs_raw"] = (latest["r3"] * 2) + latest["r6"] + latest["r9"] + latest["r12"]

    latest["RS"] = latest["rs_raw"].rank(pct=True) * 100
    latest = latest.sort_values("RS", ascending=False)

    return latest[["stock_id", "RS", "r3", "r6", "r9", "r12"]]

rs_df = calc_rs(price_df)

# =========================
# 4. UI Dashboard
# =========================
st.title("📈 台股 RS 強勢股排名 Dashboard")

col1, col2 = st.columns([2, 1])

with col2:
    top_n = st.slider("顯示前 N 名", 10, 200, 50)
    rs_filter = st.slider("最低 RS 篩選", 0, 100, 70)

filtered = rs_df[rs_df["RS"] >= rs_filter].head(top_n)

with col1:
    st.subheader("🏆 RS 強勢股排名")
    st.dataframe(filtered, use_container_width=True)

# =========================
# 5. Detail View
# =========================
st.markdown("---")
st.subheader("📊 個股趨勢檢視")

stock_list = rs_df["stock_id"].tolist()
selected_stock = st.selectbox("選擇股票", stock_list)

stock_df = price_df[price_df["stock_id"] == selected_stock]

st.line_chart(stock_df.set_index("trade_date")["close"])

# =========================
# 6. Debug Info (Optional)
# =========================
with st.expander("🔧 Debug Info"):
    st.write("資料筆數:", len(price_df))
    st.write("股票數量:", price_df["stock_id"].nunique())
