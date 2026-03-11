import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import time
import requests

# --- 1. ページ設定 ---
st.set_page_config(page_title="日経225判定システム・完全版", layout="wide")
st.title("🇯🇵 日経225 全銘柄 判定＆スキャン")

# --- 2. LINE通知関数 ---
def send_line_notification(message):
    try:
        if "LINE_CHANNEL_ACCESS_TOKEN" not in st.secrets: return
        token = st.secrets["LINE_CHANNEL_ACCESS_TOKEN"]
        user_id = st.secrets["LINE_USER_ID"]
        url = "https://api.line.me/v2/bot/message/push"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        data = {"to": user_id, "messages": [{"type": "text", "text": message}]}
        requests.post(url, headers=headers, json=data)
    except: pass

# --- 3. 指標計算 ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# --- 4. 株価データ取得 ---
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

# --- 5. 業種・財務データ取得（エラーガード強化版） ---
@st.cache_data(ttl=86400)
def get_fundamentals(ticker_symbol):
    if not ticker_symbol.endswith('.T'): ticker_symbol = f"{ticker_symbol}.T"
    try:
        t = yf.Ticker(ticker_symbol)
        info = t.info
        if not info: return {"業種": "不明", "PER": "N/A", "PBR": "N/A", "ROE": "N/A"}
        return {
            "業種": info.get('sector', '不明'),
            "PER": info.get('trailingPE', info.get('forwardPE', 'N/A')),
            "PBR": info.get('priceToBook', 'N/A'),
            "ROE": info.get('returnOnEquity', 'N/A')
        }
    except:
        return {"業種": "取得不可", "PER": "N/A", "PBR": "N/A", "ROE": "N/A"}

# --- 6. バックテスト ---
def run_backtest(df):
    t_trend, t_rev = [], []
    in_trend, in_rev = False, False
    p_trend, p_rev = 0, 0
    for i in range(200, len(df)):
        d, y = df.iloc[i], df.iloc[i-1]
        if not in_trend:
            if d['Uptrend'] and d['Close'] > d['SMA200'] and y['High'] >= y['High20'] and d['Low'] <= d['SMA5']:
                in_trend, p_trend = True, d['Close']
        elif d['Close'] < d['Low3']:
            in_trend = False
            t_trend.append((d['Close'] / p_trend) - 1)
        if not in_rev:
            if d['Close'] > d['SMA200'] and d['RSI14'] < 30 and d['Close'] < d['BB_Lower']:
                in_rev, p_rev = True, d['Close']
        elif d['RSI14'] > 70 or d['Close'] <= p_rev * 0.95:
            in_rev = False
            t_rev.append((d['Close'] / p_rev) - 1)
    return t_trend, t_rev

# --- 7. 銘柄リスト (225銘柄) ---
COMPANY_DICT = {
    "極洋": "1301", "ニッスイ": "1332", "マルハニチロ": "1333", "INPEX": "1605", "大成建設": "1801",
    "大林組": "1802", "清水建設": "1803", "鹿島建設": "1812", "大和ハウス": "1925", "積水ハウス": "1928",
    "日揮HD": "1963", "サッポロHD": "2501", "アサヒグループHD": "2502", "キリンHD": "2503", "宝HD": "2531",
    "コカ・コーラBJH": "2579", "サントリー食品": "2587", "味の素": "2802", "ブルドックソース": "2804", "ニチレイ": "2871",
    "日本たばこ産業": "2914", "セブン＆アイHD": "3382", "日本製紙": "3863", "王子HD": "3861", "昭和電工": "4004",
    "住友化学": "4005", "日産化学": "4021", "東ソー": "4042", "トクヤマ": "4043", "デンカ": "4061",
    "信越化学工業": "4063", "協和キリン": "4151", "三菱ケミカルHD": "4188", "ダイセル": "4202", "三井化学": "4183",
    "住友ベークライト": "4203", "日本ゼオン": "4205", "宇部興産": "4208", "積水化学": "4204", "野村総合研究所": "4307",
    "電通グループ": "4324", "花王": "4452", "武田薬品工業": "4502", "アステラス製薬": "4503", "住友ファーマ": "4506",
    "塩野義製薬": "4507", "田辺三菱製薬": "4508", "三菱ガス化学": "4182", "中外製薬": "4519", "エーザイ": "4523",
    "テルモ": "4543", "第一三共": "4568", "大塚HD": "4578", "資生堂": "4911", "富士フイルムHD": "4901",
    "コニカミノルタ": "4902", "出光興産": "5019", "ENEOS HD": "5020", "横浜ゴム": "5101", "ブリヂストン": "5108",
    "AGC": "5201", "日本板硝子": "5202", "日本電気硝子": "5214", "住友大阪セメント": "5232", "太平洋セメント": "5233",
    "東海カーボン": "5301", "日本ガイシ": "5333", "日本特殊陶業": "5334", "日本製鉄": "5401", "神戸製鋼所": "5406",
    "JFE HD": "5411", "三井金属": "5706", "三菱マテリアル": "5711", "住友金属鉱山": "5713", "DOWA HD": "5714",
    "古河電工": "5801", "住友電工": "5802", "フジクラ": "5803", "リョービ": "5851", "アーレスティ": "5852",
    "LIXIL": "5938", "三井海洋開発": "6269", "小松製作所": "6301", "住友重機械": "6302", "日立建機": "6305",
    "荏原製作所": "6361", "ダイキン工業": "6367", "日本精工": "6471", "NTN": "6472", "ジェイテクト": "6473",
    "ミネベアミツミ": "6479", "日立製作所": "6501", "東芝": "6502", "三菱電機": "6503", "富士電機": "6504",
    "安川電機": "6506", "明電舎": "6508", "シャープ": "6753", "NEC": "6701", "富士通": "6702",
    "セイコーエプソン": "6724", "パナソニック": "6752", "ソニーグループ": "6758", "TDK": "6762", "アルプスアルパイン": "6770",
    "横河電機": "6841", "アドバンテスト": "6857", "キーエンス": "6861", "カシオ": "6952", "ファナック": "6954",
    "京セラ": "6971", "村田製作所": "6981", "日東電工": "6988", "三菱重工業": "7011", "川崎重工業": "7012",
    "IHI": "7013", "三井E&S HD": "7003", "日立造船": "7004", "トヨタ自動車": "7203", "日産自動車": "7201",
    "いすゞ自動車": "7202", "日野自動車": "7205", "三菱自動車工業": "7211", "マツダ": "7261", "本田技研工業": "7267",
    "スズキ": "7269", "SUBARU": "7270", "ヤマハ発動機": "7272", "島津製作所": "7701", "ニコン": "7731",
    "オリンパス": "7733", "シチズン時計": "7762", "キヤノン": "7751", "リコー": "7752",
    "スクリーンHD": "7735", "凸版印刷": "7911", "大日本印刷": "7912", "ヤマハ": "7951", "任天堂": "7974",
    "バンダイナムコHD": "7832", "三井物産": "8031", "三菱商事": "8058", "住友商事": "8053", "伊藤忠商事": "8001",
    "丸紅": "8002", "豊田通商": "8015", "双日": "2768", "兼松": "8020", "三井不動産": "8801",
    "三菱地所": "8802", "平和不動産": "8803", "住友不動産": "8830", "東急不動産HD": "3289", "野村不動産HD": "3231",
    "東京建物": "8804", "日本郵船": "9101", "商船三井": "9104", "川崎汽船": "9107", "日本航空": "9201",
    "ANA HD": "9202", "三菱倉庫": "9301", "三井倉庫HD": "9302", "住友倉庫": "9303", "日本通運": "9062",
    "ヤマトHD": "9064", "近鉄グループHD": "9041", "阪急阪神HD": "9042", "東武鉄道": "9001", "東急": "9005",
    "小田急電鉄": "9007", "京王電鉄": "9008", "京成電鉄": "9009", "西武HD": "9024", "JR東日本": "9020",
    "JR東海": "9022", "JR西日本": "9021", "中部電力": "9502", "東京電力HD": "9501", "関西電力": "9503",
    "大阪ガス": "9532", "東京ガス": "9531", "NTT": "9432", "KDDI": "9433", "ソフトバンクグループ": "9984",
    "ソフトバンク": "9434", "楽天グループ": "4755", "セコム": "9735", "コナミHD": "9766", "トレンドマイクロ": "4704",
    "リクルートHD": "6098", "ファーストリテイリング": "9983", "ニトリHD": "9843", "三菱UFJ FG": "8306", "三井住友 FG": "8316",
    "みずほ FG": "8411", "りそな HD": "8308", "三井住友トラスト": "8309", "千葉銀行": "8331", "ふくおか FG": "8354",
    "しずおか FG": "8355", "コンコルディア FG": "7186", "野村 HD": "8604", "大和証券グループ": "8601", "松井証券": "8628",
    "マネックスグループ": "8698", "東京海上 HD": "8766", "MS&AD": "8725", "第一生命 HD": "8750", "T&D HD": "8795",
    "日本取引所グループ": "8697"
}

# --- サイドバー ---
st.sidebar.header("🔍 銘柄選択")
company_names = sorted(list(COMPANY_DICT.keys()))
selected_name = st.sidebar.selectbox("銘柄名を入力（例：三菱）", options=company_names, index=company_names.index("三菱商事"))
ticker_input = COMPANY_DICT[selected_name]

# --- メインコンテンツ ---
tab1, tab2 = st.tabs(["📊 個別銘柄分析", "🚀 225銘柄一斉スキャン"])

with tab1:
    df, symbol = load_data(ticker_input)
    fundamentals = get_fundamentals(ticker_input)
    
    if df is not None:
        latest, prev = df.iloc[-1], df.iloc[-2]
        sig = "🟢 待機"
        if latest['Uptrend'] and latest['Close'] > latest['SMA200'] and prev['High'] >= prev['High20'] and latest['Low'] <= latest['SMA5']:
            sig = "🔥 【順張り】買いシグナル！"
        elif latest['Close'] > latest['SMA200'] and latest['RSI14'] < 30 and latest['Close'] < latest['BB_Lower']:
            sig = "🚨 【逆張り】買いシグナル！"
            
        st.subheader(f"判定：{sig}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("現在値", f"¥{latest['Close']:,.1f}")
        col2.metric("RSI(14)", f"{latest['RSI14']:.1f}")
        col3.metric("日経トレンド", "上昇 📈" if latest['Uptrend'] else "下落 📉")
        col4.metric("200日線", "上" if latest['Close'] > latest['SMA200'] else "下")

        st.markdown(f"### 🏢 企業情報・ファンダメンタルズ")
        f1, f2, f3, f4 = st.columns(4)
        f1.write(f"**業種:** {fundamentals['業種']}")
        
        # 数値かどうか判定して安全に表示
        def safe_format(val, unit, digits=1):
            if isinstance(val, (int, float)):
                return f"{val:.{digits}f} {unit}"
            return "N/A"

        f2.write(f"**PER:** {safe_format(fundamentals['PER'], '倍')}")
        f3.write(f"**PBR:** {safe_format(fundamentals['PBR'], '倍', 2)}")
        
        roe_val = fundamentals['ROE']
        roe_display = f"{roe_val*100:.1f} %" if isinstance(roe_val, (int, float)) else "N/A"
        f4.write(f"**ROE:** {roe_display}")
        
        if st.button("📱 分析結果をLINEに送る"):
            msg = f"【判定】{selected_name}\n結果: {sig}\n株価: {latest['Close']:,.0f}円\n業種: {fundamentals['業種']}\nPER: {safe_format(fundamentals['PER'], '倍')}\nROE: {roe_display}"
            send_line_notification(msg)

        st.divider()
        t_trend, t_rev = run_backtest(df)
        st.subheader("📈 バックテスト結果（過去5年）")
        c1, c2 = st.columns(2)
        with c1:
            if t_trend: st.write(f"順張り勝率: **{len([x for x in t_trend if x > 0])/len(t_trend)*100:.1f}%**")
            else: st.write("データなし")
        with c2:
            if t_rev: st.write(f"逆張り勝率: **{len([x for x in t_rev if x > 0])/len(t_rev)*100:.1f}%**")
            else: st.write("データなし")
    else:
        st.error("データ読み込みエラー：銘柄データが取得できません。")

with tab2:
    if st.button("🚀 日経225銘柄をスキャン開始"):
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
                    if l['Uptrend'] and l['Close'] > l['SMA200'] and p['High'] >= p['High20'] and l['Low'] <= l['SMA5']:
                        s = "順張り🔥"
                    elif l['Close'] > l['SMA200'] and l['RSI14'] < 30 and l['Close'] < l['BB_Lower']:
                        s = "逆張り🚨"
                    if s: hits.append({"銘柄": name, "判定": s, "価格": f"{l['Close']:,.1f}"})
                time.sleep(0.01)
            except: continue
        pb.empty()
        if hits:
            st.success(f"🎉 {len(hits)} 銘柄が条件に一致しました！")
            st.table(pd.DataFrame(hits))
        else: st.info("本日のシグナルはありません。")
