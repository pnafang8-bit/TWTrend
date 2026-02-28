import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import socket

# 1. 強制 IPv4 補丁
_orig = socket.getaddrinfo
def _v4(h, p, f=0, t=0, pr=0, fl=0):
    return _orig(h, p, socket.AF_INET, t, pr, fl)
socket.getaddrinfo = _v4

st.set_page_config(layout="wide", page_title="TWTrend Pro RS Dashboard")

# ====== 2. 最終連線字串 (使用 Pooler + Transaction Mode) ======
# 格式: postgresql://[USER].[PROJECT_REF]:[PASSWORD]@[POOLER_HOST]:6543/postgres
DB_STR = "postgresql://postgres.zuwlrboozuwdkfevlces:Twtrend@9988@aws-0-ap-northeast-1.pooler.supabase.com:6543/postgres"

@st.cache_resource
def get_engine():
    try:
        # 使用 pool_pre_ping 確保連線在閒置後能自動重連
        engine = create_engine(
            DB_STR, 
            connect_args={"sslmode": "require", "connect_timeout": 20},
            pool_pre_ping=True,
            pool_recycle=300
        )
        return engine
    except Exception as e:
        st.error(f"DB 連線失敗: {str(e)}")
        return None

engine = get_engine()

# ==============================
# 3. 資料讀取函數 (加入更多錯誤檢查)
# ==============================
@st.cache_data(ttl=600) # 縮短快取時間以便測試
def load_price_data():
    q = "SELECT stock_id, trade_date, close FROM daily_price WHERE trade_date > CURRENT_DATE - INTERVAL '15 months' ORDER BY stock_id, trade_date"
    try:
        if engine is None: return pd.DataFrame()
        df = pd.read_sql(q, engine)
        if df.empty:
            st.warning("⚠️ 資料庫連上了，但 daily_price 資料表目前是空的。")
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df
    except Exception as e:
        # 如果這裡噴出 OperationalError，代表連線字串還是連不到
        st.error(f"連線成功但讀取失敗: {str(e)}")
        return pd.DataFrame()

# ... (其餘 calculate_rs_score, apply_filters 函數保持不變) ...

# ==============================
# 4. 主畫面顯示
# ==============================
st.title("📈 TWTrend Pro | RS 強勢股雷達")

if engine:
    with st.spinner("🚀 正在穿透雲端防火牆讀取數據..."):
        df_p = load_price_data()
        if not df_p.empty:
            # 這裡執行後續計算與顯示 (與前一版相同)
            rs_base = calculate_rs_score(df_p)
            if not rs_base.empty:
                full_df = apply_filters(rs_base, df_p)
                # ... 顯示指標與表格 ...
                st.dataframe(full_df.sort_values("RS Score", ascending=False).head(250))
else:
    st.error("❌ 引擎初始化失敗，請檢查 Supabase 帳號密碼與專案狀態。")
