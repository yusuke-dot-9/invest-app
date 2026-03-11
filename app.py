import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# ページ設定
st.set_page_config(page_title="デイリー投資ダッシュボード", layout="wide")
st.title("🚀 投資判定ダッシュボード v2.1")

# LINE通知関数
def send_line_notification(message):
    try:
        token = st.secrets["LINE_NOTIFY_TOKEN"]
        url = "https://notify-api.line.me/api/notify"
        headers = {"Authorization": f"Bearer {token}"}
        data = {"message": message}
        requests.post(url, headers=headers, data=data)
    except:
        st.error("LINE通知の設定が見つかりません。Secretsを確認してください。")

# --- データ取得と計算 ---
@st.cache_data(ttl=3600)
def load_data():
    tqqq_data = yf.Ticker("TQQQ").history(period="5y")
    vix_data = yf.Ticker("^VIX").history(period="5y")
    df = pd.DataFrame({'TQQQ': tqqq_data['Close'], 'VIX': vix_data['Close']}).dropna()
    df.index = df.index.tz_localize(None)
    df['SMA25'] = df['TQQQ'].rolling(window=25).mean()
    df['SMA200'] = df['TQQQ'].rolling(window=200).mean()
    df['High20'] = df['TQQQ'].rolling(window=20).max()
    df['Drawdown'] = (df['TQQQ'] - df['High20']) / df['High20'] * 100
    df['Buy_Signal'] = (df['VIX'] >= 30) & (df['TQQQ'] < df['SMA200'] * 0.8)
    return df

try:
    df = load_data()
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # 判定ロジック
    signal = "🟢 待機"
    if (latest['VIX'] >= 30) and (latest['TQQQ'] < latest['SMA200'] * 0.8):
        signal = "🚨 大暴落キャッチ（全力買い！）"
    elif latest['Drawdown'] <= -25:
        signal = "🔴 損切り・撤退"
    elif (prev['TQQQ'] <= prev['SMA25']) and (latest['TQQQ'] > latest['SMA25']):
        signal = "🔥 爆速買い戻し（強気入り）"

    # UI表示
    st.subheader(f"判定：{signal}")
    col1, col2 = st.columns(2)
    col1.metric("TQQQ", f"${latest['TQQQ']:.2f}")
    col2.metric("VIX", f"{latest['VIX']:.2f}")

    # LINE送信ボタン
    if st.button("📱 今日の判定をLINEに送信する"):
        msg = f"\n【TQQQ投資判定】\n判定：{signal}\n価格：${latest['TQQQ']:.2f}\nVIX：{latest['VIX']:.2f}\n下落率：{latest['Drawdown']:.1f}%"
        send_line_notification(msg)
        st.success("LINEに通知を送りました！")

except Exception as e:
    st.error(f"エラー：{e}")
