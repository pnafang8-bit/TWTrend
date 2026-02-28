import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz

# 時區與頁面設定
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)
st.set_page_config(layout="wide", page_title="Goodinfo 風格 | 強勢股篩選器")

# 模擬 Goodinfo 的繁體中文名稱抓取
@st.cache_data(ttl=86400)
def get_stock_name_tw(ticker):
    try:
        t = yf.Ticker(ticker)
        # shortName 通常是證交所提供的繁體中文簡稱
        name = t.info.get('shortName')
        if not name or name.isascii():
            name = t.info.get('longName')
        return name if name else ticker
    except:
        return ticker

@st.cache_data(ttl=3600)
def fetch_bulk_data(tickers, days=750):
    # 這裡採用 auto_adjust=True 確保與 Goodinfo 的還原股價邏輯一致
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
        
        # 指標計算 (移動平均線)
        ma50 = ta.sma(close_s, length=50)
        ma150 = ta.sma(close_s, length=150)
        ma200 = ta.sma(close_s, length=200)
        
        # --- RS 相對強度 (Goodinfo/Minervini 標準) ---
        # 計算公式: ((個股現價/個股一年前價) / (大盤現價/大盤一年前價)) * 100
        stock_perf = close_s.iloc[-1] / close_s.iloc[-252]
        mkt_perf = market_close.iloc[-1] / market_close.iloc[-252]
        rs_value = round((stock_perf / mkt_perf) * 100, 2)
        
        # 用於 C8 判斷的短期 RS 趨勢
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

        # 8 項趨勢指標 (Mark Minervini 模板)
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
        if score == 0: return None # 自動排除 0 分股

        return {
            "總得分": score,
            "代號": ticker.split('.')[0],
            "名稱": get_stock_name_tw(ticker),
            "現價": round(last_p, 2),
            "RS相對強度": rs_value,
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

# --- 表格樣式 (Goodinfo 紅綠風格) ---
def style_apply(val):
    if val == '✅': return 'color: #d63031; font-weight: bold' # Goodinfo 紅
    if val == '❌': return 'color: #b2bec3' # 灰色
    return ''

def score_bg(val):
    if isinstance(val, int):
        if val >= 7: return 'background-color: #ffeaa7; color: #d63031; font-weight: bold'
        if val >= 5: return 'background-color: #f1f2f6; color: #2d3436'
    return ''

# --- UI 介面 ---
st.title("💹 TWTrend 強勢股排行榜 (Goodinfo 樣式)")
st.sidebar.header("市場掃描設定")

# 預設自選名單
default_list = "2330.TW, 2317.TW, 2454.TW, 2603.TW, 2382.TW, 3231.TW, 3017.TW, 1513.TW, 1519.TW, 6806.TW, 3324.TW, 8046.TW"
input_str = st.sidebar.text_area("輸入股票代號 (例如 2330.TW)", default_list)
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("執行 Goodinfo 數據分析"):
    try:
        with st.spinner('正在分析盤後資料與計算 RS 相對強度...'):
            # 大盤數據 (加權指數)
            m_df = yf.download("^TWII", start=(now_tw - timedelta(days=750)).strftime('%Y-%m-%d'), auto_adjust=True)
            m_close = m_df['Close'].squeeze()
            
            # 個股數據
            all_data = fetch_bulk_data(input_str)
            
            results = []
            for ticker in ticker_list:
                res = analyze_stock(ticker, all_data, m_close)
                if res: results.append(res)
            
            if not results:
                st.warning("⚠️ 掃描完成。目前名單中沒有股票得分大於 0 (不符合強勢模板)。")
            else:
                df = pd.DataFrame(results)
                
                # 排序: 總得分(高->低) > RS相對強度(高->低)
                df = df.sort_values(by=["總得分", "RS相對強度"], ascending=[False, False])
                
                st.success(f"✅ 掃描完成！已列出 {len(df)} 檔有得分的繁體中文名單。")
                
                # 套用樣式
                styled_df = df.style.map(style_apply).map(score_highlight, subset=['總得分'])
                
                # 顯示表格
                st.dataframe(
                    df.style.map(style_apply).map(score_bg, subset=['總得分']),
                    use_container_width=True, 
                    height=600
                )
                
                # 下載按鈕
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("匯出分析報表 (CSV)", csv, f"Goodinfo_Style_{now_tw.strftime('%Y%m%d')}.csv", "text/csv")

    except Exception as e:
        st.error(f"數據抓取失敗：{e}")

with st.expander("📝 數據口徑與指標說明"):
    st.markdown("""
    1. **RS 相對強度 (Relative Strength)**: 
       這是 Goodinfo 核心價值指標，公式為：
       $$RS = \\frac{個股一年報酬率}{大盤一年報酬率} \\times 100$$
       - **> 100**: 表現領先大盤 (Alpha)
       - **< 100**: 表現落後大盤
    2. **繁體中文名稱**: 系統自動抓取台灣證券交易所與櫃買中心之官方簡稱。
    3. **排序邏輯**: 優先顯示 **總得分** 最高者；若得分相同，則 **RS 相對強度** 較高者排在前。
    4. **排除 0 分股**: 為了保持名單精簡，得分為 0 的個股不會顯示在表中。
    """)
