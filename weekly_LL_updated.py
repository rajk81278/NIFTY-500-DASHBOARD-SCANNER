import streamlit as st
import os
import pyotp as tp
from fyers_apiv3 import fyersModel
import credentials as crs

os.makedirs("log", exist_ok=True)

ACCESS_FILE = "access.txt"

# -------------------------------
# Token validation
# -------------------------------
def is_token_valid(token):
    try:
        fyers = fyersModel.FyersModel(
            client_id=crs.client_id,
            token=token,
            log_path="log/"
        )
        res = fyers.quotes({"symbols": "NSE:SBIN-EQ"})
        return "d" in res
    except:
        return False


# -------------------------------
# FYERS LOGIN BLOCK (WEEKLY_LL)
# -------------------------------
def weekly_fyers_login():
    if "access_token" not in st.session_state:
        st.session_state.access_token = None

    # ---------- AUTO LOGIN ----------
    if os.path.exists(ACCESS_FILE):
        token = open(ACCESS_FILE).read().strip()
        if token and is_token_valid(token):
            st.session_state.access_token = token
            return token

    # ---------- LOGIN UI ----------
    st.set_page_config(page_title="FYERS Login – Weekly Scanner", layout="wide")
    st.title("🔐 FYERS Login Required (Weekly Scanner)")

    st.warning("Access token missing or expired. Please login.")

    # ---------- TOTP ----------
    st.sidebar.header("TOTP Generator")
    if st.sidebar.button("Generate TOTP"):
        code = tp.TOTP(crs.totp_key).now()
        st.sidebar.success(code)

    # ---------- AUTH URL ----------
    if st.button("Open FYERS Login Page"):
        session = fyersModel.SessionModel(
            client_id=crs.client_id,
            secret_key=crs.secret_key,
            redirect_uri=crs.redirect_uri,
            response_type="code"
        )
        url = session.generate_authcode()
        st.markdown(f"[👉 Click here to login]({url})", unsafe_allow_html=True)

    # ---------- AUTH CODE ----------
    redirect_url = st.text_input("Paste redirected URL")

    if redirect_url and "auth_code=" in redirect_url:
        auth_code = redirect_url.split("auth_code=")[1].split("&")[0]

        if st.button("Generate Access Token"):
            session = fyersModel.SessionModel(
                client_id=crs.client_id,
                secret_key=crs.secret_key,
                redirect_uri=crs.redirect_uri,
                response_type="code",
                grant_type="authorization_code"
            )
            session.set_token(auth_code)
            res = session.generate_token()

            if "access_token" in res:
                with open(ACCESS_FILE, "w") as f:
                    f.write(res["access_token"])

                st.success("✅ Login successful")
                st.rerun()

    st.stop()






# streamlit run weekly_LL.py

import streamlit as st
import pandas as pd
import datetime as dt
from fyers_apiv3 import fyersModel
import time
import requests
from io import StringIO
import warnings
import os
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

warnings.filterwarnings("ignore")

# =====================================================
# STREAMLIT CONFIG
# =====================================================
st.set_page_config(page_title="Weekly SR Scanner", layout="wide")
st.title("Weekly S/R BASE → BUY SCANNER")

# =====================================================
# SESSION STATE
# =====================================================
if "scan_done" not in st.session_state:
    st.session_state.scan_done = False
if "trade_stocks" not in st.session_state:
    st.session_state.trade_stocks = {}
if "scan_log" not in st.session_state:
    st.session_state.scan_log = []

lock = threading.Lock()

# =====================================================
# FYERS LOGIN
# =====================================================
# with open("access.txt", "r") as a:
#     access_token = a.read().strip()

access_token = weekly_fyers_login()

fyers = fyersModel.FyersModel(
    client_id=crs.client_id,
    token=access_token,
    log_path="log/"
)


# fyers = fyersModel.FyersModel(
#     client_id="5YKT940X4B-100",
#     token=access_token,
#     log_path=""
# )

# =====================================================
# CACHE
# =====================================================
CACHE_DIR = "data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def _cache_path(sym):
    return os.path.join(CACHE_DIR, sym.replace(":","_").replace("-","_") + ".parquet")

def load_cache(sym):
    if os.path.exists(_cache_path(sym)):
        return pd.read_parquet(_cache_path(sym))
    return pd.DataFrame()

def save_cache(sym, df):
    if not df.empty:
        df.to_parquet(_cache_path(sym))

# =====================================================
# DATA FETCH
# =====================================================
def fetch_month_data(symbol, start, end):
    data = fyers.history({
        "symbol": symbol,
        "resolution": "1D",
        "date_format": "1",
        "range_from": start,
        "range_to": end,
        "cont_flag": "1"
    })
    if data.get("s") == "ok":
        df = pd.DataFrame(
            data["candles"],
            columns=["date","open","high","low","close","volume"]
        )
        df["date"] = pd.to_datetime(df["date"], unit="s")
        df.set_index("date", inplace=True)
        return df
    return pd.DataFrame()

def fetch_5yr_data(symbol, years=6):
    cached = load_cache(symbol)
    if not cached.empty:
        return cached

    end = dt.datetime.now()
    start = end - dt.timedelta(days=years*365)
    cur = start
    parts = []

    while cur < end:
        nxt = min(cur + dt.timedelta(days=30), end)
        df = fetch_month_data(symbol, cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d"))
        if not df.empty:
            parts.append(df)
        cur = nxt + dt.timedelta(days=1)
        time.sleep(0.12)

    if parts:
        out = pd.concat(parts).sort_index()
        out = out[~out.index.duplicated()]
        save_cache(symbol, out)
        return out
    return pd.DataFrame()

# =====================================================
# SR LEVELS
# =====================================================
def calculate_sr_levels(df):
    high = df["high"].max()
    low = df["low"].min()
    avg = (high + low) / 2
    pct = (high - low) / high

    sr = {}
    for i in range(6,0,-1):
        sr[f"L{i}"] = round(high * (1-pct)**i, 2)
    for i in range(1,7):
        sr[f"P{i}"] = round(high * (1+pct)**i, 2)

    sr["Average"] = round(avg,2)
    sr["High (Ref)"] = round(high,2)
    return sr

# =====================================================
# WEEKLY BUY LOGIC (UNCHANGED)
# =====================================================
def find_weekly_buy_trades(df_daily, sr_levels, march_close_price):

    df_weekly = df_daily.resample('W').agg({
        'open':'first','high':'max','low':'min','close':'last','volume':'sum'
    }).dropna()
    # print(df_weekly)

    ul_pool = [float(sr_levels.get(f"P{i}")) for i in range(1,7)] + \
              [float(sr_levels["Average"]), float(sr_levels["High (Ref)"])]

    ll_pool = [float(sr_levels.get(f"L{i}")) for i in range(1,7)]

    ul_pool = [x for x in ul_pool if x > march_close_price]
    ll_pool = [x for x in ll_pool if x < march_close_price]

    if not ul_pool or not ll_pool:
        return pd.DataFrame(), df_weekly

    nearest_ul = min(ul_pool, key=lambda x: abs(x - march_close_price))
    nearest_ll = min(ll_pool, key=lambda x: abs(x - march_close_price))

    weeks = df_weekly.index
    n = len(df_weekly)
    i = 0
    trades = []
    # print(trades)

    while i < n:
        if df_weekly.iloc[i]['close'] <= nearest_ll:
            i += 1
            continue

        base_low = df_weekly.iloc[i]['low']
        if i+3 >= n: break

        fail = False
        for k in range(i+1, i+4):
            row = df_weekly.iloc[k]
            if row['close'] > nearest_ul or row['close'] < nearest_ll or row['low'] <= base_low:
                fail = True
                break

        if fail:
            i = k+1
            continue

        entry_idx = i+4
        if entry_idx >= n: break

        entry_price = df_weekly.iloc[entry_idx]['open']
        entry_date  = weeks[entry_idx]

        exit_price = None
        for k in range(entry_idx, min(entry_idx+4, n)):
            if df_weekly.iloc[k]['high'] >= nearest_ul:
                exit_price = nearest_ul
                exit_date  = weeks[k]
                exit_idx   = k
                break

        if exit_price is None:
            exit_idx   = min(entry_idx+5, n-1)
            exit_price = df_weekly.iloc[exit_idx]['close']
            exit_date  = weeks[exit_idx]

        pnl = round((exit_price-entry_price)/entry_price*100,2)

        trades.append({
            "entry_date": entry_date,
            "entry_price": round(entry_price,2),
            "exit_date": exit_date,
            "exit_price": round(exit_price,2),
            "pnl_pct": pnl,
            "ul": round(nearest_ul,2),
            "ll": round(nearest_ll,2),
            "base_date": weeks[i]
        })

        i = exit_idx + 1

    return pd.DataFrame(trades), df_weekly

# =====================================================
# PLOTTING FUNCTION (UNCHANGED)
# =====================================================


# def plot_chart(df, sr, title):
#     fig = go.Figure()
#     fig.add_candlestick(
#         x=df.index, open=df.open, high=df.high, low=df.low, close=df.close, name="Price"
#     )
#     for k,v in sr.items():
#         color = "green" if k.startswith("L") else "red"
#         fig.add_hline(y=v, line_dash="dot", line_color=color)
#     fig.update_layout(
#         title=title, height=750, dragmode="pan",
#         template="plotly_dark", xaxis_rangeslider_visible=True
#     )
#     return fig


# def plot_chart_with_signals(df, sr_levels, trades_df, title, show_volume=True):
#     import plotly.graph_objects as go
#     import pandas as pd

#     fig = go.Figure()

#     # ===================== CANDLESTICKS =====================
#     fig.add_trace(go.Candlestick(
#         x=df.index,
#         open=df["open"],
#         high=df["high"],
#         low=df["low"],
#         close=df["close"],
#         name="Price",
#         increasing=dict(line=dict(width=1.5, color="#00ff99")),
#         decreasing=dict(line=dict(width=1.5, color="#ff4d4d"))
#     ))

#     # ===================== VOLUME =====================
#     if show_volume and "volume" in df.columns:
#         fig.add_trace(go.Bar(
#             x=df.index,
#             y=df["volume"],
#             name="Volume",
#             yaxis="y2",
#             opacity=0.25
#         ))

#     # ===================== ENTRY / EXIT MARKERS =====================
#     if trades_df is not None and not trades_df.empty:
#         # ENTRY
#         fig.add_trace(go.Scatter(
#             x=trades_df["entry_date"],
#             y=trades_df["entry_price"],
#             mode="markers",
#             marker=dict(symbol="triangle-up", size=13, color="lime"),
#             name="ENTRY"
#         ))

#         # EXIT
#         fig.add_trace(go.Scatter(
#             x=trades_df["exit_date"],
#             y=trades_df["exit_price"],
#             mode="markers",
#             marker=dict(symbol="x", size=12, color="red"),
#             name="EXIT"
#         ))

#     # ===================== SR LEVELS =====================
#     level_colors = {
#         "L1": "#2E86C1", "L2": "#2874A6", "L3": "#21618C",
#         "L4": "#1B4F72", "L5": "#154360", "L6": "#0E2A38",
#         "P1": "#E74C3C", "P2": "#CB4335", "P3": "#B03A2E",
#         "P4": "#943126", "P5": "#78281F", "P6": "#641E16",
#         "Average": "#16A085",
#         "High (Ref)": "#F1C40F"
#     }

#     for key, value in sr_levels.items():
#         try:
#             lvl = float(value)
#             fig.add_hline(
#                 y=lvl,
#                 line_dash="dot",
#                 line=dict(width=2, color=level_colors.get(key, "#7F8C8D")),
#                 annotation_text=f"{key}: {lvl:.2f}",
#                 annotation_position="top left"
#             )
#         except:
#             pass

#     # ===================== LAYOUT =====================
#     fig.update_layout(
#         title=title,
#         height=750,
#         dragmode="pan",
#         hovermode="x unified",
#         template="plotly_dark",

#         xaxis=dict(showgrid=False),
#         yaxis=dict(showgrid=False),

#         yaxis2=dict(
#             overlaying="y",
#             side="right",
#             showgrid=False,
#             title="Volume" if show_volume else None
#         ),

#         plot_bgcolor="rgba(0,0,0,0)"
#     )

#     fig.update_yaxes(fixedrange=False)

#     return fig


def plot_chart_with_signals(df, sr_levels, trades_df, title, show_volume=True):
    import plotly.graph_objects as go

    fig = go.Figure()

    # ===================== CANDLESTICKS =====================
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
        increasing=dict(line=dict(width=1.5, color="#00ff99")),
        decreasing=dict(line=dict(width=1.5, color="#ff4d4d"))
    ))

    # ===================== VOLUME =====================
    if show_volume and "volume" in df.columns:
        fig.add_trace(go.Bar(
            x=df.index,
            y=df["volume"],
            name="Volume",
            yaxis="y2",
            opacity=0.25
        ))

    # ===================== ENTRY / EXIT =====================
    if trades_df is not None and not trades_df.empty:
        fig.add_trace(go.Scatter(
            x=trades_df["entry_date"],
            y=trades_df["entry_price"],
            mode="markers",
            marker=dict(symbol="triangle-up", size=13, color="lime"),
            name="ENTRY"
        ))

        fig.add_trace(go.Scatter(
            x=trades_df["exit_date"],
            y=trades_df["exit_price"],
            mode="markers",
            marker=dict(symbol="x", size=12, color="red"),
            name="EXIT"
        ))

    # ===================== SR LEVELS =====================
    level_colors = {
        "L1": "#2E86C1", "L2": "#2874A6", "L3": "#21618C",
        "L4": "#1B4F72", "L5": "#154360", "L6": "#0E2A38",
        "P1": "#E74C3C", "P2": "#CB4335", "P3": "#B03A2E",
        "P4": "#943126", "P5": "#78281F", "P6": "#641E16",
        "Average": "#16A085",
        "High (Ref)": "#F1C40F"
    }

    for k, v in sr_levels.items():
        try:
            fig.add_hline(
                y=float(v),
                line_dash="dot",
                line=dict(width=2, color=level_colors.get(k, "#7F8C8D")),
                annotation_text=f"{k}: {v:.2f}",
                annotation_position="top left"
            )
        except:
            pass

    # ===================== LAYOUT (STATIC CHART) =====================
    fig.update_layout(
        title=title,
        height=750,
        hovermode="x unified",
        template="plotly_dark",

        dragmode=False,               # ❌ disable zoom & pan
        xaxis=dict(
            showgrid=False,
            fixedrange=True,          # ❌ disable scroll/zoom
            rangeslider=dict(visible=False)  # ❌ remove scrollbar
        ),
        yaxis=dict(
            showgrid=False,
            fixedrange=True
        ),
        yaxis2=dict(
            overlaying="y",
            side="right",
            showgrid=False,
            title="Volume" if show_volume else None,
            fixedrange=True
        ),

        plot_bgcolor="rgba(0,0,0,0)"
    )

    return fig


# =====================================================
# SYMBOL LIST
# =====================================================

@st.cache_data(ttl=86400)
def get_nifty500_symbols():

    url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.nseindia.com/"
    }

    session = requests.Session()
    session.headers.update(headers)

    try:
        # Step 1: Warm-up request (important)
        session.get(
            "https://www.nseindia.com",
            timeout=15
        )

        time.sleep(1)

        # Step 2: Actual CSV request
        response = session.get(
            url,
            timeout=20
        )

        response.raise_for_status()

        df = pd.read_csv(StringIO(response.text))
        symbols = sorted(df["Symbol"].dropna().unique().tolist())
        return symbols

    except Exception as e:
        st.warning("⚠ NSE not responding. Using fallback symbol list.")

        # 🔒 SAFE FALLBACK (app will NEVER crash)
        return [
            "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
            "SBIN", "LT", "ITC", "AXISBANK", "BAJFINANCE",
            "HINDUNILVR", "KOTAKBANK", "MARUTI", "SUNPHARMA"
        ]





# =====================================================
# UI
# =====================================================
base_year = st.selectbox("Base FY",["2020-2021","2021-2022","2022-2023","2023-2024","2024-2025"])
march_year = st.selectbox("March Close Year",[2023,2024,2025],index=1)

# =====================================================
# SCAN
# =====================================================
def process_symbol(sym):
    try:
        symbol=f"NSE:{sym}-EQ"
        df=fetch_5yr_data(symbol)
        print(f"Processed: {symbol}")
        # print(df)
        if df.empty: return sym,None,"No data"

        fy=df.loc[
            (df.index>=dt.datetime(int(base_year[:4]),4,1)) &
            (df.index<=dt.datetime(int(base_year[5:]),3,31))
        ]
        if fy.empty: return sym,None,"FY missing"

        sr=calculate_sr_levels(fy)
        march_close=df.loc[df.index<=dt.datetime(march_year,3,31),"close"].iloc[-1]

        bt_df=df[df.index>dt.datetime(march_year,3,31)]
        trades,wk=find_weekly_buy_trades(bt_df,sr,march_close)
        print(trades)

        if trades.empty:
            return sym,None,"No trades"

        return sym,{"trades":trades,"df":wk,"sr":sr},None
    except Exception as e:
        return sym,None,str(e)

# if st.button("SCAN ALL STOCKS"):
#     st.session_state.trade_stocks.clear()
#     st.session_state.scan_log.clear()

#     symbols=get_nifty500_symbols()
#     progress=st.progress(0)

#     with ThreadPoolExecutor(max_workers=8) as ex:
#         futs=[ex.submit(process_symbol,s) for s in symbols]
#         for i,f in enumerate(as_completed(futs)):
#             sym,data,log=f.result()
#             if data: st.session_state.trade_stocks[sym]=data
#             if log: st.session_state.scan_log.append(f"{sym}: {log}")
#             progress.progress((i+1)/len(symbols))

#     st.session_state.scan_done=True
#     st.success("Scan Completed")

# ================= SCAN BUTTON =================
if st.button("SCAN ALL STOCKS"):
    st.session_state.trade_stocks.clear()
    st.session_state.scan_log.clear()
    st.session_state.scan_done = False

    symbols = get_nifty500_symbols()

    progress_placeholder = st.empty()
    progress = progress_placeholder.progress(0)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = [ex.submit(process_symbol, s) for s in symbols]
        total = len(futs)

        for i, f in enumerate(as_completed(futs)):
            sym, data, log = f.result()

            if data:
                st.session_state.trade_stocks[sym] = data
            if log:
                st.session_state.scan_log.append(f"{sym}: {log}")

            progress.progress((i + 1) / total)

    progress_placeholder.empty()
    st.session_state.scan_done = True
    st.success("Scan completed successfully")


# =====================================================
# RESULTS
# =====================================================


# if st.session_state.scan_done and st.session_state.trade_stocks:
#     selected=st.sidebar.selectbox("Stocks",sorted(st.session_state.trade_stocks.keys()))
#     data=st.session_state.trade_stocks[selected]
#     st.dataframe(data["trades"],use_container_width=True)
#     st.plotly_chart(plot_chart(data["df"],data["sr"],f"{selected} Weekly Chart"),use_container_width=True)


# ================= RESULTS =================
if st.session_state.scan_done and st.session_state.trade_stocks:
    selected = st.sidebar.selectbox(
        "Stocks",
        sorted(st.session_state.trade_stocks.keys())
    )

    data = st.session_state.trade_stocks[selected]

    st.subheader(f"{selected} – Trades")
    st.dataframe(data["trades"], use_container_width=True)

    st.subheader("Weekly Chart")

    # st.plotly_chart(
    #     plot_chart(data["df"], data["sr"], f"{selected} Weekly Chart"),
    #     use_container_width=True
    # )


    # show_volume = st.sidebar.checkbox("Show Volume", value=True)

    # st.plotly_chart(
    # plot_chart_with_signals(
    #     df=data["df"],
    #     sr_levels=data["sr"],
    #     trades_df=data["trades"],
    #     title=f"{selected} – Weekly S/R Buy Setup",
    #     show_volume=True
    # ),
    # use_container_width=True
    # )

    show_volume = st.checkbox("Show Volume", value=True)

    st.plotly_chart(
    plot_chart_with_signals(
        df=data["df"],
        sr_levels=data["sr"],
        trades_df=data["trades"],
        title=f"{selected} – Weekly S/R Buy Setup",
        show_volume=show_volume
    ),
    use_container_width=True,
    config={"scrollZoom": False}
    )


