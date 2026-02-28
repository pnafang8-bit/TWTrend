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

# 快取股票名稱
@st.cache_data(ttl=86400)
def get_stock_name(ticker):
    try:
        t = yf.Ticker(ticker)
        name = t.info.get('shortName') or t.info.get('longName') or ticker
        return name
    except:
        return ticker

@st.cache_data(ttl=3600)
def fetch_bulk_data(tickers, days=730):
    df = yf.download(tickers, start=(now_tw - timedelta(days=days)).strftime('%Y-%m-%d'), auto_adjust=True)
    return df

def analyze_stock(ticker, full_df, market_close):
    try:
        # 處理多重索引
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
        rs_line = (close_s / market_close.loc[stock_df.index]) * 100
        h52 = high_s.rolling(window=252).max()
        l52 = low_s.rolling(window=252).min()
        
        # 取得數值
        last_p = float(close_s.iloc[-1])
        m50 = float(ma50.iloc[-1])
        m150 = float(ma150.iloc[-1])
        m200 = float(ma200.iloc[-1])
        m200_prev = float(ma200.iloc[-22])
        rs_now = float(rs_line.iloc[-1])
        rs_prev = float(rs_line.iloc[-22])
        curr_h52 = float(h52.iloc[-1])
        curr_l52 = float(l52.iloc[-1])

        # 8 項條件
        cond = [
            last_p > m150 and last_p > m200,
            m150 > m200,
            m200 > m200_prev,
            m50 > m150 and m50 > m200,
            last_p > m50,
            last_p >= (curr_l52 * 1.30),
            last_p >= (curr_h52 * 0.75),
            rs_now > rs_prev
        ]
        
        score = sum(cond)
        
        # 如果得分為 0，直接回傳 None，後續會被過濾掉
        if score == 0:
            return None

        return {
            "總得分": score,
            "代號": ticker,
            "名稱": get_stock_name(ticker),
            "收盤價": round(last_p, 2),
            "C1:價>長均": "✅" if cond[0] else "❌",
            "C2:長均多排": "✅" if cond[1] else "❌",
            "C3:200MA向上": "✅" if cond[2] else "❌",
            "C4:均線全多排": "✅" if cond[3] else "❌",
            "C5:價>50MA": "✅" if cond[4] else "❌",
            "C6:底反彈30%": "✅" if cond[5] else "❌",
            "C7:近高25%": "✅" if cond[6] else "❌",
            "C8:RS趨勢": "✅" if cond[7] else "❌"
        }
    except:
        return None

# --- UI 介面 ---
st.title("📊 TWTrend 強勢股篩選器 (排除 0 分股)")
st.sidebar.header("篩選設定")

default_tickers = "2330.TW, 2317.TW, 2454.TW, 2603.TW, 2382.TW, 3231.TW, 1513.TW, 1519.TW, 1504.TW, 2303.TW, 3037.TW, 2376.TW"
input_str = st.sidebar.text_area("輸入台股代碼 (逗號隔開)", default_tickers)
ticker_list = [t.strip().upper() for t in input_str.split(",") if t.strip()]

if st.sidebar.button("開始篩選"):
    try:
        with st.spinner('分析中，請稍候...'):
            # 大盤數據
            m_df = yf.download("^TWII", start=(now_tw - timedelta(days=730)).strftime('%Y-%m-%d'), auto_adjust=True)
            market_close = m_df['Close'].squeeze()
            
            # 批次下載
            all_data = fetch_bulk_data(ticker_list)
            
            results = []
            for ticker in ticker_list:
                res = analyze_stock(ticker, all_data, market_close)
                if res: # 只有非 None (得分 > 0) 的才會加入
                    results.append(res)
            
            if not results:
                st.warning("⚠️ 掃描完成，但在輸入的名單中沒有任何股票符合至少一項趨勢條件。")
            else:
                df_result = pd.DataFrame(results)
                
                # 排序：得分(大到小) -> 代號(小到大)
                df_result = df_result.sort_values(by=["總得分", "代號"], ascending=[False, True])

                st.success(f"✅ 掃描完成！已列出 {len(df_result)} 檔具有動能的股票（已隱藏 0 分股票）。")

                # 顯示表格
                st.dataframe(
                    df_result.style.applymap(
                        lambda x: 'color: #EB3323; font-weight: bold' if x == '✅' else 'color: #999999' if x == '❌' else ''
                    ).background_gradient(subset=['總得分'], cmap='YlOrRd'),
                    use_container_width=True,
                    height=600
                )

                # 下載按鈕
                csv = df_result.to_csv(index=False).encode('utf-8-sig')
                st.download_button("匯出結果", csv, "Trend_Score_List.csv", "text/csv")

    except Exception as e:
        st.error(f"錯誤：{e}")
else:
    st.info("👈 請在左側輸入代碼並點擊「開始篩選」。")

with st.expander("📌 評分指標說明"):
    st.markdown("""
    本表僅顯示 **得分 > 0** 的股票。各項條件公式如下：
    - **C1 & C2 (長期趨勢)**: $$Price > MA_{150}/200$$ 且 $$MA_{150} > MA_{200}$$
    - **C3 (均線斜率)**: $$MA_{200}$$ 正在向上
    - **C4 & C5 (中期趨勢)**: $$MA_{50}$$ 排列正確且價格在其上方
    - **C6 (超跌反彈)**: $$Price \ge (Low_{52W} \times 1.30)$$
    - **C7 (強勢整理)**: $$Price \ge (High_{52W} \times 0.75)$$
    - **C8 (相對強度)**: 當前 $$RS$$ 指標優於一個月前
    """)
