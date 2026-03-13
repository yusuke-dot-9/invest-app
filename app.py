import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests

# --- 1. ページ設定 ---
st.set_page_config(page_title="US株・TQQQ 判定ダッシュボード", layout="wide")
st.title("🇺🇸 米国株＆TQQQ 投資判定ダッシュボード")

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

# --- 3. 【最重要】Yahoo!ファイナンス エラー回避セッション ---
# これが「Too Many Requests」を防ぐための魔法のパスポートです
def get_safe_session():
    session = requests.Session()
    # 一般的なブラウザ（Chrome）からのアクセスだと偽装する
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    })
    return session

# --- 4. データ取得関数（パスポート付き） ---
@st.cache_data(ttl=3600)
def load_us_data(ticker_symbol):
    try:
        safe_session = get_safe_session()
        
        # 恐怖指数（VIX）の取得
        vix_data = yf.Ticker("^VIX", session=safe_session).history(period="5y")
        # 個別株（TQQQなど）の取得
        df_data = yf.Ticker(ticker_symbol, session=safe_session).history(period="5y")
        
        if df_data.empty or vix_data.empty: 
            return None, None
            
        df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
        vix = pd.DataFrame({'VIX': vix_data['Close']}).dropna()
        
        # テクニカル指標の計算
        df['SMA25'] = df['Close'].rolling(window=25).mean()
        df['SMA200'] = df['Close'].rolling(window=200).mean()
        df['High20'] = df['High'].rolling(window=20).max()
        
        # 直近20日高値からの下落率
        df['Drawdown_from_High20'] = (df['Close'] - df['High20']) / df['High20']
        
        df.index = df.index.tz_localize(None)
        vix.index = vix.index.tz_localize(None)
        
        # VIXデータを結合
        df = df.join(vix, how='left').ffill()
        
        return df, ticker_symbol
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return None, None

# --- 5. TQQQ専用判定ロジック関数 ---
def get_tqqq_signal(latest, prev):
    # ① 🚨 大暴落キャッチ（全力買い）: VIX 30以上 ＆ 株価が200日線から-20%以上乖離
    if latest['VIX'] >= 30 and latest['Close'] < (latest['SMA200'] * 0.8):
        return "🚨 大暴落キャッチ（全力買い）", "今すぐ全力買い・ナンピンのタイミングです"
        
    # ② 🔴 トレイリングストップ（即撤退・損切り）: 直近20日高値から -25% 下落
    elif latest['Drawdown_from_High20'] <= -0.25:
        return "🔴 トレイリングストップ", "直近高値から25%下落。即撤退・損切り推奨です"
        
    # ③ 🔥 爆速買い戻し（強気トレンド入り）: 前日25日線以下 → 本日25日線上抜け
    elif prev['Close'] <= prev['SMA25'] and latest['Close'] > latest['SMA25']:
        return "🔥 爆速買い戻し", "上昇トレンド入り（ゴールデンクロス）。買い戻し推奨です"
        
    # ④ 🟢 待機（トレンドフォロー継続）
    else:
        return "🟢 待機", "現状維持・継続ホールド"


# --- 6. 主要米国銘柄リスト ---
US_TICKERS = {
    "TQQQ (ナスダック3倍ブル)": "TQQQ",
    "SOXL (半導体3倍ブル)": "SOXL",
    "QQQ (ナスダック100)": "QQQ",
    "SPY (S&P500)": "SPY",
    "NVDA (エヌビディア)": "NVDA",
    "AAPL (アップル)": "AAPL",
    "MSFT (マイクロソフト)": "MSFT",
    "TSLA (テスラ)": "TSLA"
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
    
    # 判定の実行
    signal_title, action_msg = get_tqqq_signal(latest, prev)
    
    # 画面表示
    st.markdown(f"## 🎯 本日の判定：**{signal_title}**")
    st.info(f"**アクション指示：** {action_msg}")
    
    st.write("---")
    
    # 主要データの表示
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("現在値 (USD)", f"${latest['Close']:,.2f}")
    col2.metric("VIX (恐怖指数)", f"{latest['VIX']:.2f}", "30以上で警戒レベル" if latest['VIX']>=30 else "安定")
    
    dd_percent = latest['Drawdown_from_High20'] * 100
    col3.metric("直近20日高値からの下落率", f"{dd_percent:.1f}%", "-25%で損切り" if dd_percent <= -25 else "安全圏")
    
    sma200_dist = ((latest['Close'] / latest['SMA200']) - 1) * 100
    col4.metric("200日線との乖離率", f"{sma200_dist:+.1f}%", "-20%以下でバーゲン" if sma200_dist <= -20 else "")

    st.write("---")
    
    # Yahoo Finance (US) への公式リンク
    official_url = f"https://finance.yahoo.com/quote/{ticker_code}"
    st.link_button(f"🔗 {ticker_code} の詳細を米Yahoo! Financeで確認", official_url)

    # LINE送信ボタン
    if st.button("📱 本日の判定結果をLINEに送信"):
        line_msg = (
            f"【🇺🇸 米国株判定レポート】\n"
            f"銘柄: {selected_name}\n"
            f"判定: {signal_title}\n"
            f"指示: {action_msg}\n\n"
            f"価格: ${latest['Close']:,.2f}\n"
            f"VIX: {latest['VIX']:.2f}\n"
            f"高値からの下落率: {dd_percent:.1f}%\n"
            f"200日線乖離率: {sma200_dist:+.1f}%"
        )
        send_line_notification(line_msg)
        st.success("LINEに通知を送信しました！")

else:
    st.warning("現在、Yahoo Finance側の制限によりデータが取得できません。数十秒待ってからリロードしてください。")
