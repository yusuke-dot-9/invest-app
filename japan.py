import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import datetime
import requests

# --- 1. ページ設定 ---
st.set_page_config(page_title="日本株 短期トレード判定システム", layout="wide")
st.title("🇯🇵 日本株 短期トレード判定＆バックテスト")

# --- 2. LINE通知関数（Messaging API版：2026年仕様） ---
def send_line_notification(message):
    try:
        # StreamlitのSecretsから鍵を読み込む
        if "LINE_CHANNEL_ACCESS_TOKEN" not in st.secrets or "LINE_USER_ID" not in st.secrets:
            st.warning("LINE通知の設定（Secrets）が見つかりません。")
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
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            st.success("LINEに通知を送信しました！")
        else:
            st.error(f"LINE送信失敗: {response.text}")
    except Exception as e:
        st.error(f"LINE通知エラー: {e}")

# --- 3. テクニカル指標計算関数 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 4. データ取得と計算 ---
@st.cache_data(ttl=3600)
def load_data(ticker_symbol):
    if not ticker_symbol.endswith('.T'):
        ticker_symbol = f"{ticker_symbol}.T"
        
    # 日経平均データ（トレンド判定用）
    nk225_data = yf.Ticker("^N225").history(period="5y")
    # 個別銘柄データ
    df_data = yf.Ticker(ticker_symbol).history(period="5y")
    
    if df_data.empty or nk225_data.empty:
        return None, None
        
    df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
    nk_df = pd.DataFrame({'Close': nk225_data['Close']}).dropna()
    
    # 日経平均のトレンド判定
    nk_df['SMA25'] = nk_df['Close'].rolling(window=25).mean()
    nk_df['SMA75'] = nk_df['Close'].rolling(window=75).mean()
    nk_df['Uptrend'] = nk_df['SMA25'] > nk_df['SMA75']
    
    # 個別銘柄の指標
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

# --- 5. バックテスト関数 ---
def run_backtest(df):
    trades_trend = []
    trades_reversion = []
    in_trend = False
    in_reversion = False
    entry_price_trend = 0
    entry_price_rev = 0
    
    for i in range(200, len(df)):
        today = df.iloc[i]
        yesterday = df.iloc[i-1]
        
        # 順張りロジック
        if not in_trend:
            if today['Uptrend'] and today['Close'] > today['SMA200']:
                if yesterday['High'] >= yesterday['High20'] and today['Low'] <= today['SMA5']:
                    in_trend = True
                    entry_price_trend = today['Close']
        else:
            if today['Close'] < today['Low3']:
                in_trend = False
                profit = (today['Close'] / entry_price_trend) - 1
                trades_trend.append(profit)
                
        # 逆張りロジック
        if not in_reversion:
            if today['Close'] > today['SMA200'] and today['RSI14'] < 30 and today['Close'] < today['BB_Lower']:
                in_reversion = True
                entry_price_rev = today['Close']
        else:
            if today['RSI14'] > 70 or today['Close'] <= entry_price_rev * 0.95:
                in_reversion = False
                profit = (today['Close'] / entry_price_rev) - 1
                trades_reversion.append(profit)
                
    return trades_trend, trades_reversion

# --- 6. サイドバー：日経225全銘柄リストの自動取得 ---
st.sidebar.header("🔍 銘柄選択")

@st.cache_data(ttl=86400)
def get_nikkei225_dict():
    try:
        # Wikipediaから最新の225銘柄を取得
        url = "https://en.wikipedia.org/wiki/Nikkei_225"
        dfs = pd.read_html(url)
        df = dfs[2] # 銘柄リストのテーブル
        df['Ticker'] = df['Ticker'].astype(str)
        return dict(zip(df['Company'], df['Ticker']))
    except:
        # 失敗時のバックアップ
        return {"トヨタ自動車": "7203", "ソフトバンクグループ": "9984", "ソニー": "6758"}

COMPANY_DICT = get_nikkei225_dict()

search_mode = st.sidebar.radio("検索方法", ["リストから選ぶ", "証券コードを直接入力"])

if search_mode == "リストから選ぶ":
    selected_name = st.sidebar.selectbox("日経225銘柄を選択", list(COMPANY_DICT.keys()))
    ticker_input = COMPANY_DICT[selected_name]
    st.sidebar.success(f"👉 証券コード: {ticker_input}")
else:
    ticker_input = st.sidebar.text_input("証券コード4桁を入力 (例: 7203)", value="7203")

# --- 7. メイン画面（タブ構成） ---
tab_single, tab_scan = st.tabs(["📊 個別銘柄の分析", "🚀 全銘柄シグナルスキャン"])

with tab_single:
    df, symbol = load_data(ticker_input)

    if df is not None:
        name_display = selected_name if search_mode == "リストから選ぶ" else symbol
        st.subheader(f"📊 {name_display} の分析結果")
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # シグナル判定
        signal_msg = "🟢 待機（シグナルなし）"
        is_hit = False
        
        # 順張り判定
        if latest['Uptrend'] and latest['Close'] > latest['SMA200'] and prev['High'] >= prev['High20'] and latest['Low'] <= latest['SMA5']:
            signal_msg = "🔥 【順張り】押し目買いシグナル点灯！"
            is_hit = True
        # 逆張り判定
        elif latest['Close'] > latest['SMA200'] and latest['RSI14'] < 30 and latest['Close'] < latest['BB_Lower']:
            signal_msg = "🚨 【逆張り】パニック売られすぎ！リバウンド買いシグナル！"
            is_hit = True

        st.markdown(f"### 🎯 本日のアクション：**{signal_msg}**")
        
        # 指標の表示
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("現在値", f"¥{latest['Close']:,.1f}")
        col2.metric("日経平均トレンド", "上昇中 📈" if latest['Uptrend'] else "下落中 📉")
        col3.metric("RSI (14日)", f"{latest['RSI14']:.1f}")
        col4.metric("200日線", "上" if latest['Close'] > latest['SMA200'] else "下")
        
        # LINE通知ボタン
        if st.button("📱 この結果をLINEに送信する"):
            notification_text = f"【日本株分析】\n銘柄: {name_display}\n判定: {signal_msg}\n株価: {latest['Close']:,.1f}円"
            send_line_notification(notification_text)
        
        st.divider()
        
        # バックテスト表示
        t_trend, t_rev = run_backtest(df)
        st.subheader("📈 過去5年間のバックテスト成績")
        c_trend, c_rev = st.columns(2)
        
        with c_trend:
            st.markdown("**🔥 順張り（押し目買い）**")
            if t_trend:
                win_rate = len([x for x in t_trend if x > 0]) / len(t_trend) * 100
                st.write(f"勝率: **{win_rate:.1f}%** / 平均利益: **{np.mean(t_trend)*100:.2f}%**")
            else:
                st.write("条件一致なし")
                
        with c_rev:
            st.markdown("**🚨 逆張り（リバウンド）**")
            if t_rev:
                win_rate = len([x for x in t_rev if x > 0]) / len(t_rev) * 100
                st.write(f"勝率: **{win_rate:.1f}%** / 平均利益: **{np.mean(t_rev)*100:.2f}%**")
            else:
                st.write("条件一致なし")
    else:
        st.error("データを取得できませんでした。")

with tab_scan:
    st.subheader("🕵️‍♂️ 日経225銘柄 全自動スキャン")
    if st.button("🚀 スキャンを開始（全225銘柄）"):
        progress_bar = st.progress(0)
        hit_list = []
        tickers = list(COMPANY_DICT.items())
        
        for i, (name, code) in enumerate(tickers):
            progress_bar.progress((i + 1) / len(tickers), text=f"{name} を分析中...")
            try:
                scan_df, _ = load_data(code)
                if scan_df is not None and len(scan_df) >= 2:
                    l = scan_df.iloc[-1]
                    p = scan_df.iloc[-2]
                    sig = None
                    if l['Uptrend'] and l['Close'] > l['SMA200'] and p['High'] >= p['High20'] and l['Low'] <= l['SMA5']:
                        sig = "🔥 順張り"
                    elif l['Close'] > l['SMA200'] and l['RSI14'] < 30 and l['Close'] < l['BB_Lower']:
                        sig = "🚨 逆張り"
                    
                    if sig:
                        hit_list.append({"銘柄名": name, "コード": code, "シグナル": sig, "価格": f"{l['Close']:,.1f}円"})
                time.sleep(0.1) # サーバー負荷軽減
            except:
                continue
                
        progress_bar.empty()
        if hit_list:
            st.success(f"🎉 {len(hit_list)} 銘柄でシグナル発見！")
            st.table(pd.DataFrame(hit_list))
            # スキャン結果をLINEに送る
            if st.button("📱 スキャン結果をLINEに送る"):
                res_msg = "【本日のシグナル点灯銘柄】\n" + "\n".join([f"・{h['銘柄名']}({h['シグナル']})" for h in hit_list])
                send_line_notification(res_msg)
        else:
            st.info("本日はシグナル点灯銘柄はありませんでした。")
