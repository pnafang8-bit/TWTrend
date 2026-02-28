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
@st.cache_data(ttl=86400, show_spinner=True)  # 1 day cache - daily data doesn't change often
def load_price_data():
    query = """
        SELECT stock_id, trade_date, close
        FROM daily_price
        WHERE trade_date > CURRENT_DATE - INTERVAL '30 months'
        ORDER BY stock_id, trade_date
    """
    try:
        df = pd.read_sql(query, engine)
        if df.empty:
            st.warning("⚠️ 資料庫沒有回傳任何資料")
            return pd.DataFrame()
        return df
    except SQLAlchemyError as e:
        st.error(f"❌ 資料庫查詢錯誤: {e}")
        st.stop()

price_df = load_price_data()

if price_df.empty:
    st.error("無法載入價格資料，請檢查資料庫連線或資料是否存在。")
    st.stop()

price_df["trade_date"] = pd.to_datetime(price_df["trade_date"])
price_df = price_df.sort_values(["stock_id", "trade_date"])

# =========================
# 3. RS Calculation (Vectorized + Robust)
# =========================
def calc_rs(df: pd.DataFrame):
    if df.empty:
        st.warning("沒有價格資料可供計算 RS。")
        return pd.DataFrame(columns=["stock_id", "RS", "r3", "r6", "r9", "r12"])

    df = df.copy()
    df["r3"]  = df.groupby("stock_id")["close"].pct_change(60)
    df["r6"]  = df.groupby("stock_id")["close"].pct_change(120)
    df["r9"]  = df.groupby("stock_id")["close"].pct_change(180)
    df["r12"] = df.groupby("stock_id")["close"].pct_change(240)

    # At minimum require r3 (short-term momentum most important)
    valid = df.dropna(subset=["r3"])

    if valid.empty:
        st.warning("沒有任何股票有足夠資料計算至少 3 個月報酬。")
        return pd.DataFrame(columns=["stock_id", "RS", "r3", "r6", "r9", "r12"])

    latest = valid.groupby("stock_id").tail(1).copy()

    # Fill missing longer-term returns conservatively with 0
    for col in ["r6", "r9", "r12"]:
        latest[col] = latest[col].fillna(0)

    latest["rs_raw"] = (latest["r3"] * 2) + latest["r6"] + latest["r9"] + latest["r12"]

    # Only rank if we have valid rs_raw values
    if latest["rs_raw"].dropna().empty:
        st.warning("所有股票的 rs_raw 計算結果皆無效，無法產生排名。")
        return pd.DataFrame(columns=["stock_id", "RS", "r3", "r6", "r9", "r12"])

    latest["RS"] = latest["rs_raw"].rank(pct=True) * 100
    latest = latest.sort_values("RS", ascending=False)

    return latest[["stock_id", "RS", "r3", "r6", "r9", "r12"]]

rs_df = calc_rs(price_df)

# Guard against empty or invalid rs_df
if rs_df.empty or "RS" not in rs_df.columns:
    st.error("無法計算 RS 排名：資料不足或計算過程發生問題。請確認資料庫是否有足夠的歷史價格資料（建議至少 24–30 個月）。")
    st.stop()

# =========================
# 4. UI Dashboard
# =========================
st.title("📈 台股 RS 強勢股排名 Dashboard")

col1, col2 = st.columns([2, 1])

with col2:
    top_n = st.slider("顯示前 N 名", 10, 200, 50)
    rs_filter = st.slider("最低 RS 篩選", 0, 100, 70)

# Filter
filtered = rs_df[rs_df["RS"] >= rs_filter].head(top_n)

with col1:
    st.subheader("🏆 RS 強勢股排名")

    if filtered.empty:
        st.info("目前沒有符合條件的股票（可能 RS 篩選太嚴格或資料不足）。")
    else:
        # Nice display formatting
        display_df = filtered.copy()
        for col in ["r3", "r6", "r9", "r12"]:
            display_df[col] = display_df[col].map(lambda x: f"{x:.2%}" if pd.notna(x) else "-")
        display_df["RS"] = display_df["RS"].round(1)

        st.dataframe(
            display_df.style
                .format(precision=1)
                .background_gradient(subset=["RS"], cmap="YlGn")
                .highlight_max(subset=["RS"], color="#d4edda"),
            use_container_width=True,
            hide_index=True
        )

# =========================
# 5. Detail View
# =========================
st.markdown("---")
st.subheader("📊 個股趨勢檢視")

stock_list = ["-- 請選擇股票 --"] + rs_df["stock_id"].tolist()
selected_stock = st.selectbox("選擇股票", stock_list)

if selected_stock and selected_stock != "-- 請選擇股票 --":
    stock_df = price_df[price_df["stock_id"] == selected_stock]
    if not stock_df.empty:
        st.line_chart(stock_df.set_index("trade_date")["close"])
    else:
        st.warning(f"找不到 {selected_stock} 的價格資料。")

# =========================
# 6. Debug Info
# =========================
with st.expander("🔧 Debug / 資料狀態"):
    st.write("載入的總資料筆數:", len(price_df))
    st.write("獨立股票數量:", price_df["stock_id"].nunique() if not price_df.empty else 0)
    st.write("RS 計算完成股票數:", len(rs_df))
    st.write("RS 最高分:", rs_df["RS"].max() if not rs_df.empty else "N/A")
    st.write("最近交易日範圍:", 
             f"{price_df['trade_date'].min().date()} 至 {price_df['trade_date'].max().date()}"
             if not price_df.empty else "無資料")
