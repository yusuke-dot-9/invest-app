import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import datetime
import requests

# --- 1. ページ設定 ---
st.set_page_config(page_title="日本株 日経225分析システム", layout="wide")
st.title("🇯🇵 日本株 日経225 判定＆全銘柄スキャン")

# --- 2. LINE通知関数（最新版） ---
def send_line_notification(message):
    try:
        if "LINE_CHANNEL_ACCESS_TOKEN" not in st.secrets or "LINE_USER_ID" not in st.secrets:
            st.warning("LINEの連携設定（Secrets）が未完了です。")
            return
            
        token = st.secrets["LINE_CHANNEL_ACCESS_TOKEN"]
        user_id = st.secrets["LINE_USER_ID"]
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        data = {
            "to": user_id,
            "messages": [{"type": "text", "text": message}]
        }
        requests.post(url, headers=headers, json=data)
    except:
        pass

# --- 3. テクニカル指標計算 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 4. データ取得関数 ---
@st.cache_data(ttl=3600)
def load_data(ticker_symbol):
    if not ticker_symbol.endswith('.T'):
        ticker_symbol = f"{ticker_symbol}.T"
    
    # 日経平均（市場トレンド用）と個別株
    nk225 = yf.Ticker("^N225").history(period="5y")
    df_data = yf.Ticker(ticker_symbol).history(period="5y")
    
    if df_data.empty or nk225.empty:
        return None, None
        
    df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
    nk_df = pd.DataFrame({'Close': nk225['Close']}).dropna()
    
    # 指標計算
    nk_df['SMA25'] = nk_df['Close'].rolling(window=25).mean()
    nk_df['SMA75'] = nk_df['Close'].rolling(window=75).mean()
    nk_df['Uptrend'] = nk_df['SMA25'] > nk_df['SMA75']
    
    df['SMA5'] = df['Close'].rolling(window=5).mean()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    df['High20'] = df['High'].rolling(window=20).max()
    df['Low3'] = df['Low'].rolling(window=3).min().shift(1)
    df['RSI14'] = calculate_rsi(df['Close'], 14)
    std20 = df['Close'].rolling(window=20).std()
    df['BB_Lower'] = df['SMA20'] - (2 * std20)
    
    df.index = df.index.tz_localize(None)
    nk_df.index = nk_df.index.tz_localize(None)
    df = df.join(nk_df[['Uptrend']], how='left').ffill()
    
    return df, ticker_symbol

# --- 5. バックテスト ---
def run_backtest(df):
    t_trend, t_rev = [], []
    in_trend, in_rev = False, False
    p_trend, p_rev = 0, 0
    
    for i in range(200, len(df)):
        d = df.iloc[i]
        y = df.iloc[i-1]
        # 順張り
        if not in_trend:
            if d['Uptrend'] and d['Close'] > d['SMA200'] and y['High'] >= y['High20'] and d['Low'] <= d['SMA5']:
                in_trend, p_trend = True, d['Close']
        elif d['Close'] < d['Low3']:
            in_trend = False
            t_trend.append((d['Close'] / p_trend) - 1)
        # 逆張り
        if not in_rev:
            if d['Close'] > d['SMA200'] and d['RSI14'] < 30 and d['Close'] < d['BB_Lower']:
                in_rev, p_rev = True, d['Close']
        elif d['RSI14'] > 70 or d['Close'] <= p_rev * 0.95:
            in_rev = False
            t_rev.append((d['Close'] / p_rev) - 1)
    return t_trend, t_rev

# --- 6. 銘柄リスト自動取得 (日経225) ---
@st.cache_data(ttl=86400)
def get_nikkei225_list():
    try:
        # Wikipediaから最新の構成銘柄を取得
        url = "https://en.wikipedia.org/wiki/Nikkei_225"
        df = pd.read_html(url)[2]
        df['Ticker'] = df['Ticker'].astype(str)
        return dict(zip(df['Company'], df['Ticker']))
    except:
        return {"トヨタ": "7203", "ソフトバンクG": "9984", "ソニー": "6758"}

# --- サイドバー：銘柄選択 ---
st.sidebar.header("🔍 銘柄選択")
COMPANY_DICT = get_nikkei225_list()

selected_name = st.sidebar.selectbox(
    "銘柄名を選択（全225銘柄・検索可）", 
    options=list(COMPANY_DICT.keys())
)
ticker_input = COMPANY_DICT[selected_name]
st.sidebar.info(f"コード: {ticker_input}.T")

# --- メイン：タブ構成 ---
tab1, tab2 = st.tabs(["📊 個別分析", "🚀 全銘柄スキャン"])

with tab1:
    df, symbol = load_data(ticker_input)
    if df is not None:
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # シグナル判定
        sig = "🟢 待機"
        if latest['Uptrend'] and latest['Close'] > latest['SMA200'] and prev['High'] >= prev['High20'] and latest['Low'] <= latest['SMA5']:
            sig = "🔥 【順張り】買いシグナル！"
        elif latest['Close'] > latest['SMA200'] and latest['RSI14'] < 30 and latest['Close'] < latest['BB_Lower']:
            sig = "🚨 【逆張り】売られすぎ！買いシグナル！"
            
        st.subheader(f"判定：{sig}")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("株価", f"¥{latest['Close']:,.1f}")
        col2.metric("RSI", f"{latest['RSI14']:.1f}")
        col3.metric("トレンド", "上昇" if latest['Uptrend'] else "下落")

        if st.button("📱 LINEに送信"):
            send_line_notification(f"【株価判定】\n{selected_name}\n結果: {sig}\n価格: {latest['Close']:,.1f}円")

        st.divider()
        t_trend, t_rev = run_backtest(df)
        st.subheader("📈 バックテスト結果（過去5年）")
        c1, c2 = st.columns(2)
        with c1:
            st.write("順張り勝率:", f"{len([x for x in t_trend if x > 0])/len(t_trend)*100:.1f}%" if t_trend else "データなし")
        with c2:
            st.write("逆張り勝率:", f"{len([x for x in t_rev if x > 0])/len(t_rev)*100:.1f}%" if t_rev else "データなし")
    else:
        st.error("データ取得エラー")

with tab2:
    if st.button("🚀 日経225銘柄をスキャン開始"):
        hits = []
        pb = st.progress(0)
        items = list(COMPANY_DICT.items())
        for i, (name, code) in enumerate(items):
            pb.progress((i+1)/len(items))
            try:
                sdf, _ = load_data(code)
                if sdf is not None:
                    l, p = sdf.iloc[-1], sdf.iloc[-2]
                    s = None
                    if l['Uptrend'] and l['Close'] > l['SMA200'] and p['High'] >= p['High20'] and l['Low'] <= l['SMA5']:
                        s = "順張り🔥"
                    elif l['Close'] > l['SMA200'] and l['RSI14'] < 30 and l['Close'] < l['BB_Lower']:
                        s = "逆張り🚨"
                    if s: hits.append({"銘柄": name, "コード": code, "判定": s, "価格": l['Close']})
                time.sleep(0.1)
            except: continue
        pb.empty()
        if hits: st.table(pd.DataFrame(hits))
        else: st.info("本日のシグナルはありません。")
