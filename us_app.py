import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time

# --- 1. ページ設定 ---
st.set_page_config(page_title="US株・FANG+ 判定ダッシュボード", layout="wide")
st.title("🇺🇸 米国株＆FANG+ 投資判定ダッシュボード")

# --- 2. データ取得関数 ---
@st.cache_data(ttl=3600)
def load_us_data(ticker_symbol):
    try:
        vix_data = yf.download("^VIX", period="5y", progress=False)
        df_data = yf.download(ticker_symbol, period="5y", progress=False)
        
        if df_data.empty or vix_data.empty: 
            return None, None
            
        if isinstance(df_data.columns, pd.MultiIndex):
            df_data.columns = df_data.columns.get_level_values(0)
        if isinstance(vix_data.columns, pd.MultiIndex):
            vix_data.columns = vix_data.columns.get_level_values(0)

        df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
        vix = pd.DataFrame({'VIX': vix_data['Close']}).dropna()
        
        df.index = df.index.tz_localize(None)
        vix.index = vix.index.tz_localize(None)
        
        df['SMA25'] = df['Close'].rolling(window=25).mean()
        df['SMA200'] = df['Close'].rolling(window=200).mean()
        df['High20'] = df['High'].rolling(window=20).max()
        df['Drawdown_from_High20'] = (df['Close'] - df['High20']) / df['High20']
        
        df = df.join(vix, how='left').ffill()
        return df, ticker_symbol
    except Exception:
        return None, None

# --- 3. ファンダメンタル成長率の取得 ---
@st.cache_data(ttl=86400)
def get_fundamental_growth(ticker_symbol):
    if ticker_symbol in ["TQQQ", "SOXL", "QQQ", "SPY"]:
        return None, None, None
    try:
        t = yf.Ticker(ticker_symbol)
        inc = t.income_stmt
        if inc is None or inc.empty:
            inc = t.financials
        if inc is None or inc.empty:
            return None, None, None
            
        targets = [
            {"name": "純利益", "keywords": ["net income common", "net income"]},
            {"name": "営業利益", "keywords": ["operating income", "ebit"]},
            {"name": "売上高", "keywords": ["total revenue", "revenue"]}
        ]
        
        for target in targets:
            target_row = None
            for row_name in inc.index:
                row_lower = str(row_name).lower()
                for kw in target["keywords"]:
                    if kw in row_lower:
                        target_row = row_name
                        break
                if target_row:
                    break
                    
            if target_row:
                series = inc.loc[target_row].dropna()
                if len(series) >= 2:
                    latest_val = float(series.iloc[0])
                    oldest_val = float(series.iloc[-1])
                    if oldest_val <= 0 or latest_val <= 0: continue
                    growth = (latest_val / oldest_val) - 1
                    return growth, len(series), target["name"]
        return None, None, None
    except:
        return None, None, None

# --- 4. 判定ロジック ---
def get_tqqq_signal(latest, prev):
    if latest['VIX'] >= 30 and latest['Close'] < (latest['SMA200'] * 0.8):
        return "🚨 大暴落キャッチ（全力買い）", "今すぐ全力買い・ナンピンのタイミングです"
    elif latest['Drawdown_from_High20'] <= -0.25:
        return "🔴 トレイリングストップ", "直近高値から25%下落。即撤退・損切り推奨です"
    elif prev['Close'] <= prev['SMA25'] and latest['Close'] > latest['SMA25']:
        return "🔥 爆速買い戻し", "上昇トレンド入り（ゴールデンクロス）。買い戻し推奨です"
    else:
        return "🟢 待機", "現状維持・継続ホールド"

# --- 5. 米国株＆FANG+ 銘柄リスト ---
US_TICKERS = {
    "TQQQ (ナスダック3倍ブル)": "TQQQ",
    "SOXL (半導体3倍ブル)": "SOXL",
    "QQQ (ナスダック100)": "QQQ",
    "SPY (S&P500)": "SPY",
    "--- 監視対象銘柄 ---": "",
    "NVDA (エヌビディア)": "NVDA",
    "AAPL (アップル)": "AAPL",
    "MSFT (マイクロソフト)": "MSFT",
    "AMZN (アマゾン)": "AMZN",
    "META (メタ/Facebook)": "META",
    "GOOGL (アルファベット/Google)": "GOOGL",
    "NFLX (ネットフリックス)": "NFLX",
    "AVGO (ブロードコム)": "AVGO",
    "CRWD (クラウドストライク)": "CRWD",
    "PLTR (パランティア)": "PLTR",
    "TSLA (テスラ)": "TSLA"
}
valid_options = {k: v for k, v in US_TICKERS.items() if v != ""}

# --- サイドバー ---
st.sidebar.header("🔍 銘柄選択")
selected_name = st.sidebar.selectbox("詳細を分析する銘柄を選択", options=list(valid_options.keys()))
ticker_code = valid_options[selected_name]

st.sidebar.write("---")
if st.sidebar.button("🔄 データを最新に更新（エラー解消）"):
    st.cache_data.clear()
    st.sidebar.success("キャッシュを消去しました！画面をリロードします...")
    time.sleep(1.5)
    st.rerun()

# --- 6. メインコンテンツ（タブ分け） ---
tab1, tab2 = st.tabs(["📊 個別銘柄の詳細分析", "🚀 全銘柄シグナル一覧（スキャン）"])

with tab1:
    df, symbol = load_us_data(ticker_code)

    if df is not None:
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        signal_title, action_msg = get_tqqq_signal(latest, prev)
        
        st.markdown(f"## 🎯 本日の判定：**{signal_title}**")
        st.info(f"**アクション指示：** {action_msg}")
        st.write("---")
        
        max_price_5y = df['High'].max()
        drawdown_from_max = ((latest['Close'] / max_price_5y) - 1) * 100
        
        st.markdown("### 📊 テクニカル指標 ＆ 最高値チェック")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("現在値 (USD)", f"${latest['Close']:,.2f}")
        c2.metric("過去5年の最高値", f"${max_price_5y:,.2f}")
        c3.metric("最高値からの下落率", f"{drawdown_from_max:+.1f}%", "高値圏" if drawdown_from_max >= -5 else "調整中")
        
        st.write("")
        
        c4, c5, c6 = st.columns(3)
        c4.metric("VIX (恐怖指数)", f"{latest['VIX']:.2f}", "30以上で警戒" if latest['VIX']>=30 else "安定")
        dd_percent = latest['Drawdown_from_High20'] * 100
        c5.metric("直近20日高値からの下落率", f"{dd_percent:.1f}%", "-25%で損切り" if dd_percent <= -25 else "安全")
        sma200_dist = ((latest['Close'] / latest['SMA200']) - 1) * 100
        c6.metric("200日線との乖離率", f"{sma200_dist:+.1f}%", "-20%以下でバーゲン" if sma200_dist <= -20 else "")

        st.write("---")

        st.markdown("### 📈 株価トレンド（過去1年間）")
        chart_df = df[['Close', 'SMA25', 'SMA200']].tail(252).copy()
        chart_df.columns = ['終値 (Close)', '25日線 (短期)', '200日線 (長期)']
        st.line_chart(chart_df)
        st.caption("※ 青線が現在の株価です。緑色の200日線を下回ると長期的な下落トレンド、上回ると上昇トレンドの目安になります。")

        st.write("---")

        st.markdown("### 🏢 株価成長 vs 企業成長（ファンダメンタル乖離率）")
        if ticker_code in ["TQQQ", "SOXL", "QQQ", "SPY"]:
            st.write("※ETF（指数）のため、企業業績データはありません。")
        else:
            growth_rate, years_count, metric_name = get_fundamental_growth(ticker_code)
            
            if growth_rate is not None:
                lookback_days = min(len(df)-1, int(252 * (years_count - 1)))
                price_old = df['Close'].iloc[-(lookback_days + 1)]
                price_new = latest['Close']
                price_growth = (price_new / price_old) - 1
                divergence = price_growth - growth_rate
                
                c1, c2, c3 = st.columns(3)
                c1.metric(f"過去{years_count}年の株価上昇率", f"{price_growth*100:+.1f}%")
                c2.metric(f"過去{years_count}年の{metric_name}成長率", f"{growth_rate*100:+.1f}%")
                
                if divergence > 0.5:
                    div_status = "⚠️ 期待先行（株価上がりすぎ）"
                elif divergence < -0.2:
                    div_status = "✨ 超割安（業績に追いついてない）"
                else:
                    div_status = "🟢 適正水準（業績と連動）"
                    
                c3.metric(f"乖離率（株価 - {metric_name}）", f"{divergence*100:+.1f} pt", div_status)
            else:
                st.warning("現在、業績データを取得できませんでした。時間をおいて再試行してください。")

        st.write("---")
        st.link_button(f"🔗 {ticker_code} の詳細を米Yahoo! Financeで確認", f"https://finance.yahoo.com/quote/{ticker_code}")
    else:
        st.warning("⚠️ データ取得エラー。左下の「更新」ボタンを押してください。")

with tab2:
    st.markdown("### 🚀 全監視銘柄 一斉スキャン")
    st.write("登録されている全米国銘柄の最新シグナルとテクニカル指標を一覧表で確認します。")
    
    if st.button("🔄 最新データで一覧表を作成する"):
        scan_results = []
        pb = st.progress(0)
        
        items = list(valid_options.items())
        for i, (name, code) in enumerate(items):
            pb.progress((i + 1) / len(items))
            try:
                df, _ = load_us_data(code)
                if df is not None:
                    latest = df.iloc[-1]
                    prev = df.iloc[-2]
                    
                    # シグナルのタイトルだけを取得
                    signal_title, _ = get_tqqq_signal(latest, prev)
                    
                    # 乖離率の計算
                    dd_percent = latest['Drawdown_from_High20'] * 100
                    sma200_dist = ((latest['Close'] / latest['SMA200']) - 1) * 100
                    
                    scan_results.append({
                        "ティッカー": code,
                        "銘柄名": name.split(" ")[0], # 表示をスッキリさせるため英字部分だけ
                        "判定シグナル": signal_title,
                        "現在値": f"${latest['Close']:,.2f}",
                        "直近高値からの下落率": f"{dd_percent:.1f}%",
                        "200日線との乖離率": f"{sma200_dist:+.1f}%"
                    })
                time.sleep(0.1) # API制限回避のためのウェイト
            except Exception:
                continue
                
        pb.empty()
        
        if scan_results:
            st.success("✅ スキャン完了！")
            # データフレームに変換してテーブル表示
            res_df = pd.DataFrame(scan_results)
            st.dataframe(res_df, use_container_width=True, hide_index=True)
            
            st.caption("※ 「直近高値からの下落率」が -25% を超えると損切りアラート、"
                       "「200日線との乖離率」が -20% 以下になるとバーゲン（買い場）の目安となります。")
        else:
            st.error("データの取得に失敗しました。時間をおいて再度お試しください。")
