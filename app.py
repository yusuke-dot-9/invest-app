import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests

# --- 1. ページ設定 ---
st.set_page_config(page_title="US株・FANG+ 判定ダッシュボード", layout="wide")
st.title("🇺🇸 米国株＆FANG+ 投資判定ダッシュボード")

# --- 2. LINE通知関数 ---
def send_line_notification(message):
    try:
        if "LINE_CHANNEL_ACCESS_TOKEN" not in st.secrets or "LINE_USER_ID" not in st.secrets: 
            return
        token = st.secrets["LINE_CHANNEL_ACCESS_TOKEN"]
        user_id = st.secrets["LINE_USER_ID"]
        url = "https://api.line.me/v2/bot/message/push"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        data = {"to": user_id, "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=data)
    except: pass

# --- 3. データ取得関数（株価データ） ---
@st.cache_data(ttl=3600)
def load_us_data(ticker_symbol):
    try:
        vix_data = yf.download("^VIX", period="5y", progress=False)
        df_data = yf.download(ticker_symbol, period="5y", progress=False)
        
        if df_data.empty or vix_data.empty: 
            return None, None
            
        if isinstance(df_data.columns, pd.MultiIndex):
            df_data.columns = df_data.columns.get_level_values(0)
        if isinstance(vix_data.columns, pd.MultiIndex):
            vix_data.columns = vix_data.columns.get_level_values(0)

        df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
        vix = pd.DataFrame({'VIX': vix_data['Close']}).dropna()
        
        df.index = df.index.tz_localize(None)
        vix.index = vix.index.tz_localize(None)
        
        df['SMA25'] = df['Close'].rolling(window=25).mean()
        df['SMA200'] = df['Close'].rolling(window=200).mean()
        df['High20'] = df['High'].rolling(window=20).max()
        df['Drawdown_from_High20'] = (df['Close'] - df['High20']) / df['High20']
        
        df = df.join(vix, how='left').ffill()
        
        return df, ticker_symbol
    except Exception as e:
        return None, None

# --- 4. 【修正】純利益成長率の取得（賢い探索機能つき） ---
@st.cache_data(ttl=86400)
def get_net_income_growth(ticker_symbol):
    if ticker_symbol in ["TQQQ", "SOXL", "QQQ", "SPY"]:
        return None, None
    
    try:
        t = yf.Ticker(ticker_symbol)
        inc = t.income_stmt
        
        # income_stmtが空っぽの場合は financials を代用
        if inc is None or inc.empty:
            inc = t.financials
            
        if inc is None or inc.empty:
            return None, None
            
        # 💡 企業によって異なる「純利益」のラベル表記を片っ端から探す
        ni_labels_to_try = [
            "Net Income", 
            "Net Income Common Stockholders", 
            "Net Income From Continuing And Discontinued Operation",
            "Normalized Income",
            "Basic EPS" # 最悪EPS（1株あたり利益）で代用
        ]
        
        ni_series = None
        for label in ni_labels_to_try:
            if label in inc.index:
                ni_series = inc.loc[label].dropna()
                if not ni_series.empty:
                    break # 見つけたら探索終了
                    
        if ni_series is None or len(ni_series) < 2:
            return None, None
            
        # yfinanceは左側が最新の年なので、[0]が最新、[-1]が最古
        latest_ni = float(ni_series.iloc[0])
        oldest_ni = float(ni_series.iloc[-1])
        
        # 過去が赤字（マイナス）だとパーセンテージ成長率がバグるため除外
        if oldest_ni <= 0: 
            return None, None
            
        ni_growth = (latest_ni / oldest_ni) - 1
        return ni_growth, len(ni_series)
    except:
        return None, None

# --- 5. TQQQ・米国株専用判定ロジック関数 ---
def get_tqqq_signal(latest, prev):
    if latest['VIX'] >= 30 and latest['Close'] < (latest['SMA200'] * 0.8):
        return "🚨 大暴落キャッチ（全力買い）", "今すぐ全力買い・ナンピンのタイミングです"
    elif latest['Drawdown_from_High20'] <= -0.25:
        return "🔴 トレイリングストップ", "直近高値から25%下落。即撤退・損切り推奨です"
    elif prev['Close'] <= prev['SMA25'] and latest['Close'] > latest['SMA25']:
        return "🔥 爆速買い戻し", "上昇トレンド入り（ゴールデンクロス）。買い戻し推奨です"
    else:
        return "🟢 待機", "現状維持・継続ホールド"

# --- 6. 米国株＆FANG+ 銘柄リスト ---
US_TICKERS = {
    "TQQQ (ナスダック3倍ブル)": "TQQQ",
    "SOXL (半導体3倍ブル)": "SOXL",
    "QQQ (ナスダック100)": "QQQ",
    "SPY (S&P500)": "SPY",
    "NVDA (エヌビディア)": "NVDA",
    "AAPL (アップル)": "AAPL",
    "MSFT (マイクロソフト)": "MSFT",
    "AMZN (アマゾン)": "AMZN",
    "META (メタ/Facebook)": "META",
    "GOOGL (アルファベット/Google)": "GOOGL",
    "NFLX (ネットフリックス)": "NFLX",
    "TSLA (テスラ)": "TSLA",
    "AVGO (ブロードコム)": "AVGO",
    "SNOW (スノーフレイク)": "SNOW",
    "CRWD (クラウドストライク)": "CRWD"
}

# --- サイドバー ---
st.sidebar.header("🔍 米国銘柄選択")
selected_name = st.sidebar.selectbox("銘柄名を選択", options=list(US_TICKERS.keys()))
ticker_code = US_TICKERS[selected_name]

# --- メインコンテンツ ---
df, symbol = load_us_data(ticker_code)

if df is not None:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    signal_title, action_msg = get_tqqq_signal(latest, prev)
    
    st.markdown(f"## 🎯 本日の判定：**{signal_title}**")
    st.info(f"**アクション指示：** {action_msg}")
    st.write("---")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("現在値 (USD)", f"${latest['Close']:,.2f}")
    col2.metric("VIX (恐怖指数)", f"{latest['VIX']:.2f}", "30以上で警戒" if latest['VIX']>=30 else "安定")
    
    dd_percent = latest['Drawdown_from_High20'] * 100
    col3.metric("直近20日高値からの下落率", f"{dd_percent:.1f}%", "-25%で損切り" if dd_percent <= -25 else "安全")
    
    sma200_dist = ((latest['Close'] / latest['SMA200']) - 1) * 100
    col4.metric("200日線との乖離率", f"{sma200_dist:+.1f}%", "-20%以下でバーゲン" if sma200_dist <= -20 else "")

    st.write("---")

    # --- 株価 vs 純利益 の乖離率チェック ---
    st.markdown("### 🏢 株価成長 vs 純利益成長（ファンダメンタル乖離率）")
    if ticker_code in ["TQQQ", "SOXL", "QQQ", "SPY"]:
        st.write("※ETF（指数）のため、純利益データはありません。")
    else:
        price_old = df['Close'].iloc[0]
        price_new = latest['Close']
        price_growth = (price_new / price_old) - 1
        
        ni_growth, years = get_net_income_growth(ticker_code)
        
        if ni_growth is not None:
            divergence = price_growth - ni_growth
            
            c1, c2, c3 = st.columns(3)
            c1.metric("過去5年の株価上昇率", f"{price_growth*100:+.1f}%")
            c2.metric(f"過去{years}年の純利益成長率", f"{ni_growth*100:+.1f}%")
            
            div_color = "normal"
            if divergence > 0.5:
                div_status = "⚠️ 期待先行（株価上がりすぎ）"
            elif divergence < -0.2:
                div_status = "✨ 超割安（利益に株価が追いついていない）"
            else:
                div_status = "🟢 適正水準（利益と株価が連動）"
                
            c3.metric("乖離率（株価上昇分 - 利益成長分）", f"{divergence*100:+.1f} pt", div_status)
            
            st.caption("※乖離率が大きなプラスの場合は「バブル・期待先行」、マイナスの場合は「割安・出遅れ」の可能性があります。")
        else:
            st.warning("現在、純利益データを取得できませんでした。時間をおいて再試行するか、公式ページでご確認ください。")

    st.write("---")
    official_url = f"https://finance.yahoo.com/quote/{ticker_code}"
    st.link_button(f"🔗 {ticker_code} の詳細を米Yahoo! Financeで確認", official_url)

    if st.button("📱 本日の判定結果をLINEに送信"):
        line_msg = f"【🇺🇸 米国株判定レポート】\n銘柄: {selected_name}\n判定: {signal_title}\n指示: {action_msg}\n価格: ${latest['Close']:,.2f}"
        send_line_notification(line_msg)
        st.success("LINEに通知を送信しました！")
