import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

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
    except:
        pass
    return {
        "トヨタ自動車": "7203", "ソニーグループ": "6758", "三菱UFJFG": "8306", "キーエンス": "6861",
        "東京エレクトロン": "8035", "信越化学工業": "4063", "三井住友FG": "8316", "日立製作所": "6501",
        "伊藤忠商事": "8001", "三菱商事": "8058", "ソフトバンクグループ": "9984", "ホンダ": "7267",
        "武田薬品工業": "4502", "KDDI": "9433", "ファーストリテイリング": "9983", "任天堂": "7974"
    }

COMPANY_DICT = get_nikkei225_dict()

search_mode = st.sidebar.radio("検索方法", ["リストから選ぶ", "証券コードを直接入力"])

if search_mode == "リストから選ぶ":
    selected_name = st.sidebar.selectbox("会社名を選択（文字入力で絞り込み可）", list(COMPANY_DICT.keys()))
    ticker_input = COMPANY_DICT[selected_name]
    st.sidebar.success(f"👉 証券コード: {ticker_input}")
else:
    ticker_input = st.sidebar.text_input("証券コード4桁を入力 (例: 7203)", value="7203")

# --- メイン画面（タブ分け） ---
tab_single, tab_scan = st.tabs(["📊 個別銘柄の分析", "🚀 全銘柄シグナルスキャン"])

with tab_single:
    df, symbol = load_data(ticker_input)

    if df is not None:
        st.subheader(f"📊 {symbol} ({selected_name if search_mode == 'リストから選ぶ' else ''}) の分析結果")
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
        
        c_trend, c_rev = st.columns(2)
        with c_trend:
            st.markdown("**🔥 順張り（ブレイク＆押し目）**")
            if len(t_trend) > 0:
                win_rate = len([x for x in t_trend if x > 0]) / len(t_trend) * 100
                avg_return = np.mean(t_trend) * 100
                st.write(f"勝率: **{win_rate:.1f}%** (全{len(t_trend)}回) / 平均利益: **{avg_return:.2f}%**")
            else:
                st.write("過去5年で条件一致なし")
                
        with c_rev:
            st.markdown("**🚨 逆張り（リバウンド狙い）**")
            if len(t_rev) > 0:
                win_rate = len([x for x in t_rev if x > 0]) / len(t_rev) * 100
                avg_return = np.mean(t_rev) * 100
                st.write(f"勝率: **{win_rate:.1f}%** (全{len(t_rev)}回) / 平均利益: **{avg_return:.2f}%**")
            else:
                st.write("過去5年で条件一致なし")
    else:
        st.error("データを取得できませんでした。")

with tab_scan:
    st.subheader("🕵️‍♂️ お宝銘柄 全自動スキャン")
    st.write("リスト内の全銘柄をチェックし、本日「買いシグナル」が点灯している銘柄だけを抽出します。")
    
    if st.button("🚀 スキャンを開始する（数分かかります）"):
        progress_text = "データを取得・分析中..."
        my_bar = st.progress(0, text=progress_text)
        
        hit_list = []
        tickers = list(COMPANY_DICT.items())
        total_tickers = len(tickers)
        
        # エラーを出さないように少しずつ進める
        for i, (name, code) in enumerate(tickers):
            # 進捗バーの更新
            progress_percent = int(((i + 1) / total_tickers) * 100)
            my_bar.progress(progress_percent, text=f"{progress_percent}% 完了 ({name} を確認中...)")
            
            try:
                # データの読み込み
                scan_df, _ = load_data(code)
                if scan_df is not None and len(scan_df) >= 200:
                    latest_scan = scan_df.iloc[-1]
                    prev_scan = scan_df.iloc[-2]
                    
                    signal = None
                    # 順張り判定
                    if latest_scan['Uptrend'] and latest_scan['Close'] > latest_scan['SMA200'] and prev_scan['High'] >= prev_scan['High20'] and latest_scan['Low'] <= latest_scan['SMA5']:
                        signal = "🔥 順張り（押し目買い）"
                    # 逆張り判定
                    elif latest_scan['Close'] > latest_scan['SMA200'] and latest_scan['RSI14'] < 30 and latest_scan['Close'] < latest_scan['BB_Lower']:
                        signal = "🚨 逆張り（リバウンド）"
                        
                    if signal:
                        hit_list.append({
                            "銘柄名": name,
                            "コード": code,
                            "シグナル": signal,
                            "現在値": f"¥{latest_scan['Close']:.1f}"
                        })
                # アクセス制限回避のため0.2秒待機
                time.sleep(0.2)
            except:
                pass # エラーが起きた銘柄はスキップ
                
        my_bar.empty() # スキャン完了でバーを消す
        
        if hit_list:
            st.success(f"🎉 スキャン完了！本日シグナルが点灯しているのは以下の {len(hit_list)} 銘柄です。")
            st.table(pd.DataFrame(hit_list))
            st.info("※気になる銘柄を見つけたら、「個別銘柄の分析」タブにコードを入力してバックテストの勝率を確認してください！")
        else:
            st.info("スキャン完了。残念ながら、本日はシグナルが点灯している銘柄はありませんでした。")
