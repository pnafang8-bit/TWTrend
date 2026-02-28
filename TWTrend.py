import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz

# 時區與頁面設定
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)
st.set_page_config(layout="wide", page_title="TWTrend | 台股繁體中文篩選器")

# 抓取證交所官方繁體中文名稱
@st.cache_data(ttl=86400)
def get_stock_name_tw(ticker):
    try:
        t = yf.Ticker(ticker)
        # shortName 通常存放繁體中文簡稱 (如: 台積電)
        name = t.info.get('shortName')
        
        # 如果抓到的是空值或是英文，嘗試抓取 longName
        if not name or name.isascii():
            name = t.info.get('longName')
            
        # 若還是找不到或依然是英文，則回傳代號本身
        return name if name else ticker
    except:
        return ticker

@st.cache_data(ttl=3600)
def fetch_bulk_data(tickers, days=750):
    df = yf.download(tickers, start=(now_tw - timedelta(days=days)).strftime('%Y-%m-%d'), auto_adjust=True)
    return df

def analyze_stock(ticker, full_df, market_close):
    try:
        if isinstance(full_df.columns, pd.MultiIndex):
            stock_df = full_df.xs(ticker, axis=1, level=1).dropna()
        else:
            stock_df = full_df.dropna()
            
        if len(stock_df) < 250: return None
        
        close_s = stock_df['Close']
        high_s = stock_df['High']
        low_s = stock_df['Low']
        
        # 指標計算 (MA)
        ma50 = ta.sma(close_s, length=50)
        ma150 = ta.sma(close_s, length=150)
        ma200 = ta.sma(close_s, length=200)
        
        # RS 相對強度數值 (數值越高代表比大盤強越多)
        # 公式: RS = (個股現價 / 個股一年前價) / (大盤現價 / 大盤一年前價) * 100
        stock_perf = close_s.iloc[-1] / close_s.iloc[-252]
        mkt_perf = market_close.iloc[-1] / market_close.iloc[-252]
        rs_value = round((stock_perf / mkt_perf) * 100, 2)
        
        # 短期 RS 趨勢 (用於 C8 條件判斷)
        rs_line = (close_s / market_close.loc[stock_df.index]) * 100
        
        last_p = float(close_s.iloc[-1])
        m50 = float(ma50.iloc[-1])
        m150 = float(ma150.iloc[-1])
        m200 = float(ma200.iloc[-1])
        m200_prev = float(ma200.iloc[-22]) # 約一個月前
        rs_now = float(rs_line.iloc[-1])
        rs_prev = float(rs_line.iloc[-22])
        curr_h52 = float(high_s.rolling(window=252).max().iloc[-1])
        curr_l52 = float(low_s.rolling(window=252).min().iloc[-1])

        # 8 項強勢股條件
        cond = [
            last_p > m150 and last_p > m200,          # C1
            m150 > m200,                               # C2
            m200 > m200_prev,                          # C3
            m50 > m150 and m50 > m200,                 # C4
            last_p > m50,                              # C5
            last_p >= (curr_l52 * 1.30),               # C6
            last_p >= (curr_h52 * 0.75),               # C7
            rs_now > rs_prev                           # C8
        ]
        
        score = sum(cond)
        if score == 0: return None # 排除 0 分股票

        return {
            "總得分": score,
            "代號": ticker,
            "股票名稱": get_stock_name_tw(ticker),
            "收盤價": round(last_p, 2),
            "RS相對強度": rs_value,
            "C1:價>長均": "✅" if cond[0] else "❌",
            "C2:長均多排": "✅" if cond[1] else "❌",
            "C3:200MA↑": "✅" if cond[2] else "❌",
            "C4:均線全多排": "✅" if cond[3] else "❌",
            "C5:價>50MA": "✅" if cond[4] else "❌",
            "C6:底反彈30%": "✅" if cond[5] else "❌",
            "C7:近高25%": "✅" if cond[6] else "❌",
            "C8:RS上升": "✅" if cond[7] else "❌"
        }
    except:
        return None

# --- 表格樣式設定 ---
def color_rules(val):
    if val == '✅': return 'color: #EB3323; font-weight: bold'
    if val == '❌': return 'color: #999999'
    return ''

def score_highlight(val):
    if isinstance(val, int):
        if val >= 7: return 'background-color: #FFCDD2; color: #B71C1C; font-weight: bold'
        if val >= 5: return 'background-color: #FFF9C4; color: #F57F17'
    return ''

# --- UI 介面 ---
st.title("📊 TWTrend 台股強勢排行榜 (繁體中文版)")
st.sidebar.header("搜尋設定")

# 預設熱門觀察名單
default_list = "2330.TW, 2317.TW, 2454.TW, 2603.TW, 2382.TW, 3231.TW, 1513.TW, 1519.TW, 3017.TW, 6235.TW, 3324.TW, 3548.TW"
input_str = st.sidebar.text_area("輸入台股代碼 (需含 .TW 或 .TWO)", default_list)
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("開始掃描分析"):
    try:
        with st.spinner('正在從證交所獲取繁體中文名稱與計算 RS 值...'):
            # 大盤數據 (加權指數)
            m_df = yf.download("^TWII", start=(now_tw - timedelta(days=750)).strftime('%Y-%m-%d'), auto_adjust=True)
            m_close = m_df['Close'].squeeze()
            
            # 個股數據
            all_data = fetch_bulk_data(input_str)
            
            final_list = []
            for ticker in ticker_list:
                res = analyze_stock(ticker, all_data, m_close)
                if res: final_list.append(res)
            
            if not final_list:
                st.warning("⚠️ 掃描完成。所選股票目前無任何一項符合趨勢模板 (得分全為 0)。")
            else:
                df = pd.DataFrame(final_list)
                
                # 排序: 總得分 (8->1) -> RS 相對強度 (大->小)
                df = df.sort_values(by=["總得分", "RS相對強度"], ascending=[False, False])
                
                st.success(f"✅ 掃描完成！已過濾掉 0 分股票，共顯示 {len(df)} 檔繁體中文名單。")
                
                # 套用樣式 (不依賴 matplotlib)
                styled_df = df.style.map(color_rules).map(score_highlight, subset=['總得分'])
                
                st.dataframe(styled_df, use_container_width=True, height=600)
                
                # 下載按鈕
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("匯出 Excel (CSV)", csv, f"TrendScan_{now_tw.strftime('%Y%m%d')}.csv", "text/csv")

    except Exception as e:
        st.error(f"系統錯誤：{e}")

with st.expander("📌 指標說明與公式"):
    st.markdown("""
    - **股票名稱**: 強制顯示台灣證券交易所定義之 **繁體中文** 簡稱。
    - **RS 相對強度 (數值)**: 
      $$RS = \\frac{Price_{Now} / Price_{1Y}}{Market_{Now} / Market_{1Y}} \\times 100$$
      數值越高代表動能越強，優於大盤。
    - **排除得分為 0**: 根據 Minervini 模板，若一項條件都不符合，代表處於空頭或盤整，自動隱藏以精簡名單。
    - **排序邏輯**: 先看 **總得分**，得分相同時比 **RS 相對強度**。
    """)
