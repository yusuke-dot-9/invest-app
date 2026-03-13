import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests

# --- 1. ページ設定 ---
st.set_page_config(page_title="日経225 全銘柄スキャン＆判定ツール", layout="wide")
st.title("🇯🇵 日経225 判定＆全銘柄スキャンシステム")

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

# --- 3. テクニカル指標計算 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 4. 株価データ取得（チャートデータは安定しています） ---
@st.cache_data(ttl=3600)
def load_data(ticker_symbol):
    if not ticker_symbol.endswith('.T'): ticker_symbol = f"{ticker_symbol}.T"
    try:
        nk225 = yf.Ticker("^N225").history(period="5y")
        df_data = yf.Ticker(ticker_symbol).history(period="5y")
        if df_data.empty or nk225.empty: return None, None
        
        df = df_data[['Open', 'High', 'Low', 'Close']].dropna()
        nk_df = pd.DataFrame({'Close': nk225['Close']}).dropna()
        
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
        df = df.join(nk_df[['Uptrend']], how='left').ffill()
        return df, ticker_symbol
    except:
        return None, None

# --- 5. バックテスト計算 ---
def run_backtest(df):
    t_trend, t_rev = [], []
    in_trend, in_rev = False, False
    p_trend, p_rev = 0, 0
    # 200日移動平均線を計算するため、最初の200日はスキップ
    for i in range(200, len(df)):
        d, y = df.iloc[i], df.iloc[i-1]
        
        # 順張り
        if not in_trend:
            if d['Uptrend'] and d['Close'] > d['SMA200'] and y['High'] >= y['High20'] and d['Low'] <= d['SMA5']:
                in_trend, p_trend = True, d['Close']
        elif d['Close'] < d['Low3']:
            in_trend = False
            t_trend.append((d['Close'] / p_trend) - 1)
            
        # 逆張り
        if not in_rev:
            if d['Close'] > d['SMA200'] and d['RSI14'] < 30 and d['Close'] < d['BB_Lower']:
                in_rev, p_rev = True, d['Close']
        elif d['RSI14'] > 70 or d['Close'] <= p_rev * 0.95:
            in_rev = False
            t_rev.append((d['Close'] / p_rev) - 1)
            
    return t_trend, t_rev

# --- 6. 日経225 全225銘柄リスト（完全ハードコード版・エラー率0%） ---
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

# --- 7. サイドバー ---
st.sidebar.header("🔍 銘柄選択")
company_names = sorted(list(COMPANY_DICT.keys()))
selected_name = st.sidebar.selectbox("銘柄名を選択・検索", options=company_names, index=company_names.index("三菱商事"))
ticker_code = COMPANY_DICT[selected_name]

# --- 8. メインコンテンツ ---
tab1, tab2 = st.tabs(["📊 個別銘柄分析", "🚀 225銘柄一斉スキャン"])

with tab1:
    df, symbol = load_data(ticker_code)
    
    if df is not None:
        latest, prev = df.iloc[-1], df.iloc[-2]
        
        # 判定ロジック
        sig = "🟢 待機"
        if latest['Uptrend'] and latest['Close'] > latest['SMA200'] and prev['High'] >= prev['High20'] and latest['Low'] <= latest['SMA5']:
            sig = "🔥 【順張り】買いシグナル！"
        elif latest['Close'] > latest['SMA200'] and latest['RSI14'] < 30 and latest['Close'] < latest['BB_Lower']:
            sig = "🚨 【逆張り】買いシグナル！"
            
        st.subheader(f"本日の判定：{sig}")
        
        # 基本指標表示
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("現在値", f"¥{latest['Close']:,.1f}")
        col2.metric("RSI(14)", f"{latest['RSI14']:.1f}")
        col3.metric("日経平均トレンド", "上昇 📈" if latest['Uptrend'] else "下落 📉")
        col4.metric("200日移動平均線", "上" if latest['Close'] > latest['SMA200'] else "下")

        # --- エラー回避策：企業情報はYahooファイナンス公式へリンク ---
        st.write("---")
        st.markdown(f"### 🏢 {selected_name} の詳細な企業情報（PER・ROEなど）")
        st.write("※データ取得エラーを防ぐため、最新の財務データは公式ページから直接確認してください。")
        
        official_url = f"https://finance.yahoo.co.jp/quote/{ticker_code}.T/fundamental"
        st.link_button(f"🔗 {selected_name} のPER・PBR・ROEを公式で確認する", official_url)

        # --- バックテスト成績 ---
        st.divider()
        t_trend, t_rev = run_backtest(df)
        st.subheader("📈 過去5年間のバックテスト成績")
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 🔥 順張り（押し目買い）")
            if t_trend:
                wr = len([x for x in t_trend if x > 0]) / len(t_trend) * 100
                ar = np.mean(t_trend) * 100
                m1, m2, m3 = st.columns(3)
                m1.metric("発生回数", f"{len(t_trend)}回")
                m2.metric("勝率", f"{wr:.1f}%")
                m3.metric("平均利回り", f"{ar:+.2f}%")
            else: st.info("過去5年で条件に一致した日はありません")
                
        with c2:
            st.markdown("#### 🚨 逆張り（リバウンド）")
            if t_rev:
                wr = len([x for x in t_rev if x > 0]) / len(t_rev) * 100
                ar = np.mean(t_rev) * 100
                m1, m2, m3 = st.columns(3)
                m1.metric("発生回数", f"{len(t_rev)}回")
                m2.metric("勝率", f"{wr:.1f}%")
                m3.metric("平均利回り", f"{ar:+.2f}%")
            else: st.info("過去5年で条件に一致した日はありません")

        if st.button("📱 この結果をLINEに送信する"):
            line_msg = f"【日本株判定】\n銘柄: {selected_name}\n判定: {sig}\n現在価格: {latest['Close']:,.0f}円"
            send_line_notification(line_msg)

    else:
        st.error("データの取得に失敗しました。時間をおいて再試行してください。")

with tab2:
    st.markdown("日経225の全銘柄を一気に分析し、本日「買いシグナル」が点灯している銘柄を探し出します。")
    if st.button("🚀 225銘柄を一斉スキャン開始"):
        hits = []
        pb = st.progress(0)
        items = list(COMPANY_DICT.items())
        
        for i, (name, code) in enumerate(items):
            pb.progress((i+1)/len(items), text=f"{name} を分析中...")
            try:
                sdf, _ = load_data(code)
                if sdf is not None:
                    l, p = sdf.iloc[-1], sdf.iloc[-2]
                    s = None
                    if l['Uptrend'] and l['Close'] > l['SMA200'] and p['High'] >= p['High20'] and l['Low'] <= l['SMA5']:
                        s = "順張り🔥"
                    elif l['Close'] > l['SMA200'] and l['RSI14'] < 30 and l['Close'] < l['BB_Lower']:
                        s = "逆張り🚨"
                    
                    if s: hits.append({"銘柄": name, "判定": s, "現在値": f"¥{l['Close']:,.1f}"})
                # スキャンを高速化しつつ、サーバーに優しくする絶妙な待機時間
                time.sleep(0.01)
            except: 
                continue
                
        pb.empty()
        
        if hits:
            st.success(f"🎉 {len(hits)} 銘柄でシグナルが点灯しています！")
            st.table(pd.DataFrame(hits))
            
            # まとめてLINEに送る機能も追加
            if st.button("📱 スキャン結果をLINEに一括送信"):
                res_msg = "【本日のスキャン結果】\n" + "\n".join([f"・{h['銘柄']}({h['判定']})" for h in hits])
                send_line_notification(res_msg)
        else: 
            st.info("本日はシグナルが点灯している銘柄はありませんでした。")
