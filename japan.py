import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests
import os

# --- 1. ページ設定 ---
st.set_page_config(page_title="日経225 スキャン＆ポートフォリオ", layout="wide")
st.title("🇯🇵 日経225 判定＆保有銘柄管理システム")

# --- 2. LINE通知関数 ---
def send_line_notification(message):
    try:
        if "LINE_CHANNEL_ACCESS_TOKEN" not in st.secrets or "LINE_USER_ID" not in st.secrets: 
            return
        token = st.secrets["LINE_CHANNEL_ACCESS_TOKEN"]
        user_id = st.secrets["LINE_USER_ID"]
        url = "https://api.line.me/v2/bot/message/push"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        data = {"to": user_id, "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=data)
    except: pass

# --- 3. ポートフォリオ（保有銘柄）の保存機能 ---
PORTFOLIO_FILE = "portfolio.csv"

def load_portfolio():
    if os.path.exists(PORTFOLIO_FILE):
        return pd.read_csv(PORTFOLIO_FILE)
    else:
        return pd.DataFrame(columns=["銘柄名", "コード", "買値", "株数", "戦略"])

def save_portfolio(df):
    df.to_csv(PORTFOLIO_FILE, index=False)

# --- 4. テクニカル指標計算 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 5. データ取得関数（タイムゾーン修正＆エラー表示強化版） ---
@st.cache_data(ttl=3600)
def load_data(ticker_symbol):
    if not ticker_symbol.endswith('.T'): ticker_symbol = f"{ticker_symbol}.T"
    try:
        nk225 = yf.download("^N225", period="5y", progress=False)
        df_data = yf.download(ticker_symbol, period="5y", progress=False)
        
        if df_data.empty or nk225.empty: 
            st.error("⚠️ Yahoo Financeから空のデータが返ってきました（通信制限の可能性）。")
            return None, None
        
        if isinstance(df_data.columns, pd.MultiIndex):
            df_data.columns = df_data.columns.get_level_values(0)
        if isinstance(nk225.columns, pd.MultiIndex):
            nk225.columns = nk225.columns.get_level_values(0)
        
        df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
        nk_df = pd.DataFrame({'Close': nk225['Close']}).dropna()
        
        # 💡 日本株特有のエラーを防ぐためのタイムゾーン（時差）処理
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        if nk_df.index.tz is not None:
            nk_df.index = nk_df.index.tz_localize(None)
            
        nk_df['SMA25'] = nk_df['Close'].rolling(window=25).mean()
        nk_df['SMA75'] = nk_df['Close'].rolling(window=75).mean()
        nk_df['Uptrend'] = nk_df['SMA25'] > nk_df['SMA75']
        
        df['SMA5'] = df['Close'].rolling(window=5).mean()
        df['SMA25'] = df['Close'].rolling(window=25).mean()
        df['SMA200'] = df['Close'].rolling(window=200).mean()
        df['High200_prev'] = df['High'].rolling(window=200).max().shift(1)
        df['RSI14'] = calculate_rsi(df['Close'], 14)
        
        df = df.join(nk_df[['Uptrend']], how='left').ffill()
        return df, ticker_symbol
    except Exception as e:
        # 💡 もしエラーが出ても、画面に赤文字で詳細を表示させる
        st.error(f"データ取得エラー詳細: {e}")
        return None, None

# --- 6. バックテスト計算 ---
def run_backtest(df):
    t_trend, t_rev = [], []
    in_trend, in_rev = False, False
    p_trend, p_rev = 0, 0
    for i in range(200, len(df)):
        d, y = df.iloc[i], df.iloc[i-1]
        if not in_trend:
            if d['Close'] > d['High200_prev']:
                in_trend, p_trend = True, d['Close']
        else:
            if d['Close'] < d['SMA25'] or d['Close'] < p_trend * 0.95:
                in_trend = False
                t_trend.append((d['Close'] / p_trend) - 1)
        if not in_rev:
            if d['Close'] > d['SMA200'] and y['Close'] <= y['SMA200']:
                in_rev, p_rev = True, d['Close']
        else:
            if d['Close'] < d['SMA200'] * 0.98 or d['Close'] > p_rev * 1.20:
                in_rev = False
                t_rev.append((d['Close'] / p_rev) - 1)
    return t_trend, t_rev

# --- 7. 日経225 全銘柄リスト ---
COMPANY_DICT = {
    "ニッスイ": "1332", "マルハニチロ": "1333", "INPEX": "1605", "大成建設": "1801", "大林組": "1802", "清水建設": "1803", "長谷工コーポレーション": "1808", "鹿島": "1812", 
    "大和ハウス工業": "1925", "積水ハウス": "1928", "日揮HD": "1963", "日清製粉グループ本社": "2002", "双日": "2768", "アルフレッサHD": "2784", "味の素": "2802", 
    "キッコーマン": "2801", "ニチレイ": "2871", "JT(日本たばこ産業)": "2914", "ジェイフロントリテイリング": "3086", "マツキヨココカラ＆C": "3088", "ZOZO": "3092", 
    "三越伊勢丹HD": "3099", "野村不動産HD": "3231", "東急不動産HD": "3289", "セブン＆アイHD": "3382", "東レ": "3402", "クラレ": "3405", "旭化成": "3407", 
    "SUMCO": "3436", "ネクソン": "3659", "王子HD": "3861", "日本製紙": "3863", "レゾナックHD": "4004", "住友化学": "4005", "日産化学": "4021", "東ソー": "4042", 
    "トクヤマ": "4043", "デンカ": "4061", "信越化学工業": "4063", "協和キリン": "4151", "三井化学": "4183", "三菱ケミカルグループ": "4188", "積水化学工業": "4204", 
    "UBE": "4208", "野村総合研究所": "4307", "電通グループ": "4324", "花王": "4452", "武田薬品工業": "4502", "アステラス製薬": "4503", "住友ファーマ": "4506", 
    "塩野義製薬": "4507", "中外製薬": "4519", "エーザイ": "4523", "テルモ": "4543", "第一三共": "4568", "大塚HD": "4578", "LINEヤフー": "4689", 
    "トレンドマイクロ": "4704", "サイバーエージェント": "4751", "楽天グループ": "4755", "富士フイルムHD": "4901", "コニカミノルタ": "4902", "資生堂": "4911", 
    "出光興産": "5019", "ENEOS HD": "5020", "横浜ゴム": "5101", "ブリヂストン": "5108", "AGC": "5201", "日本板硝子": "5202", "日本電気硝子": "5214", 
    "住友大阪セメント": "5232", "太平洋セメント": "5233", "東海カーボン": "5301", "TOTO": "5332", "日本ガイシ": "5333", "日本製鉄": "5401", "神戸製鋼所": "5406", 
    "JFE HD": "5411", "大平洋金属": "5541", "日本製鋼所": "5631", "三井金属": "5706", "三菱マテリアル": "5711", "住友金属鉱山": "5713", "DOWA HD": "5714", 
    "フジクラ": "5803", "古河電気工業": "5801", "住友電気工業": "5802", "東洋製罐グループHD": "5901", "リクルートHD": "6098", "オークマ": "6103", 
    "アマダ": "6118", "ディスコ": "6146", "SMC": "6273", "コマツ": "6301", "住友重機械工業": "6302", "日立建機": "6305", "クボタ": "6326", "荏原製作所": "6361", 
    "ダイキン工業": "6367", "日本精工": "6471", "NTN": "6472", "ジェイテクト": "6473", "ミネベアミツミ": "6479", "日立製作所": "6501", "三菱電機": "6503", 
    "富士電機": "6504", "安川電機": "6506", "ニデック": "6594", "オムロン": "6645", "NEC": "6701", "富士通": "6702", "ルネサスエレクトロニクス": "6723", 
    "セイコーエプソン": "6724", "パナソニックHD": "6752", "シャープ": "6753", "ソニーグループ": "6758", "TDK": "6762", "アルプスアルパイン": "6770", 
    "横河電機": "6841", "アドバンテスト": "6857", "キーエンス": "6861", "デンソー": "6902", "カシオ計算機": "6952", "ファナック": "6954", "京セラ": "6971", 
    "太陽誘電": "6976", "村田製作所": "6981", "日東電工": "6988", "三菱重工業": "7011", "川崎重工業": "7012", "IHI": "7013", "日産自動車": "7201", 
    "いすゞ自動車": "7202", "トヨタ自動車": "7203", "日野自動車": "7205", "三菱自動車": "7211", "マツダ": "7261", "ホンダ": "7267", "スズキ": "7269", 
    "SUBARU": "7270", "ヤマハ発動機": "7272", "ニコン": "7731", "オリンパス": "7733", "SCREEN HD": "7735", "HOYA": "7741", "キヤノン": "7751", 
    "リコー": "7752", "バンダイナムコHD": "7832", "TOPPAN HD": "7911", "大日本印刷": "7912", "ヤマハ": "7951", "任天堂": "7974", "伊藤忠商事": "8001", 
    "丸紅": "8002", "豊田通商": "8015", "三井物産": "8031", "東京エレクトロン": "8035", "住友商事": "8053", "三菱商事": "8058", "クレディセゾン": "8253", 
    "三菱UFJ FG": "8306", "りそなHD": "8308", "三井住友トラストHD": "8309", "三井住友FG": "8316", "千葉銀行": "8331", "ふくおかFG": "8354", 
    "しずおかFG": "8355", "みずほFG": "8411", "オリックス": "8591", "大和証券グループ本社": "8601", "野村HD": "8604", "松井証券": "8628", 
    "SOMPO HD": "8630", "日本取引所グループ": "8697", "MS&AD": "8725", "第一生命HD": "8750", "東京海上HD": "8766", "T&D HD": "8795", 
    "三井不動産": "8801", "三菱地所": "8802", "東京建物": "8804", "住友不動産": "8830", "東武鉄道": "9001", "東急": "9005", "小田急電鉄": "9007", 
    "京王電鉄": "9008", "京成電鉄": "9009", "JR東日本": "9020", "JR西日本": "9021", "JR東海": "9022", "西武HD": "9024", "近鉄グループHD": "9041", 
    "阪急阪神HD": "9042", "ヤマトHD": "9064", "日本郵船": "9101", "商船三井": "9104", "川崎汽船": "9107", "NIPPON EXPRESS": "9147", "日本航空(JAL)": "9201", 
    "ANA HD": "9202", "三菱倉庫": "9301", "NTT": "9432", "KDDI": "9433", "ソフトバンク": "9434", "東京電力HD": "9501", "中部電力": "9502", 
    "関西電力": "9503", "東京ガス": "9531", "大阪ガス": "9532", "東宝": "9602", "NTTデータ": "9613", "セコム": "9735", "コナミグループ": "9766", 
    "ファーストリテイリング": "9983", "ソフトバンクグループ": "9984"
}

# --- 8. サイドバー ---
st.sidebar.header("🔍 銘柄選択")
company_names = sorted(list(COMPANY_DICT.keys()))
selected_name = st.sidebar.selectbox("銘柄名を選択・検索", options=company_names, index=company_names.index("三菱商事"))
ticker_code = COMPANY_DICT[selected_name]

# --- 9. メインコンテンツ（3つのタブ） ---
tab1, tab2, tab3 = st.tabs(["📊 個別分析", "🚀 225銘柄スキャン", "💼 保有銘柄管理（出口戦略）"])

with tab1:
    df, symbol = load_data(ticker_code)
    if df is not None:
        latest, prev = df.iloc[-1], df.iloc[-2]
        
        sig = "🟢 待機"
        if latest['Close'] > latest['High200_prev']:
            sig = "🔥 【新高値ブレイク】最強順張りシグナル！"
        elif latest['Close'] > latest['SMA200'] and prev['Close'] <= prev['SMA200']:
            sig = "🚨 【バリュー初動】200日線突破シグナル！"
            
        st.subheader(f"本日の判定：{sig}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("現在値", f"¥{latest['Close']:,.1f}")
        col2.metric("過去200日最高値", f"¥{latest['High200_prev']:,.1f}")
        col3.metric("日経平均トレンド", "上昇 📈" if latest['Uptrend'] else "下落 📉")
        col4.metric("200日移動平均線", "上" if latest['Close'] > latest['SMA200'] else "下")

        st.write("---")
        official_url = f"https://finance.yahoo.co.jp/quote/{ticker_code}.T"
        st.link_button(f"🔗 {selected_name} の財務データを公式で確認する", official_url)

        st.divider()
        t_trend, t_rev = run_backtest(df)
        st.subheader("📈 過去5年間のバックテスト成績")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🔥 新高値ブレイクアウト（順張り）")
            if t_trend:
                wr = len([x for x in t_trend if x > 0]) / len(t_trend) * 100
                m1, m2, m3 = st.columns(3)
                m1.metric("発生回数", f"{len(t_trend)}回")
                m2.metric("勝率", f"{wr:.1f}%")
                m3.metric("平均利回り", f"{np.mean(t_trend)*100:+.2f}%")
        with c2:
            st.markdown("#### 🚨 バリューモメンタム（逆張り/初動）")
            if t_rev:
                wr = len([x for x in t_rev if x > 0]) / len(t_rev) * 100
                m1, m2, m3 = st.columns(3)
                m1.metric("発生回数", f"{len(t_rev)}回")
                m2.metric("勝率", f"{wr:.1f}%")
                m3.metric("平均利回り", f"{np.mean(t_rev)*100:+.2f}%")
    else:
        # データ取得に失敗した場合の表示（load_data内でエラーが出ているはず）
        pass

with tab2:
    st.markdown("新ロジックで225銘柄を一斉スキャンします。")
    if st.button("🚀 225銘柄を一斉スキャン開始"):
        hits = []
        pb = st.progress(0)
        items = list(COMPANY_DICT.items())
        
        for i, (name, code) in enumerate(items):
            pb.progress((i+1)/len(items))
            try:
                sdf, _ = load_data(code)
                if sdf is not None:
                    l, p = sdf.iloc[-1], sdf.iloc[-2]
                    s = None
                    if l['Close'] > l['High200_prev']:
                        s = "ブレイクアウト🔥"
                    elif l['Close'] > l['SMA200'] and p['Close'] <= p['SMA200']:
                        s = "バリュー初動🚨"
                    
                    if s: hits.append({"銘柄": name, "判定": s, "現在値": f"¥{l['Close']:,.1f}"})
                time.sleep(0.01)
            except: 
                continue
        pb.empty()
        
        if hits:
            st.success(f"🎉 {len(hits)} 銘柄でシグナルが点灯しています！")
            st.table(pd.DataFrame(hits))
        else: 
            st.info("本日はシグナルが点灯している銘柄はありませんでした。")

with tab3:
    st.markdown("### 💼 保有銘柄の利確・損切り判定")
    with st.expander("➕ 新しく購入した銘柄を登録する", expanded=False):
        with st.form("add_portfolio_form"):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                p_name = st.selectbox("銘柄", options=company_names)
            with col2:
                p_price = st.number_input("買値 (円)", min_value=1.0, value=1000.0, step=10.0)
            with col3:
                p_qty = st.number_input("株数 (ミニカブ対応)", min_value=1, value=1, step=1)
            with col4:
                p_strategy = st.selectbox("エントリー手法", options=["新高値ブレイク(順張り)", "バリュー初動(逆張り)"])
            
            submitted = st.form_submit_button("ポートフォリオに追加")
            if submitted:
                p_code = COMPANY_DICT[p_name]
                new_data = pd.DataFrame([{
                    "銘柄名": p_name, "コード": p_code, "買値": p_price, "株数": p_qty, "戦略": p_strategy
                }])
                pf_df = load_portfolio()
                pf_df = pd.concat([pf_df, new_data], ignore_index=True)
                save_portfolio(pf_df)
                st.success(f"{p_name} をポートフォリオに追加しました！")
                st.rerun()

    pf_df = load_portfolio()
    if pf_df.empty:
        st.info("現在、登録されている保有銘柄はありません。上のフォームから追加してください。")
    else:
        st.markdown("#### 現在の保有状況とアクション指示")
        results = []
        
        for index, row in pf_df.iterrows():
            code = str(row["コード"])
            df, _ = load_data(code)
            
            if df is not None:
                latest = df.iloc[-1]
                current_price = latest['Close']
                buy_price = row["買値"]
                profit_rate = (current_price - buy_price) / buy_price * 100
                profit_amount = (current_price - buy_price) * row["株数"]
                strategy = row["戦略"]
                
                action = "🟢 ホールド（利益拡大中）"
                
                if strategy == "新高値ブレイク(順張り)":
                    if current_price < latest['SMA25']:
                        action = "🟡 決済（25日線割れ・トレンド終了）"
                    elif profit_rate <= -5.0:
                        action = "🔴 即損切り（-5%ルール到達）"
                elif strategy == "バリュー初動(逆張り)":
                    if profit_rate >= 20.0:
                        action = "🔵 利益確定（目標+20%到達）"
                    elif current_price < latest['SMA200'] * 0.98:
                        action = "🔴 即損切り（200日線割れ・ダマシ判定）"
                
                results.append({
                    "銘柄名": row["銘柄名"],
                    "手法": strategy,
                    "買値": f"¥{buy_price:,.1f}",
                    "現在値": f"¥{current_price:,.1f}",
                    "損益率": f"{profit_rate:+.2f}%",
                    "含み損益": f"¥{profit_amount:,.0f}",
                    "アクション指示": action
                })
        
        if results:
            res_df = pd.DataFrame(results)
            st.dataframe(res_df, use_container_width=True)
            
            st.markdown("---")
            del_name = st.selectbox("決済済みの銘柄をポートフォリオから削除", options=pf_df["銘柄名"].tolist())
            if st.button("この銘柄を削除"):
                pf_df = pf_df[pf_df["銘柄名"] != del_name]
                save_portfolio(pf_df)
                st.success(f"{del_name} を削除しました。")
                st.rerun()
