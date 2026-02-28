import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import socket

# 1. 強制 IPv4 補丁
_orig = socket.getaddrinfo
def _v4(h, p, f=0, t=0, pr=0, fl=0):
    return _orig(h, p, socket.AF_INET, t, pr, fl)
socket.getaddrinfo = _v4

st.set_page_config(layout="wide", page_title="TWTrend Pro")

# ====== 2. 修正後的連線設定 (精確對位 Supabase Pooler) ======
DB_URL = URL.create(
    drivername="postgresql",
    username="postgres.zuwlrboozuwdkfevlces", # <--- 確認這裡是 postgres.[ProjectID]
    password="Twtrend@9988", 
    host="aws-0-ap-northeast-1.pooler.supabase.com",
    port=6543,
    database="postgres"
)

@st.cache_resource
def get_engine():
    try:
        engine = create_engine(
            DB_URL, 
            connect_args={
                "sslmode": "require", 
                "connect_timeout": 20,
                "application_name": "st_dashboard" # 加入應用名稱有助於 Pooler 識別
            },
            pool_pre_ping=True
        )
        return engine
    except Exception as e:
        st.error(f"❌ 引擎初始化失敗: {str(e)}")
        return None

engine = get_engine()

# --- 測試讀取 ---
@st.cache_data(ttl=600)
def load_price_data():
    # 這裡我們換一個更穩定的方式測試連線
    q = "SELECT stock_id, trade_date, close FROM daily_price WHERE trade_date > CURRENT_DATE - INTERVAL '15 months' ORDER BY stock_id, trade_date"
    try:
        if engine is None: return pd.DataFrame()
        # 使用原生連線執行
        with engine.connect() as conn:
            df = pd.read_sql(q, conn)
        return df
    except Exception as e:
        st.error(f"❌ 讀取失敗: {str(e)}")
        # 如果還是 Tenant not found，建議去 Supabase Dashboard 點擊 "Reset Password" 
        # 並確保密碼沒有特殊字元，這是最後的保險。
        return pd.DataFrame()

# ... (後續顯示邏輯同前) ...
st.title("📈 TWTrend Pro | RS 強勢股雷達")
df_p = load_price_data()
if not df_p.empty:
    st.success("✅ 連線成功！已抓取數據。")
    st.dataframe(df_p.head())
