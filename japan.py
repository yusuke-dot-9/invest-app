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

@st.cache_data(ttl=86400) # 1日1回だけ最新リストを自動取得
def get_nikkei225_dict():
    try:
        url = "https://ja.wikipedia.org/wiki/%E6%97%A5%E7%B5%8C%E5%B9%B3%E5%9D%87%E6%A0%AA%E4%BE%A1%E3%81%AE%E6%A7%8B%E6%88%90%E9%8A%98%E6%9F%84%E4%B8%80%E8%A6%A7"
        dfs = pd.read_html(url)
        for df in dfs:
            if 'コード' in df.columns and '銘柄名' in df.columns:
                df['コード'] = df['コード'].astype(str)
                return dict(zip(df['銘柄名'], df['コード']))
    except Exception as e:
        st.sidebar.warning("Wikipediaからの自動取得に失敗しました。予備の主要銘柄リストを使用します。")
        pass
        
    # Wikipedia取得失敗時の強力な予備リスト（主要50社以上）
    return {
        "トヨタ自動車": "7203", "ソニーグループ": "6758", "三菱UFJFG": "8306", "キーエンス": "6861",
        "東京エレクトロン": "8035", "信越化学工業": "4063", "三井住友FG": "8316", "日立製作所": "6501",
        "伊藤忠商事": "8001", "三菱商事": "8058", "ソフトバンクグループ": "9984", "ホンダ": "7267",
        "武田薬品工業": "4502", "KDDI": "9433", "ファーストリテイリング": "9983", "任天堂": "7974",
        "三井物産": "8031", "ダイキン工業": "6367", "みずほFG": "8411", "リクルートHD": "6098",
        "第一三共": "4568", "デンソー": "6902", "日本電信電話": "9432", "アステラス製薬": "4503",
        "村田製作所": "6981", "丸紅": "8002", "オリックス": "8591", "パナソニックHD": "6752",
        "小松製作所": "6301", "富士フイルムHD": "4901", "ブリヂストン": "5108", "アサヒグループHD": "2502",
        "キヤノン": "7751", "セブン＆アイHD": "3382", "日本たばこ産業(JT)": "2914", "花王": "4452",
        "中外製薬": "4519", "ニデック": "6594", "アドバンテスト": "6857", "ファナック": "6954",
        "SMC": "6273", "ディスコ": "6146", "ルネサスエレクトロニクス": "6723", "コマツ": "6301",
        "スズキ": "7269", "マツダ": "7261", "日産自動車": "7201", "SUBARU": "7270", "三菱地所": "8802"
    }

COMPANY_DICT = get_nikkei225_dict()

search_mode = st.sidebar.radio("検索方法", ["リストから選ぶ", "証券コードを直接入力"])

if search_mode == "リストから選ぶ":
    selected_name = st.sidebar.selectbox("会社名を選択（文字入力で絞り込み可）", list(COMPANY_DICT.keys()))
    ticker_input = COMPANY_DICT[selected_name]
    st.sidebar.success(f"👉 証券コード: {ticker_input}")
else:
    ticker_input = st.sidebar.text_input("証券コード4桁を入力 (例: 7203)", value="7203")

# --- メイン画面 ---
df, symbol = load_data(ticker_input)

if df is not None:
    st.subheader(f"📊 {symbol} ({selected_name if search_mode == 'リストから選ぶ' else ''}) の分析結果")
    latest = df.iloc[-1]
    
    signal_msg = "🟢 待機（シグナルなし）"
    if latest['Uptrend'] and latest['Close'] > latest['SMA200'] and df.iloc[-2]['High'] >= df.iloc[-2]['High20'] and latest['Low'] <= latest['SMA5']:
        signal_msg = "🔥 【順張り】押し目買いシグナル点灯！"
    elif latest['Close'] > latest['SMA200'] and latest['RSI14'] < 30 and latest['Close'] < latest['BB_Lower']:
        signal_msg = "🚨 【逆張り】パニック売られすぎ！リバウンド買いシグナル！"

    st.markdown(f"### 🎯 本日の
