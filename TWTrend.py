import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import socket

# 1. 強制 IPv4 補丁 (解決 Streamlit Cloud 與 Supabase 的連線問題)
_orig = socket.getaddrinfo
def _v4(h, p, f=0, t=0, pr=0, fl=0):
    return _orig(h, p, socket.AF_INET, t, pr, fl)
socket.getaddrinfo = _v4

# 2. 頁面設定
st.set_page_config(layout="wide", page_title="TWTrend Pro RS Dashboard")

# 3. 資料庫連線設定 (針對 Streamlit Cloud 優化)
# 使用 Supabase Connection Pooler (Port 6543)
DB_URL = URL.create(
    drivername="postgresql",
    username="postgres.zuwlrboozuwdkfevlces", # 注意：這裡必須補上專案 ID
    password="Twtrend@9988", 
    host="aws-0-ap-northeast-1.pooler.supabase.com", # 使用 Pooler 主機
    port=6543, 
    database="postgres"
)

@st.cache_resource
def get_engine():
    try:
        # pool_pre_ping 會在每次使用連線前檢查是否斷線
        engine = create_engine(
            DB_URL, 
            connect_args={"sslmode": "require", "connect_timeout": 15},
            pool_pre_ping=True
        )
        return engine
    except Exception as e:
        st.error(f"DB 連線失敗: {str(e)}")
        return None

engine = get_engine()

# ==============================
# 4. 資料讀取函數
# ==============================
@st.cache_data(ttl=3600)
def load_price_data():
    q = "SELECT stock_id, trade_date, close FROM daily_price WHERE trade_date > CURRENT_DATE - INTERVAL '15 months' ORDER BY stock_id, trade_date"
    try:
        df = pd.read_sql(q, engine)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        return df
    except Exception as e:
        st.error(f"價格讀取錯誤: {str(e)}")
        return pd.DataFrame()

# ==============================
# 5. RS 計算與過濾邏輯
# ==============================
def calculate_rs_score(price_df):
    results = []
    for stock_id, group in price_df.groupby("stock_id"):
        group = group.sort_values("trade_date")
        if len(group) < 240: continue
        
        curr_p = group.iloc[-1]["close"]
        # 尼克萊加權公式: (3m*2 + 6m + 9m + 12m)
        r3  = curr_p / group.iloc[-60]["close"]
        r6  = curr_p / group.iloc[-120]["close"]
        r9  = curr_p / group.iloc[-180]["close"]
        r12 = curr_p / group.iloc[0]["close"]
        w = (r3 * 2) + r6 + r9 + r12
        
        results.append({
            "Stock": stock_id, 
            "Price": curr_p, 
            "Weighted_Ret": w, 
            "High_1Y": group["close"].max()
        })
        
    rs_df = pd.DataFrame(results)
    if not rs_df.empty:
        rs_df["RS Score"] = (rs_df["Weighted_Ret"].rank(pct=True) * 100).astype(int)
    return rs_df

def apply_filters(rs_df, price_df):
    tech = []
    for stock_id, group in price_df.groupby("stock_id"):
        if len(group) < 200: continue
        data = group.sort_values("trade_date")
        ma50  = data["close"].rolling(50).mean().iloc[-1]
        ma150 = data["close"].rolling(150).mean().iloc[-1]
        ma200 = data["close"].rolling(200).mean().iloc[-1]
        ok = bool(data.iloc[-1]["close"] > ma50 > ma150 > ma200)
        tech.append({"Stock": stock_id, "Explosive Setup": ok})
    
    if tech:
        rs_df = rs_df.merge(pd.DataFrame(tech), on="Stock", how="left")
    
    try:
        rev = pd.read_sql("SELECT stock_id, revenue, year_month FROM monthly_revenue", engine)
        rev["YoY"] = rev.groupby("stock_id")["revenue"].pct_change(12)
        lr = rev.sort_values("year_month").groupby("stock_id").tail(1)[["stock_id", "YoY"]]
        lr.rename(columns={"stock_id": "Stock", "YoY": "Rev_YoY"}, inplace=True)
        rs_df = rs_df.merge(lr, on="Stock", how="left")
    except:
        rs_df["Rev_YoY"] = 0.0

    try:
        inst = pd.read_sql("SELECT stock_id, foreign_buy, trust_buy FROM institutional_flow ORDER BY trade_date DESC LIMIT 5000", engine)
        ins = inst.groupby("stock_id").head(3).groupby("stock_id").sum()
        ins["Inst_Sync"] = (ins["foreign_buy"] > 0) & (ins["trust_buy"] > 0)
        rs_df = rs_df.merge(ins[["Inst_Sync"]], left_on="Stock", right_index=True, how="left")
    except:
        rs_df["Inst_Sync"] = False

    rs_df["Explosive Setup"] = rs_df["Explosive Setup"].fillna(False)
    rs_df["Inst_Sync"] = rs_df["Inst_Sync"].fillna(False)
    rs_df["Rev_YoY"] = rs_df["Rev_YoY"].fillna(0.0)
    return rs_df

# ==============================
# 6. 主介面顯示 (加入漲紅跌綠樣式)
# ==============================
st.title("📈 TWTrend Pro | RS 強勢股雷達")

if not engine:
    st.stop()

# 顏色輔助函數
def color_yoy(val):
    color = '#ff4b4b' if val >= 0.3 else 'white'
    return f'color: {color}'

with st.spinner("🚀 正在連線至 Supabase 計算數據..."):
    df_p = load_price_data()
    if not df_p.empty:
        rs_base = calculate_rs_score(df_p)
        if not rs_base.empty:
            full_df = apply_filters(rs_base, df_p)
            
            col1, col2, col3 = st.columns(3)
            n = len(full_df[full_df["RS Score"] >= 90])
            col1.metric("RS > 90 檔數", f"{n} 檔")
            col2.metric("法人同步買進", f"{len(full_df[full_df['Inst_Sync']])} 檔")
            col3.metric("趨勢符合模板", f"{len(full_df[full_df['Explosive Setup']])} 檔")
            
            radar = full_df[
                (full_df["RS Score"] >= 90) & 
                (full_df["Explosive Setup"] == True) & 
                (full_df["Rev_YoY"] >= 0.3)
            ].copy()

            st.subheader("🚀 最終爆發潛力股 (RS > 90 + 營收 + 趨勢)")
            st.dataframe(
                radar.style.format({"Price": "{:.2f}", "Rev_YoY": "{:.2%}"})
                .applymap(color_yoy, subset=['Rev_YoY']), 
                use_container_width=True
            )
            
            st.subheader("🔥 全市場 RS 強勢排名 (TOP 250)")
            st.dataframe(
                full_df.sort_values("RS Score", ascending=False).head(250), 
                use_container_width=True
            )
        else:
            st.warning("⚠️ 計算後無符合條件股票，請檢查歷史數據長度。")
    else:
        st.warning("⚠️ 無法讀取資料，請檢查 Supabase 裡的 Table 名稱與權限。")
