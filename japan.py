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
    if not ticker_symbol.endswith('.T'):
        ticker_symbol = f"{ticker_symbol}.T"
        
    nk225_data = yf.Ticker("^N225").history(period="5y")
    df_data = yf.Ticker(ticker_symbol).history(period="5y")
    
    if df_data.empty or nk225_data.empty:
        return None, None
        
    df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
    
    nk_df = pd.DataFrame({'Close': nk225_data['Close']}).dropna()
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
    df = df.join(nk_df[['Uptrend']], how='left').fillna(method='ffill')
    
    return df, ticker_symbol

# --- バックテスト関数 ---
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

# --- サイドバー入力（日経225自動取得機能） ---
st.sidebar.header("🔍 銘柄選択")

@st.cache_data(ttl=86400) # 1日1回だけ最新リストを自動取得（負荷軽減）
def get_nikkei225_dict():
    try:
        # Wikipediaから最新の日経225構成銘柄一覧を自動で読み取る
        url = "https://ja.wikipedia.org/wiki/%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%E6%A0%AA%E4%BE%A1%E3%81%AE%E6%A7%8B%E6%88%90%E9%8A%98%E6%9F%84%E4%B8%80%E8%A6%A7"
        dfs = pd.read_html(url)
        for df in dfs:
            if 'コード' in df.columns and '銘柄名' in df.columns:
                df['コード'] = df['コード'].astype(str)
                return dict(zip(df['銘柄名'], df['コード']))
    except:
        pass
    # 万が一、Wikipediaの構成が変わって読み取れなかった時の予備リスト
    return {"トヨタ自動車": "7203", "ソフトバンクグループ": "9984", "東京エレクトロン": "8035"}

COMPANY_DICT = get_nikkei225_dict()

search_mode = st.sidebar.radio("検索方法", ["リストから選ぶ（日経225全銘柄）", "証券コードを直接入力"])

if search_mode == "リストから選ぶ（日経225全銘柄）":
    # 225社すべてが格納されたドロップダウン
    selected_name = st.sidebar.selectbox("会社名を選択（文字入力で絞り込み可）", list(COMPANY_DICT.keys()))
    ticker_input = COMPANY_DICT[selected_name]
    st.sidebar.success(f"👉 証券コード: {ticker_input}")
else:
    ticker_input = st.sidebar.text_input("証券コード4桁を入力 (例: 7203)", value="7203")

# --- メイン画面 ---
df, symbol = load_data(ticker_input)

if df is not None:
    st.subheader(f"📊 {symbol} ({selected_name if search_mode == 'リストから選ぶ（日経225全銘柄）' else ''}) の分析結果")
    latest = df.iloc[-1]
    
    signal_msg = "🟢 待機（シグナルなし）"
    if latest['Uptrend'] and latest['Close'] > latest['SMA200'] and df.iloc[-2]['High'] >= df.iloc[-2]['High20'] and latest['Low'] <= latest['SMA5']:
        signal_msg = "🔥 【順張り】押し目買いシグナル点灯！"
    elif latest['Close'] > latest['SMA200'] and latest['RSI14'] < 30 and latest['Close'] < latest['BB_Lower']:
        signal_msg = "🚨 【逆張り】パニック売られすぎ！リバウンド買いシグナル！"

    st.markdown(f"### 🎯 本日のアクション：**{signal_msg}**")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("現在値", f"¥{latest['Close']:.1f}")
    col2.metric("日経平均トレンド", "上昇中 📈" if latest['Uptrend'] else "下落中 📉")
    col3.metric("RSI (14日)", f"{latest['RSI14']:.1f}", "30以下で売られすぎ")
    col4.metric("200日線との関係", "上（長期強気）" if latest['Close'] > latest['SMA200'] else "下（長期弱気）")
    
    st.divider()
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
