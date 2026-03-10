import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# --- ページ設定 ---
st.set_page_config(page_title="日本株 短期トレード判定システム", layout="wide")
st.title("🇯🇵 日本株 短期トレード判定＆バックテスト")

# --- テクニカル指標計算関数 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- データ取得と計算 ---
@st.cache_data(ttl=3600)
def load_data(ticker_symbol):
    # 日本株は「コード.T」にする必要があるため整形
    if not ticker_symbol.endswith('.T'):
        ticker_symbol = f"{ticker_symbol}.T"
        
    # 日経平均と個別銘柄のデータを過去5年分取得
    nk225 = yf.download("^N225", period="5y", progress=False)['Close']
    df = yf.download(ticker_symbol, period="5y", progress=False)
    
    if df.empty:
        return None, None
        
    df = df[['Open', 'High', 'Low', 'Close']].dropna()
    
    # 日経平均の指標
    nk_df = pd.DataFrame({'Close': nk225}).dropna()
    nk_df['SMA25'] = nk_df['Close'].rolling(window=25).mean()
    nk_df['SMA75'] = nk_df['Close'].rolling(window=75).mean()
    nk_df['Uptrend'] = nk_df['SMA25'] > nk_df['SMA75']
    
    # 個別銘柄の指標
    df['SMA5'] = df['Close'].rolling(window=5).mean()
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA200'] = df['Close'].rolling(window=200).mean()
    
    # 順張り用：20日高値、3日安値
    df['High20'] = df['High'].rolling(window=20).max()
    df['Low3'] = df['Low'].rolling(window=3).min().shift(1) # 前日までの3日間安値
    
    # 逆張り用：RSI、ボリンジャーバンド
    df['RSI14'] = calculate_rsi(df['Close'], 14)
    std20 = df['Close'].rolling(window=20).std()
    df['BB_Lower'] = df['SMA20'] - (2 * std20)
    
    # 日経平均のトレンドを結合
    df = df.join(nk_df[['Uptrend']], how='left').fillna(method='ffill')
    
    return df, ticker_symbol

# --- バックテスト関数 ---
def run_backtest(df):
    trades_trend = []
    trades_reversion = []
    
    in_trend = False
    in_reversion = False
    entry_price_rev = 0
    
    for i in range(200, len(df)):
        today = df.iloc[i]
        yesterday = df.iloc[i-1]
        
        # --- ロジック1：順張り（アイデアB出口） ---
        if not in_trend:
            # 買い条件: 日経上昇、200日線上、直近20日高値更新後、5日線まで押した
            if today['Uptrend'] and today['Close'] > today['SMA200']:
                if yesterday['High'] >= yesterday['High20'] and today['Low'] <= today['SMA5']:
                    in_trend = True
                    entry_price_trend = today['Close']
        else:
            # 売り条件: 前日までの3日間安値を下回った（トレイリングストップ）
            if today['Close'] < today['Low3']:
                in_trend = False
                profit = (today['Close'] / entry_price_trend) - 1
                trades_trend.append(profit)
                
        # --- ロジック2：逆張り（アイデアA出口） ---
        if not in_reversion:
            # 買い条件: 200日線上、RSI<30、BB-2σ以下
            if today['Close'] > today['SMA200'] and today['RSI14'] < 30 and today['Close'] < today['BB_Lower']:
                in_reversion = True
                entry_price_rev = today['Close']
        else:
            # 売り条件: RSI>70 または -5%損切
            if today['RSI14'] > 70 or today['Close'] <= entry_price_rev * 0.95:
                in_reversion = False
                profit = (today['Close'] / entry_price_rev) - 1
                trades_reversion.append(profit)
                
    return trades_trend, trades_reversion

# --- サイドバー入力 ---
st.sidebar.header("🔍 銘柄選択")
ticker_input = st.sidebar.text_input("証券コードを入力 (例: 7203, 9984, 8035)", value="7203")
st.sidebar.caption("※日本の証券コード4桁を入力してください。")

# --- メイン画面 ---
df, symbol = load_data(ticker_input)

if df is not None:
    st.subheader(f"📊 {symbol} の分析結果")
    latest = df.iloc[-1]
    
    # 今日のシグナル判定
    signal_msg = "🟢 待機（シグナルなし）"
    
    # 順張りシグナル
    if latest['Uptrend'] and latest['Close'] > latest['SMA200'] and df.iloc[-2]['High'] >= df.iloc[-2]['High20'] and latest['Low'] <= latest['SMA5']:
        signal_msg = "🔥 【順張り】押し目買いシグナル点灯！"
        
    # 逆張りシグナル
    elif latest['Close'] > latest['SMA200'] and latest['RSI14'] < 30 and latest['Close'] < latest['BB_Lower']:
        signal_msg = "🚨 【逆張り】パニック売られすぎ！リバウンド買いシグナル！"

    st.markdown(f"### 🎯 本日のアクション：**{signal_msg}**")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("現在値", f"¥{latest['Close']:.1f}")
    col2.metric("日経平均トレンド", "上昇中 📈" if latest['Uptrend'] else "下落中 📉")
    col3.metric("RSI (14日)", f"{latest['RSI14']:.1f}", "30以下で売られすぎ")
    col4.metric("200日線との関係", "上（長期強気）" if latest['Close'] > latest['SMA200'] else "下（長期弱気）")
    
    st.divider()
    
    # バックテスト実行
    t_trend, t_rev = run_backtest(df)
    
    st.subheader("📈 過去5年間のバックテスト成績")
    
    tab1, tab2 = st.tabs(["🔥 順張り（ブレイク＆押し目）", "🚨 逆張り（リバウンド狙い）"])
    
    with tab1:
        st.write("【出口戦略】3日間安値を下回るまでホールド（トレイリングストップ）")
        if len(t_trend) > 0:
            win_rate = len([x for x in t_trend if x > 0]) / len(t_trend) * 100
            avg_return = np.mean(t_trend) * 100
            c1, c2, c3 = st.columns(3)
            c1.metric("トレード回数", f"{len(t_trend)} 回")
            c2.metric("勝率", f"{win_rate:.1f} %")
            c3.metric("1回あたりの平均利益", f"{avg_return:.2f} %")
        else:
            st.write("過去5年間で条件に一致するトレードはありませんでした。")
            
    with tab2:
        st.write("【出口戦略】RSI70で利確 / -5%で損切")
        if len(t_rev) > 0:
            win_rate = len([x for x in t_rev if x > 0]) / len(t_rev) * 100
            avg_return = np.mean(t_rev) * 100
            c1, c2, c3 = st.columns(3)
            c1.metric("トレード回数", f"{len(t_rev)} 回")
            c2.metric("勝率", f"{win_rate:.1f} %")
            c3.metric("1回あたりの平均利益", f"{avg_return:.2f} %")
        else:
            st.write("過去5年間で条件に一致するトレードはありませんでした。")

else:
    st.error("データを取得できませんでした。正しい証券コードを入力してください。")
