import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ページ設定
st.set_page_config(page_title="デイリー投資ダッシュボード", layout="wide")
st.title("🚀 投資判定ダッシュボード v2.0")

# --- データ取得と計算（キャッシュ化） ---
@st.cache_data(ttl=3600)
def load_data():
    # yf.downloadから、エラーが起きにくいyf.Ticker().historyに変更
    tqqq_data = yf.Ticker("TQQQ").history(period="5y")
    vix_data = yf.Ticker("^VIX").history(period="5y")
    
    # データフレーム結合
    df = pd.DataFrame({
        'TQQQ': tqqq_data['Close'],
        'VIX': vix_data['Close']
    }).dropna()
    
    # タイムゾーンのズレによるエラーを防ぐ
    df.index = df.index.tz_localize(None)
    
    # 指標の計算
    df['SMA25'] = df['TQQQ'].rolling(window=25).mean()
    df['SMA200'] = df['TQQQ'].rolling(window=200).mean()
    df['High20'] = df['TQQQ'].rolling(window=20).max()
    df['Drawdown'] = (df['TQQQ'] - df['High20']) / df['High20'] * 100
    
    # シグナル判定（大暴落キャッチ: VIX>30 & 200日線の80%未満）
    df['Buy_Signal'] = (df['VIX'] >= 30) & (df['TQQQ'] < df['SMA200'] * 0.8)
    
    return df

try:
    df = load_data()
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    # --- 判定ロジック ---
    signal = "🟢 待機（トレンドフォロー継続）"
    if (latest['VIX'] >= 30) and (latest['TQQQ'] < latest['SMA200'] * 0.8):
        signal = "🚨 大暴落キャッチ（全力買いシグナル）"
    elif latest['Drawdown'] <= -25:
        signal = "🔴 トレイリングストップ（即撤退・損切り）"
    elif (prev['TQQQ'] <= prev['SMA25']) and (latest['TQQQ'] > latest['SMA25']):
        signal = "🔥 爆速買い戻し（強気トレンド入り）"

    # --- UI表示：タブ分け ---
    tab1, tab2 = st.tabs(["📊 本日のTQQQ判定＆資金管理", "📈 バックテスト（過去の勝率）"])

    with tab1:
        st.subheader("💡 今日の相場状況")
        col1, col2, col3 = st.columns(3)
        col1.metric("TQQQ 現在値", f"${latest['TQQQ']:.2f}", f"{latest['TQQQ'] - prev['TQQQ']:.2f} (前日比)")
        col2.metric("VIX (恐怖指数)", f"{latest['VIX']:.2f}", "30以上でパニック")
        col3.metric("直近20日高値からの下落率", f"{latest['Drawdown']:.1f}%", "-25%で撤退")
        
        st.markdown(f"### 本日のアクション指示：**{signal}**")
        st.divider()
        
        # --- C機能：適正ポジション（
