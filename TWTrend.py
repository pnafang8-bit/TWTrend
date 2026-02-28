import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz

# 時區與頁面設定
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)
st.set_page_config(layout="wide", page_title="TWTrend | 即時強勢股分析")

# 獲取繁體中文名稱 (不使用快取，確保資料最新)
def get_stock_name_tw(ticker):
    try:
        t = yf.Ticker(ticker)
        # shortName 通常存放繁體中文簡稱
        name = t.info.get('shortName')
        if not name or name.isascii():
            name = t.info.get('longName')
        return name if name else ticker
    except:
        return ticker

# 抓取盤後數據 (不使用快取，每次執行皆重新下載)
def fetch_bulk_data(tickers, days=750):
    # auto_adjust=True 確保與還原股價計算一致
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
        
        # RS 相對強度數值 (Goodinfo 標準)
        # 公式: $$RS = \frac{Price_{Now} / Price_{252DaysAgo}}{Market_{Now} / Market_{252DaysAgo}} \times 100$$
        stock_perf = close_s.iloc[-1] / close_s.iloc[-252]
        mkt_perf = market_close.iloc[-1] / market_close.iloc[-252]
        rs_value = round((stock_perf / mkt_perf) * 100, 2)
        
        # RS Line 趨勢 (用於 C8 判斷)
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

        # 8 項強勢股條件 (Minervini 模板)
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
        if score == 0: return None 

        return {
            "總得分": score,
            "代號": ticker.split('.')[0],
            "名稱": get_stock_name_tw(ticker),
            "現價": round(last_p, 2),
            "RS相對強度": rs_value,
            "C1:價>長均": "✅" if cond[0] else "❌",
            "C2:長均多排": "✅" if cond[1] else "❌",
            "C3:200MA↑": "✅" if cond[2] else "❌",
            "C4:均線全多排": "✅" if cond[3] else "❌",
            "C5:價>50MA": "✅" if cond[4] else "❌",
            "C6:底反彈30%": "✅" if cond[5] else "❌",
            "C7:近高25%": "✅" if cond[6] else "❌",
            "C8:RS上升趨勢": "✅" if cond[7] else "❌"
        }
    except:
        return None

# --- 樣式設定 ---
def style_logic(val):
    if val == '✅': return 'color: #d63031; font-weight: bold'
    if val == '❌': return 'color: #b2bec3'
    return ''

def score_highlight(val):
    if isinstance(val, int):
        if val >= 7: return 'background-color: #ffeaa7; color: #d63031; font-weight: bold'
        if val >= 5: return 'background-color: #f1f2f6; color: #2d3436'
    return ''

# --- UI 介面 ---
st.title("💹 TWTrend 全手動強勢股掃描")
st.sidebar.header("分析清單輸入")

# 刪除預設清單，改為空字串
input_str = st.sidebar.text_area("請輸入台股代號 (例: 2330.TW, 2317.TW)", "", placeholder="請在此貼上代號，以逗號隔開...")
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("開始全量計算分析"):
    if not ticker_list:
        st.error("❌ 請先在左側輸入股票代號。")
    else:
        try:
            with st.spinner('正在重新抓取市場數據並進行繁體中文名稱匹配...'):
                # 重新抓取大盤數據
                m_df = yf.download("^TWII", start=(now_tw - timedelta(days=750)).strftime('%Y-%m-%d'), auto_adjust=True)
                m_close = m_df['Close'].squeeze()
                
                # 重新抓取個股數據
                all_data = fetch_bulk_data(input_str)
                
                results = []
                for ticker in ticker_list:
                    # 每次執行都進過完整分析邏輯
                    res = analyze_stock(ticker, all_data, m_close)
                    if res: results.append(res)
                
                if not results:
                    st.warning("⚠️ 掃描完成。所選股票目前無任何一項符合強勢趨勢 (得分皆為 0)。")
                else:
                    df_res = pd.DataFrame(results)
                    
                    # 排序: 總得分(高->低) > RS相對強度(高->低)
                    df_res = df_res.sort_values(by=["總得分", "RS相對強度"], ascending=[False, False])
                    
                    st.success(f"✅ 重新計算完成！目前名單中共有 {len(df_res)} 檔具備動能。")
                    
                    # 套用表格樣式
                    styled_df = df_res.style.map(style_logic).map(score_highlight, subset=['總得分'])
                    st.dataframe(styled_df, use_container_width=True, height=600)
                    
                    # 下載報表
                    csv = df_res.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("匯出最新報表 (CSV)", csv, f"TrendScan_{now_tw.strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")

        except Exception as e:
            st.error(f"分析失敗，錯誤原因：{e}")
else:
    st.info("👈 請在側邊欄輸入股票代號（例如：$$2330.TW, 2454.TW, 2317.TW$$），然後點擊按鈕執行完整分析。")

with st.expander("📝 計算邏輯說明"):
    st.markdown("""
    - **每次重新計算**: 本系統已移除快取機制，每次點擊按鈕皆會重新下載最新的歷史日線數據（約 750 天份量），確保 **$$200MA$$** 等長線指標反映最新股價。
    - **RS 相對強度**: 數值反映個股過去一年的漲幅相對於加權指數的倍數，$$RS > 100$$ 代表表現優於大盤。
    - **繁體中文名稱**: 即時從資料庫比對台灣交易所登記之官方簡稱。
    """)
