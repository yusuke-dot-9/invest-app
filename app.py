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
    # 過去5年分のデータを取得（バックテスト用）
    tqqq = yf.download("TQQQ", period="5y", progress=False)['Close']
    vix = yf.download("^VIX", period="5y", progress=False)['Close']
    
    # データフレーム結合
    df = pd.DataFrame({'TQQQ': tqqq, 'VIX': vix}).dropna()
    
    # 指標の計算
    df['SMA25'] = df['TQQQ'].rolling(window=25).mean()
    df['SMA200'] = df['TQQQ'].rolling(window=200).mean()
    df['High20'] = df['TQQQ'].rolling(window=20).max()
    df['Drawdown'] = (df['TQQQ'] - df['High20']) / df['High20'] * 100
    
    # シグナル判定（大暴落キャッチ: VIX>30 & 200日線の80%未満）
    df['Buy_Signal'] = (df['VIX'] >= 30) & (df['TQQQ'] < df['SMA200'] * 0.8)
    
    return df

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
    
    st.markdown(f"### 本日のアクション指示：{signal}")
    st.divider()
    
    # --- C機能：適正ポジション（資金管理）計算 ---
    st.subheader("🛡️ 適正ポジション（購入株数）計算機")
    st.write("「許容できる最大損失額」から、安全な購入金額と株数を自動計算します。")
    
    capital = st.number_input("投資待機資金を入力してください（円）", value=1000000, step=100000)
    risk_pct = st.slider("1回のトレードで許容する最大損失（%）", min_value=1.0, max_value=10.0, value=2.0, step=0.5)
    
    # 計算ロジック: 25%下落で損切りとした場合、総資金のrisk_pct%を失うための購入金額
    # 例：100万円の2%（2万円）の損失を許容。25%下落で2万円失うなら、購入金額は8万円。
    max_loss_yen = capital * (risk_pct / 100)
    safe_invest_amount = max_loss_yen / 0.25  # 25%下落想定
    estimated_shares = safe_invest_amount / (latest['TQQQ'] * 150) # 1ドル=150円換算
    
    col_a, col_b = st.columns(2)
    col_a.info(f"💰 今回の安全な購入金額：**約 {int(safe_invest_amount):,} 円**")
    col_b.success(f"📦 購入目安株数：**約 {int(estimated_shares)} 株**")
    st.caption("※為替レートは1ドル=150円で概算しています。撤退ライン（-25%）を守る限り、総資金の致命傷は避けられます。")

with tab2:
    # --- B機能：バックテスト可視化 ---
    st.subheader("📊 過去5年間のシグナル成績（大暴落キャッチ）")
    st.write("過去5年間で「🚨大暴落キャッチ」の条件を満たした日に買い、20営業日後に売却した場合の成績です。")
    
    # 20日後のリターンを計算
    df['Return_20d'] = df['TQQQ'].shift(-20) / df['TQQQ'] - 1
    trades = df[df['Buy_Signal']].dropna(subset=['Return_20d'])
    
    if len(trades) > 0:
        win_trades = trades[trades['Return_20d'] > 0]
        win_rate = (len(win_trades) / len(trades)) * 100
        avg_return = trades['Return_20d'].mean() * 100
        
        c1, c2, c3 = st.columns(3)
        c1.metric("過去のエントリー回数", f"{len(trades)} 回")
        c2.metric("勝率（20日後プラス）", f"{win_rate:.1f} %")
        c3.metric("平均リターン（20日後）", f"+{avg_return:.1f} %")
        
        st.line_chart(trades['Return_20d'] * 100)
        st.caption("グラフは各エントリーから20日後の騰落率（%）を示しています。")
    else:
        st.write("過去5年間でこの厳しい暴落条件を満たした日はありませんでした。")
