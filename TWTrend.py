import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
import socket

_orig = socket.getaddrinfo
def _v4(h, p, f=0, t=0, pr=0, fl=0):
return _orig(h, p, socket.AF_INET, t, pr, fl)
socket.getaddrinfo = _v4

st.set_page_config(layout=“wide”, page_title=“TWTrend Pro RS Dashboard”)

DB_URL = URL.create(
drivername=“postgresql”,
username=“postgres”,
password=”[Twtrend@9988]”,
host=“db.zuwlrboozuwdkfevlces.supabase.co”,
port=5432,
database=“postgres”
)

@st.cache_resource
def get_engine():
try:
engine = create_engine(DB_URL, connect_args={“sslmode”: “require”})
return engine
except Exception as e:
st.error(f”DB error: {str(e)}”)
return None

engine = get_engine()
if not engine:
st.stop()

@st.cache_data(ttl=3600)
def load_price_data():
q = “SELECT stock_id, trade_date, close FROM daily_price WHERE trade_date > CURRENT_DATE - INTERVAL ‘15 months’ ORDER BY stock_id, trade_date”
try:
df = pd.read_sql(q, engine)
df[“trade_date”] = pd.to_datetime(df[“trade_date”])
return df
except Exception as e:
st.error(f”Price error: {str(e)}”)
return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_index_data():
q = “SELECT trade_date, close FROM tw_index WHERE trade_date > CURRENT_DATE - INTERVAL ‘15 months’ ORDER BY trade_date”
try:
idx = pd.read_sql(q, engine)
idx[“trade_date”] = pd.to_datetime(idx[“trade_date”])
return idx
except Exception as e:
st.error(f”Index error: {str(e)}”)
return pd.DataFrame()

def calculate_rs_score(price_df, index_df):
results = []
for stock_id, group in price_df.groupby(“stock_id”):
group = group.sort_values(“trade_date”)
if len(group) < 240:
continue
curr_p = group.iloc[-1][“close”]
r3  = curr_p / group.iloc[-60][“close”]
r6  = curr_p / group.iloc[-120][“close”]
r9  = curr_p / group.iloc[-180][“close”]
r12 = curr_p / group.iloc[0][“close”]
w = (r3 * 2) + r6 + r9 + r12
results.append({“Stock”: stock_id, “Price”: curr_p, “Weighted_Ret”: w, “High_1Y”: group[“close”].max()})
rs_df = pd.DataFrame(results)
if rs_df.empty:
return rs_df
rs_df[“RS Score”] = (rs_df[“Weighted_Ret”].rank(pct=True) * 100).astype(int)
return rs_df

def apply_filters(rs_df, price_df):
tech = []
for stock_id, group in price_df.groupby(“stock_id”):
if len(group) < 200:
continue
data = group.sort_values(“trade_date”)
ma50  = data[“close”].rolling(50).mean().iloc[-1]
ma150 = data[“close”].rolling(150).mean().iloc[-1]
ma200 = data[“close”].rolling(200).mean().iloc[-1]
ok = bool(data.iloc[-1][“close”] > ma50 > ma150 > ma200)
tech.append({“Stock”: stock_id, “Explosive Setup”: ok})
rs_df = rs_df.merge(pd.DataFrame(tech), on=“Stock”, how=“left”)
try:
rev = pd.read_sql(“SELECT stock_id, revenue, year_month FROM monthly_revenue”, engine)
rev[“YoY”] = rev.groupby(“stock_id”)[“revenue”].pct_change(12)
lr = rev.sort_values(“year_month”).groupby(“stock_id”).tail(1)[[“stock_id”, “YoY”]]
lr.rename(columns={“stock_id”: “Stock”, “YoY”: “Rev_YoY”}, inplace=True)
rs_df = rs_df.merge(lr, on=“Stock”, how=“left”)
except:
rs_df[“Rev_YoY”] = 0
try:
inst = pd.read_sql(“SELECT stock_id, foreign_buy, trust_buy FROM institutional_flow ORDER BY trade_date DESC LIMIT 5000”, engine)
ins = inst.groupby(“stock_id”).head(3).groupby(“stock_id”).sum()
ins[“Inst_Sync”] = (ins[“foreign_buy”] > 0) & (ins[“trust_buy”] > 0)
rs_df = rs_df.merge(ins[[“Inst_Sync”]], left_on=“Stock”, right_index=True, how=“left”)
except:
rs_df[“Inst_Sync”] = False
rs_df[“Explosive Setup”] = rs_df[“Explosive Setup”].fillna(False)
rs_df[“Inst_Sync”] = rs_df[“Inst_Sync”].fillna(False)
rs_df[“Rev_YoY”] = rs_df[“Rev_YoY”].fillna(0.0)
return rs_df

st.title(“TWTrend Pro | RS 強勢股雷達”)

with st.spinner(“正在從雲端計算全市場數據…”):
df_p = load_price_data()
df_i = load_index_data()
if not df_p.empty:
rs_base = calculate_rs_score(df_p, df_i)
full_df = apply_filters(rs_base, df_p)
col1, col2, col3 = st.columns(3)
n = len(full_df[full_df[“RS Score”] >= 90])
col1.metric(“RS > 90 檔數”, f”{n} 檔”)
radar = full_df[
(full_df[“RS Score”] >= 90) &
(full_df[“Explosive Setup”] == True) &
(full_df[“Rev_YoY”] >= 0.3)
].copy()
st.subheader(“10 倍股爆發雷達 (RS > 90 + 財報 + 趨勢)”)
st.dataframe(radar.style.format({“Price”: “{:.2f}”, “Rev_YoY”: “{:.2%}”}), use_container_width=True)
st.subheader(“全市場 RS 強勢排名”)
st.dataframe(full_df.sort_values(“RS Score”, ascending=False), use_container_width=True)
else:
st.warning(“目前資料庫中無足夠資料。”)
