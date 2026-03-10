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

# --- サイドバー入力（会社名検索機能） ---
st.sidebar.header("🔍 銘柄選択")

# よく使う銘柄の辞書（ここを自由に増やせます！）
COMPANY_DICT = {
    "トヨタ自動車": "7203", "ソフトバンクグループ": "9984", "東京エレクトロン": "8035",
    "ファーストリテイリング（ユニクロ）": "9983", "ソニーグループ": "6758", "三菱UFJ": "8306",
    "任天堂": "7974", "キーエンス": "6861", "信
