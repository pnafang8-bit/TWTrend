import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz

# 時區與頁面設定
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)
st.set_page_config(layout="wide", page_title="TWTrend | 多週期 RS 強勢股分析")

# 獲取繁體中文名稱 (無快取，每次重新抓取)
def get_stock_name_tw(ticker):
    try:
        t = yf.Ticker(ticker)
        name = t.info.get('shortName')
        if not name or name.isascii():
            name = t.info.get('longName')
        return name if name else ticker
    except:
        return ticker

# 抓取盤後數據 (無快取)
def fetch_bulk_data(tickers, days=750):
    df = yf.download(tickers, start=(now_tw - timedelta(days=days)).strftime('%Y-%m-%d'), auto_adjust=True)
    return df

def analyze_stock(ticker, full_df, market_close):
    try:
        if isinstance(full_df.columns, pd.MultiIndex):
            stock_df = full_df.xs(ticker, axis=1, level=1).dropna()
        else:
            stock_df = full_df.dropna()
            
        # 至少需要一年的數據 (約 252 交易日)
        if len(stock_df) < 250: return None
        
        close_s = stock_df['Close']
        high_s = stock_df['High']
        low_s = stock_df['Low']
        
        # --- 指標計算 ---
        ma50 = ta.sma(close_s, length=50)
        ma150 = ta.sma(close_s, length=150)
        ma200 = ta.sma(close_s, length=200)
        
        # --- RS 相對強度與報酬率計算 ---
        # 1. 一年期 (252天)
        stock_perf_1y = close_s.iloc[-1] / close_s.iloc[-252]
        mkt_perf_1y = market_close.iloc[-1] / market_close.iloc[-252]
        rs_1y = round((stock_perf_1y / mkt_perf_1y) * 100, 2)
        
        # 2. 一季期 (63天)
        stock_perf_3m = close_s.iloc[-1] / close_s.iloc[-63]
        mkt_perf_3m = market_close.iloc[-1] / market_close.iloc[-63]
        rs_3m = round((stock_perf_3m / mkt_perf_3m) * 100, 2)
        
        # 3. 季報酬率 (%)
        q_return = round(((stock_perf_3m - 1) * 100), 2)
        
        # RS Line 趨勢 (用於 C8 判斷)
        rs_line = (close_s / market_close.loc[stock_df.index]) * 100
        
        # 變數提取
        last_p = float(close_s.iloc[-1])
        m50 = float(ma50.iloc[-1])
        m150 = float(ma150.iloc[-1])
        m200 = float(ma200.iloc[-1])
        m200_prev = float(ma200.iloc[-22])
        rs_now = float(rs_line.iloc[-1])
        rs_prev = float(rs_line.iloc[-22])
        curr_h52 = float(high_s.rolling(window=252).max().iloc[-1])
        curr_l52 = float(low_s.rolling(window=252).min().iloc[-1])

        # Mark Minervini 8 項趨勢條件
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
            "季報酬(%)": q_return,
            "RS年強度": rs_1y,
            "RS季強度": rs_3m,
            "C1:價>長均": "✅" if cond[0] else "❌",
            "C2:長均多排": "✅" if cond[1] else "❌",
            "C3:200MA↑": "✅" if cond[2] else "❌",
            "C4:均線多排": "✅" if cond[3] else "❌",
            "C5:價>50MA": "✅" if cond[4] else "❌",
            "C6:底反彈30%": "✅" if cond[5] else "❌",
            "C7:近高25%": "✅" if cond[6] else "❌",
            "C8:RS上升": "✅" if cond[7] else "❌"
        }
    except:
        return None

# --- 表格樣式 ---
def style_logic(val):
    if val == '✅': return 'color: #d63031; font-weight: bold'
    if val == '❌': return 'color: #b2bec3'
    return ''

def score_highlight(val):
    if isinstance(val, int):
        if val >= 7: return 'background-color: #ffeaa7; color: #d63031; font-weight: bold'
        if val >= 5: return 'background-color: #f1f2f6; color: #2d3436'
    return ''

def return_color(val):
    if isinstance(val, (int, float)):
        color = '#d63031' if val > 0 else '#2ecc71' if val < 0 else 'black'
        return f'color: {color}; font-weight: bold'
    return ''

# --- UI 介面 ---
st.title("💹 TWTrend 強勢股分析 (一年/季 RS 強化版)")
st.sidebar.header("分析清單")

# 刪除預設清單
input_str = st.sidebar.text_area("請輸入台股代號 (例: 2330.TW, 2454.TW)", "", placeholder="請在此貼上代號，以逗號隔開...")
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("執行完整計算"):
    if not ticker_list:
        st.error("❌ 請輸入股票代號。")
    else:
        try:
            with st.spinner('正在重新抓取市場數據、計算各週期 RS 強度與報酬率...'):
                # 重新抓取大盤數據
                m_df = yf.download("^TWII", start=(now_tw - timedelta(days=750)).strftime('%Y-%m-%d'), auto_adjust=True)
                m_close = m_df['Close'].squeeze()
                
                # 重新抓取個股數據
                all_data = fetch_bulk_data(input_str)
                
                results = []
                for ticker in ticker_list:
                    res = analyze_stock(ticker, all_data, m_close)
                    if res: results.append(res)
                
                if not results:
                    st.warning("⚠️ 掃描完成。所選股票目前無任何一項符合強勢趨勢 (得分皆為 0)。")
                else:
                    df_res = pd.DataFrame(results)
                    
                    # 排序: 總得分 > RS年強度 > RS季強度
                    df_res = df_res.sort_values(by=["總得分", "RS年強度", "RS季強度"], ascending=[False, False, False])
                    
                    st.success(f"✅ 計算完成！共有 {len(df_res)} 檔股票具備動能。")
                    
                    # 套用樣式
                    styled_df = df_res.style.map(style_logic)\
                                            .map(score_highlight, subset=['總得分'])\
                                            .map(return_color, subset=['季報酬(%)', 'RS季強度'])
                    
                    st.dataframe(styled_df, use_container_width=True, height=600)
                    
                    # 匯出按鈕
                    csv = df_res.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("下載最新分析報表 (CSV)", csv, f"TrendScan_{now_tw.strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")

        except Exception as e:
            st.error(f"分析失敗，錯誤原因：{e}")
else:
    st.info("👈 請在側邊欄輸入股票代號（例如：$$2330.TW, 2454.TW, 2317.TW$$）並執行分析。")

with st.expander("📝 週期報酬與 RS 計算說明"):
    st.markdown("""
    - **RS 年強度 (1Y)**: 
      $$RS_{1Y} = \\frac{Stock_{1Y\\_Perf}}{Market_{1Y\\_Perf}} \\times 100$$
      數值越穩定，代表長線趨勢保護短線。
    - **RS 季強度 (3M)**: 
      $$RS_{3M} = \\frac{Stock_{3M\\_Perf}}{Market_{3M\\_Perf}} \\times 100$$
      數值越高，代表近三個月動能優於大盤，屬於短線強勢爆發。
    - **季報酬 (%)**: 指個股過去三個月 ($$63$$ 個交易日) 的純價格變動百分比。
    - **繁體中文名稱**: 即時從伺服器取得證交所官方登記名稱。
    """)
