import streamlit as st
import yfinance as yf
import pandas as pd
import requests
from io import StringIO
import datetime

# ==========================================
# ページ設定 & スタイル
# ==========================================
st.set_page_config(
    page_title="デイリー投資ダッシュボード",
    page_icon="📈",
    layout="centered"
)

# スマホ閲覧用に Metric（数値表示）などを少し大きく・見やすくするCSS
st.markdown("""
<style>
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# データ取得関数（キャッシュ有効化）
# ==========================================
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_tqqq_vix_data():
    """TQQQとVIXの直近1年分のデータを取得"""
    tqqq = yf.download("TQQQ", period="1y", interval="1d", progress=False)
    vix = yf.download("^VIX", period="1y", interval="1d", progress=False)
    return tqqq, vix

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sp500_tickers():
    """WikipediaからS&P500のティッカーシンボル一覧を取得"""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    tables = pd.read_html(StringIO(response.text))
    df = tables[0]
    tickers = df['Symbol'].tolist()
    # yfinance用にドットをハイフンに変換（BRK.B -> BRK-Bなど）
    tickers = [t.replace('.', '-') for t in tickers]
    return tickers

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_sp500_data(tickers):
    """S&P500全銘柄の直近1年分のデータをマルチスレッドで一括取得"""
    df = yf.download(tickers, period="1y", interval="1d", progress=False, threads=True)
    return df

# ==========================================
# 分析ロジック関数
# ==========================================
def analyze_tqqq(tqqq_data, vix_data):
    if tqqq_data.empty or vix_data.empty:
        return None
        
    tqqq_c = tqqq_data['Close'].dropna()
    tqqq_h = tqqq_data['High'].dropna()
    vix_c = vix_data['Close'].dropna()
    
    # 200日SMAが計算できない場合はスキップ
    if len(tqqq_c) < 200:
        return None
        
    curr_tqqq = float(tqqq_c.iloc[-1])
    curr_vix = float(vix_c.iloc[-1])
    
    # 指標の計算
    sma_200 = float(tqqq_c.rolling(window=200).mean().iloc[-1])
    sma_25_series = tqqq_c.rolling(window=25).mean()
    curr_sma_25 = float(sma_25_series.iloc[-1])
    prev_sma_25 = float(sma_25_series.iloc[-2])
    prev_tqqq = float(tqqq_c.iloc[-2])
    
    high_20 = float(tqqq_h.rolling(window=20).max().iloc[-1])
    dd_20 = (curr_tqqq / high_20 - 1) * 100
    
    # アクション判定ロジック
    if curr_vix > 30 and curr_tqqq < (sma_200 * 0.8):
        action = "🚨 大暴落キャッチ（全力買い）"
        color = "#FF4B4B" # Red
    elif dd_20 <= -25:
        action = "🔴 トレイリングストップ（即撤退）"
        color = "#FF4B4B"
    elif prev_tqqq <= prev_sma_25 and curr_tqqq > curr_sma_25:
        action = "🔥 爆速買い戻し（強気）"
        color = "#FFA500" # Orange
    else:
        action = "🟢 待機（トレンドフォロー継続）"
        color = "#00CC66" # Green
        
    return {
        'curr_tqqq': curr_tqqq,
        'curr_vix': curr_vix,
        'dd_20': dd_20,
        'sma_200': sma_200,
        'curr_sma_25': curr_sma_25,
        'high_20': high_20,
        'action': action,
        'color': color
    }

def analyze_sp500():
    tickers = fetch_sp500_tickers()
    data = fetch_sp500_data(tickers)
    
    if data.empty or not isinstance(data.columns, pd.MultiIndex):
        import time
        time.sleep(1) # 回避遅延
        return pd.DataFrame()
        
    closes = data['Close']
    highs = data['High']
    results = []
    
    for ticker in tickers:
        if ticker not in closes.columns:
            continue
            
        close_s = closes[ticker].dropna()
        high_s = highs[ticker].dropna()
        
        # 200日SMAを計算するため最低200日のデータが必要
        if len(close_s) < 200:
            continue
            
        curr_close = float(close_s.iloc[-1])
        sma_200 = float(close_s.rolling(window=200).mean().iloc[-1])
        
        # 条件1: 終値が200日SMAより上（上昇トレンド）
        if curr_close <= sma_200:
            continue
            
        # 条件2: 直近2ヶ月（40営業日）の騰落率が +10% 以上
        mom_40 = (curr_close / float(close_s.iloc[-40]) - 1) * 100
        if mom_40 < 10:
            continue
            
        # 条件3: 直近10日間の高値から -3% 以上下落
        high_10 = float(high_s.rolling(window=10).max().iloc[-1])
        dd_10 = (curr_close / high_10 - 1) * 100
        if dd_10 > -3: # 下落率が-3%より浅ければ対象外
            continue
            
        # 条件4: 2日間のRSI（RSI-2）が10未満
        delta = close_s.diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        ema_up = up.ewm(alpha=1/2, adjust=False).mean()
        ema_down = down.ewm(alpha=1/2, adjust=False).mean()
        # ゼロ除算回避
        rs = ema_up / ema_down.replace(0, 1e-10)
        rsi_series = 100 - (100 / (1 + rs))
        rsi_2 = float(rsi_series.iloc[-1])
        
        if rsi_2 >= 10:
            continue
            
        sma_5 = float(close_s.rolling(window=5).mean().iloc[-1])
        
        results.append({
            'ﾃｨｯｶｰ': ticker,
            '現在値 ($)': round(curr_close, 2),
            'RSI-2': round(rsi_2, 2),
            '高値下落 (%)': round(dd_10, 2),
            'モメンタム (%)': round(mom_40, 2),
            '利確目標(5SMA)': round(sma_5, 2)
        })
        
    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values(by='RSI-2', ascending=True)
    return df

# ==========================================
# メインApp
# ==========================================
def main():
    st.title("📱 デイリー投資ダッシュボード")
    st.markdown("毎朝スマホでサクッと1分確認。データに基づいた確実なシステムトレード。")
    
    tab1, tab2 = st.tabs(["🔥 TQQQ戦略", "💎 S&P500スクリーナー"])
    
    # ---------------- 
    # タブ1: TQQQ戦略
    # ----------------
    with tab1:
        st.header("📊 TQQQ トレンドフォロー判定")
        
        with st.spinner("TQQQ・VIXデータを取得中..."):
            tqqq_data, vix_data = fetch_tqqq_vix_data()
            result = analyze_tqqq(tqqq_data, vix_data)
            
        if result is None:
            st.error("データの取得・解析に失敗しました。")
        else:
            # 3カラムで数値を大きく表示
            col1, col2, col3 = st.columns(3)
            col1.metric("TQQQ 現在値", f"${result['curr_tqqq']:.2f}")
            col2.metric("VIX 現在値", f"{result['curr_vix']:.2f}")
            col3.metric("20日高値から", f"{result['dd_20']:.2f}%")
            
            st.markdown("---")
            st.markdown("<p style='text-align: center; font-size: 1.1rem; margin-bottom: 0;'>【 本日のアクション指示 】</p>", unsafe_allow_html=True)
            
            # アクション指示メッセージ（カラー枠付き）
            st.markdown(f"""
                <div style='text-align: center; padding: 20px; border-radius: 12px; background-color: rgba(255,255,255,0.05); border: 2px solid {result['color']}; margin-top: 10px; margin-bottom: 20px;'>
                    <h2 style='color: {result['color']}; margin: 0;'>{result['action']}</h2>
                </div>
            """, unsafe_allow_html=True)
            
            with st.expander("詳細データ・算出基準"):
                st.write(f"- 200日SMA: **${result['sma_200']:.2f}**")
                st.write(f"- 終値が200日線の80%未満か: **{'Yes' if result['curr_tqqq'] < (result['sma_200'] * 0.8) else 'No'}**")
                st.write(f"- 25日SMA: **${result['curr_sma_25']:.2f}**")
                st.write(f"- 20日直近高値: **${result['high_20']:.2f}**")
                
    # ---------------- 
    # タブ2: S&P500スクリーナー
    # ----------------
    with tab2:
        st.header("💎 S&P500 厳選お宝スクリーナー")
        st.write("強い上昇トレンドの中で「超短期のパニック売り（RSI-2 < 10）」に巻き込まれた優良銘柄を抽出します。")
        
        with st.spinner("S&P500データのマルチスレッド取得・解析中...（初回は約20〜30秒かかります）"):
            df_sp500 = analyze_sp500()
            
        if df_sp500.empty:
            st.info("本日の条件に合致する「S&P500お宝銘柄」はありませんでした。")
        else:
            st.success(f"🔥 {len(df_sp500)}銘柄がヒットしました！")
            # スマホでも見やすいようにDataFrameで綺麗に表示
            st.dataframe(df_sp500, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
