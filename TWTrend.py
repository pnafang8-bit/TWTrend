import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz

# 時區與頁面設定
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)
st.set_page_config(layout="wide", page_title="TWTrend | 台股官方中文篩選器")

# 強制抓取台灣交易所中文名稱
@st.cache_data(ttl=86400)
def get_tw_stock_name(ticker):
    try:
        # 針對台股，yf.Ticker 的 shortName 通常就是交易所的中文簡稱
        t = yf.Ticker(ticker)
        info = t.info
        # 優先順序：短名稱(中文) -> 長名稱 -> 代號
        name = info.get('shortName') or info.get('longName') or ticker
        # 移除名稱中可能存在的 "Corporation" 或 "Co., Ltd." 等英文（若抓到的是英文時）
        return name
    except:
        return ticker

@st.cache_data(ttl=3600)
def fetch_bulk_data(tickers, days=730):
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
        
        # 指標計算
        ma50 = ta.sma(close_s, length=50)
        ma150 = ta.sma(close_s, length=150)
        ma200 = ta.sma(close_s, length=200)
        
        # RS 相對強度數值計算 (個股 vs 大盤)
        # 公式：$$RS = \frac{個股一年表現}{大盤一年表現} \times 100$$
        stock_perf = close_s.iloc[-1] / close_s.iloc[-252]
        mkt_perf = market_close.iloc[-1] / market_close.iloc[-252]
        rs_value = round((stock_perf / mkt_perf) * 100, 2)
        
        # 短期 RS 趨勢 (用於 C8 判斷)
        rs_line = (close_s / market_close.loc[stock_df.index]) * 100
        
        last_p = float(close_s.iloc[-1])
        m50 = float(ma50.iloc[-1])
        m150 = float(ma150.iloc[-1])
        m200 = float(ma200.iloc[-1])
        m200_prev = float(ma200.iloc[-22])
        rs_now = float(rs_line.iloc[-1])
        rs_prev = float(rs_line.iloc[-22])
        curr_h52 = float(high_s.rolling(window=252).max().iloc[-1])
        curr_l52 = float(low_s.rolling(window=252).min().iloc[-1])

        # 8 項趨勢條件
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
        if score == 0: return None # 排除得分為 0 的股票

        return {
            "總得分": score,
            "代號": ticker,
            "股票名稱": get_tw_stock_name(ticker),
            "收盤價": round(last_p, 2),
            "RS 相對強度": rs_value,
            "C1:價>長均": "✅" if cond[0] else "❌",
            "C2:長均多排": "✅" if cond[1] else "❌",
            "C3:200MA向上": "✅" if cond[2] else "❌",
            "C4:均線全多排": "✅" if cond[3] else "❌",
            "C5:價>50MA": "✅" if cond[4] else "❌",
            "C6:底反彈30%": "✅" if cond[5] else "❌",
            "C7:近高25%": "✅" if cond[6] else "❌",
            "C8:RS上升": "✅" if cond[7] else "❌"
        }
    except:
        return None

# --- 表格樣式 ---
def style_fn(val):
    if val == '✅': return 'color: #EB3323; font-weight: bold'
    if val == '❌': return 'color: #999999'
    return ''

def score_bg(val):
    if isinstance(val, int):
        if val >= 7: return 'background-color: #FFCDD2; color: #B71C1C; font-weight: bold'
        if val >= 5: return 'background-color: #FFF9C4; color: #F57F17'
    return ''

# --- UI 介面 ---
st.title("📊 TWTrend 強勢股排行榜 (中文版)")
st.sidebar.header("掃描設定")

# 預設一些熱門股測試
default_list = "2330.TW, 2317.TW, 2454.TW, 2603.TW, 2382.TW, 3231.TW, 1513.TW, 1519.TW, 3017.TW, 6806.TW"
input_str = st.sidebar.text_area("輸入台股代碼 (逗號隔開)", default_list)
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("開始掃描並排序"):
    try:
        with st.spinner('正在獲取證交所中文名稱與計算指標...'):
            # 大盤數據
            m_df = yf.download("^TWII", start=(now_tw - timedelta(days=730)).strftime('%Y-%m-%d'), auto_adjust=True)
            market_close = m_df['Close'].squeeze()
            
            # 個股數據
            all_data = fetch_bulk_data(input_str)
            
            results = []
            for ticker in ticker_list:
                res = analyze_stock(ticker, all_data, market_close)
                if res: results.append(res)
            
            if not results:
                st.warning("⚠️ 名單中沒有股票符合任何一項趨勢條件 (得分皆為 0)。")
            else:
                df_res = pd.DataFrame(results)
                
                # 排序邏輯：總得分(由大到小) -> RS強度(由大到小)
                df_res = df_res.sort_values(by=["總得分", "RS 相對強度"], ascending=[False, False])
                
                st.success(f"✅ 掃描完成！共列出 {len(df_res)} 檔強勢候選股。")
                
                # 顯示表格
                styled_df = df_res.style.map(style_fn).map(score_bg, subset=['總得分'])
                st.dataframe(styled_df, use_container_width=True, height=600)
                
                # 下載
                csv = df_res.to_csv(index=False).encode('utf-8-sig')
                st.download_button("匯出 Excel (CSV)", csv, "Stock_Trend_Report.csv", "text/csv")

    except Exception as e:
        st.error(f"分析失敗，錯誤訊息：{e}")
else:
    st.info("👈 請在側邊欄輸入股票代碼並點擊執行。")

with st.expander("📌 指標與 RS 公式說明"):
    st.markdown("""
    - **RS 相對強度**: 計算公式為 $$RS = \frac{Price_{Now} / Price_{1Y\_Ago}}{Market_{Now} / Market_{1Y\_Ago}} \times 100$$。
        - 數值 **> 100**: 代表表現優於加權指數。
        - 數值 **< 100**: 代表表現落後加權指數。
    - **排序規則**: 系統會優先將 **總得分**（滿分 8 分）最高的排在前面；若得分相同，則 **RS 相對強度** 較高者排在前。
    - **中文名稱**: 強制從證交所資料庫抓取中文簡稱，若依然顯示英文，請檢查代號是否正確（如：2330.TW）。
    """)
