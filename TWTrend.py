import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import pytz

# 時區與頁面設定
tw_tz = pytz.timezone('Asia/Taipei')
now_tw = datetime.now(tw_tz)
st.set_page_config(layout="wide", page_title="TWTrend | 強勢股篩選器")

# 快取股票中文名稱
@st.cache_data(ttl=86400)
def get_stock_name_ch(ticker):
    try:
        t = yf.Ticker(ticker)
        # yfinance 的 shortName 在台股通常會回傳中文名稱
        name = t.info.get('shortName') or t.info.get('longName') or ticker
        return name
    except:
        return ticker

@st.cache_data(ttl=3600)
def fetch_bulk_data(tickers, days=730):
    # 下載數據並處理多重索引
    df = yf.download(tickers, start=(now_tw - timedelta(days=days)).strftime('%Y-%m-%d'), auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex) and len(tickers.split(',')) == 1:
        df.columns = df.columns.get_level_values(0)
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
        
        # RS 相對強度數值計算 (個股表現 / 大盤表現)
        # 這裡定義 RS 數值為：(個股現價/個股一年前價) / (大盤現價/大盤一年前價) * 100
        stock_perf = close_s.iloc[-1] / close_s.iloc[-252]
        mkt_perf = market_close.iloc[-1] / market_close.loc[stock_df.index[0]] # 對應時間點
        rs_value = round((stock_perf / mkt_perf) * 100, 2)
        
        # 用於 C8 判斷的 RS Line (短期趨勢)
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
        if score == 0: return None

        return {
            "總得分": score,
            "代號": ticker,
            "名稱": get_stock_name_ch(ticker),
            "收盤價": round(last_p, 2),
            "RS 相對強度": rs_value,
            "C1:價>長均": "✅" if cond[0] else "❌",
            "C2:均線多排": "✅" if cond[1] else "❌",
            "C3:200MA↑": "✅" if cond[2] else "❌",
            "C4:中長多排": "✅" if cond[3] else "❌",
            "C5:價>50MA": "✅" if cond[4] else "❌",
            "C6:底反彈30%": "✅" if cond[5] else "❌",
            "C7:近高25%": "✅" if cond[6] else "❌",
            "C8:RS上升": "✅" if cond[7] else "❌"
        }
    except:
        return None

# --- 表格樣式 ---
def style_table(val):
    if val == '✅': return 'color: #EB3323; font-weight: bold'
    if val == '❌': return 'color: #999999'
    return ''

def highlight_score(val):
    if isinstance(val, int):
        if val >= 7: return 'background-color: #FFCDD2; color: #B71C1C; font-weight: bold'
        if val >= 5: return 'background-color: #FFF9C4; color: #F57F17'
    return ''

# --- UI ---
st.title("🚀 TWTrend 台股強勢股掃描儀")
st.sidebar.header("掃描設定")

# 範例股票
example_list = "2330.TW, 2317.TW, 2454.TW, 2603.TW, 2382.TW, 3231.TW, 1513.TW, 1519.TW, 6806.TW, 3017.TW, 3324.TW"
input_str = st.sidebar.text_area("請輸入台股代碼 (以逗號隔開)", example_list)
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("開始掃描分析"):
    try:
        with st.spinner('正在分析市場趨勢與抓取中文名稱...'):
            # 大盤數據
            m_df = yf.download("^TWII", start=(now_tw - timedelta(days=750)).strftime('%Y-%m-%d'), auto_adjust=True)
            m_close = m_df['Close'].squeeze()
            
            # 個股數據
            all_data = fetch_bulk_data(input_str)
            
            results = []
            for ticker in ticker_list:
                res = analyze_stock(ticker, all_data, m_close)
                if res: results.append(res)
            
            if not results:
                st.warning("⚠️ 所選名單中目前沒有股票符合趨勢模板 (得分皆為 0)。")
            else:
                df_res = pd.DataFrame(results)
                # 排序：總得分 > RS 相對強度
                df_res = df_res.sort_values(by=["總得分", "RS 相對強度"], ascending=[False, False])
                
                st.success(f"✅ 掃描完成！共找到 {len(df_res)} 檔具備動能之個股。")
                
                # 套用樣式
                styled_df = df_res.style.map(style_table).map(highlight_score, subset=['總得分'])
                
                st.dataframe(styled_df, use_container_width=True, height=600)
                
                # 下載
                csv = df_res.to_csv(index=False).encode('utf-8-sig')
                st.download_button("匯出分析報表", csv, f"TrendScan_{now_tw.strftime('%Y%m%d')}.csv", "text/csv")

    except Exception as e:
        st.error(f"分析發生錯誤：{e}")
else:
    st.info("👈 請在左側輸入自選股代碼，點擊按鈕開始分析。")

with st.expander("📊 指標定義說明"):
    st.markdown("""
    1. **RS 相對強度**: 計算公式為 $$(Stock_{Return} / Market_{Return}) \times 100$$。數值 > 100 表示表現優於大盤，數值越高動能越強。
    2. **總得分**: 滿分 8 分，採用 Mark Minervini 的趨勢模板條件。
    3. **中文名稱**: 系統自動從數據源抓取該代號對應的中文簡稱。
    4. **C1~C8**: 分別代表價格位置、均線排列、52週高低點距離與相對強度趨勢。
    """)
