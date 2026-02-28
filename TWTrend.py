import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import socket
import datetime

# 1. 強制 IPv4 補丁 (這是解決 Streamlit Cloud 無法連線至 Supabase 的核心關鍵)
_orig = socket.getaddrinfo
def _v4(h, p, f=0, t=0, pr=0, fl=0):
    return _orig(h, p, socket.AF_INET, t, pr, fl)
socket.getaddrinfo = _v4

# 2. 頁面設定
st.set_page_config(layout="wide", page_title="TWTrend Pro RS Dashboard")

# 3. 資料庫連線字串 (使用 pg8000 驅動 + 官方直連位址)
# 帳號: postgres / 密碼: Twtrend9988 / Port: 5432
DB_STR = "postgresql+pg8000://postgres:Twtrend9988@db.zuwlrboozuwdkfevlces.supabase.co:5432/postgres"

@st.cache_resource
def get_engine():
    try:
        # pg8000 在 SSL 連線時使用 ssl_context=True
        engine = create_engine(
            DB_STR,
            connect_args={"ssl_context": True},
            pool_pre_ping=True,
            pool_recycle=300
        )
        return engine
    except Exception as e:
        st.error(f"❌ 資料庫引擎初始化失敗: {str(e)}")
        return None

engine = get_engine()

# ==============================
# 4. 資料讀取函數
# ==============================
@st.cache_data(ttl=600)
def load_price_data():
    # 讀取最近 15 個月的股價資料
    q = "SELECT stock_id, trade_date, close FROM daily_price WHERE trade_date > CURRENT_DATE - INTERVAL '15 months' ORDER BY stock_id, trade_date"
    try:
        if engine is None: return pd.DataFrame()
        with engine.connect() as conn:
            df = pd.read_sql(q, conn)
        
        if df.empty:
            st.warning("⚠️ 連線成功，但 daily_price 表中目前無資料。")
            return pd.DataFrame()
        
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df
    except Exception as e:
        st.error(f"❌ 讀取失敗: {str(e)}")
        return pd.DataFrame()

# ==============================
# 5. RS 計算邏輯 (歐尼爾加權公式)
# ==============================
def calculate_rs_score(price_df):
    results = []
    for stock_id, group in price_df.groupby("stock_id"):
        group = group.sort_values("trade_date")
        # 需至少有一年 (約 240 交易日) 的資料才能計算準確 RS
        if len(group) < 240:
            continue
        
        curr_p = group.iloc[-1]["close"]
        # 加權比例：3個月*2 + 6個月 + 9個月 + 12個月
        r3  = curr_p / group.iloc[-60]["close"]
        r6  = curr_p / group.iloc[-120]["close"]
        r9  = curr_p / group.iloc[-180]["close"]
        r12 = curr_p / group.iloc[0]["close"]
        w = (r3 * 2) + r6 + r9 + r12
        
        results.append({
            "Stock": stock_id, 
            "Price": round(curr_p, 2), 
            "Weighted_Ret": w
        })
        
    rs_df = pd.DataFrame(results)
    if not rs_df.empty:
        # 計算百分位排名 (1-100)
        rs_df["RS Score"] = (rs_df["Weighted_Ret"].rank(pct=True) * 100).astype(int)
    return rs_df

# ==============================
# 6. 主介面執行區
# ==============================
st.title("📈 TWTrend Pro | RS 強勢股雷達")

if engine:
    with st.spinner("🚀 正在穿透雲端通道讀取數據..."):
        df_p = load_price_data()
        
        if not df_p.empty:
            rs_results = calculate_rs_score(df_p)
            
            if not rs_results.empty:
                # 簡單指標卡
                col1, col2 = st.columns(2)
                col1.metric("總監控檔數", f"{len(rs_results)} 檔")
                col2.metric("RS > 90 強勢股", f"{len(rs_results[rs_results['RS Score'] >= 90])} 檔")
                
                # 顯示表格
                st.subheader("🔥 全市場 RS 強勢排名 (TOP 250)")
                # 只顯示需要的欄位並排序
                display_df = rs_results[["Stock", "Price", "RS Score"]].sort_values("RS Score", ascending=False)
                st.dataframe(display_df.head(250), use_container_width=True)
            else:
                st.warning("⚠️ 資料不足以計算 RS 分數（需至少一年歷史數據）。")
        else:
            st.info("💡 請確認您的資料庫中 daily_price 資料表是否有數據。")
else:
    st.error("❌ 無法建立資料庫連線，請檢查密碼與主機位址。")

# 頁尾
st.divider()
st.caption(f"最後同步時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
