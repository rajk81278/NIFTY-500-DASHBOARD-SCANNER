# # # # streamlit run weekly_LL.py

import streamlit as st
import pandas as pd
import datetime as dt
from fyers_apiv3 import fyersModel
import time
import requests
from io import StringIO
import warnings
import os

warnings.filterwarnings("ignore")

# -----------------------------
# Load Fyers Token
# -----------------------------
with open("access.txt", "r") as a:
    access_token = a.read().strip()

client_id = "5YKT940X4B-100"
fyers = fyersModel.FyersModel(client_id=client_id, token=access_token)

# -----------------------------
# Cache Setup
# -----------------------------
CACHE_DIR = "data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def _sanitize_symbol(symbol: str) -> str:
    return symbol.replace(":", "_").replace("/", "_").replace(" ", "_")

def _cache_path(symbol: str):
    return os.path.join(CACHE_DIR, f"{_sanitize_symbol(symbol)}.parquet")

def load_cache(symbol: str):
    if os.path.exists(_cache_path(symbol)):
        try:
            return pd.read_parquet(_cache_path(symbol)).sort_index()
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def save_cache(symbol: str, df: pd.DataFrame):
    if not df.empty:
        df.to_parquet(_cache_path(symbol))

# -----------------------------
# Fetch Data from Fyers
# -----------------------------
def fetch_month_data(symbol, from_date, to_date):
    try:
        data = fyers.history({
            "symbol": symbol,
            "resolution": "1D",
            "date_format": "1",
            "range_from": from_date,
            "range_to": to_date,
            "cont_flag": "1"
        })
        if data.get("s") == "ok" and "candles" in data:
            df = pd.DataFrame(data["candles"], columns=["date","open","high","low","close","volume"])
            df["date"] = pd.to_datetime(df["date"], unit="s")
            df.set_index("date", inplace=True)
            return df
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def fetch_5yr_data_monthwise(symbol, end_date=None, years=6, force_refresh=False):
    if end_date is None:
        end_date = dt.datetime.now()

    requested_start = end_date - dt.timedelta(days=years * 365)
    requested_end = end_date

    if not force_refresh:
        cached = load_cache(symbol)
        if cached.index.min() <= requested_start and cached.index.max() >= requested_end:
            return cached.loc[(cached.index>=requested_start)&(cached.index<=requested_end)]

    parts = []
    current = requested_start
    while current <= requested_end:
        nxt = min(current + dt.timedelta(days=30), requested_end)
        chunk = fetch_month_data(symbol, current.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d"))
        if not chunk.empty:
            parts.append(chunk)
        current = nxt + dt.timedelta(days=1)
        time.sleep(0.1)

    if parts:
        df_all = pd.concat(parts).sort_index()
        df_all = df_all[~df_all.index.duplicated()]
        save_cache(symbol, df_all)
        return df_all
    return pd.DataFrame()


def calculate_sr_levels(df):
    if df.empty:
        sr_dict = {f"L{i}": 0.0 for i in range(1, 7)}
        sr_dict.update({f"P{i}": 0.0 for i in range(1, 7)})
        sr_dict["Average"] = 0.0
        sr_dict["High (Ref)"] = 0.0
        sr_dict["% Change"] = 0.0
        return sr_dict

    high = float(df["high"].max())
    low = float(df["low"].min())
    percent_change = (high - low) / high if high != 0 else 0.0
    avg = (high + low) / 2.0

    supports = []
    L1 = high - (high * percent_change)
    supports.append(L1)
    for i in range(1, 6):
        prev = supports[i - 1]
        next_level = prev - (prev * percent_change)
        supports.append(next_level)
    supports = list(reversed(supports))  # lower to higher

    resistances = []
    P1 = high + (high * percent_change)
    resistances.append(P1)
    for i in range(1, 6):
        prev = resistances[i - 1]
        next_level = prev + (prev * percent_change)
        resistances.append(next_level)

    # Reassign new labels so L1 = highest, L6 = lowest
    supports = list(reversed(supports))
    sr_dict = {}
    for i, level in enumerate(supports, start=1):
        sr_dict[f"L{i}"] = round(level, 2)
    for i, level in enumerate(resistances, start=1):
        sr_dict[f"P{i}"] = round(level, 2)
    sr_dict["Average"] = round(avg, 2)
    sr_dict["High (Ref)"] = round(high, 2)
    sr_dict["% Change"] = round(percent_change * 100, 2)
    return sr_dict

# -----------------------------
# Weekly Trade Logic
# -----------------------------
def find_weekly_buy_trades(df_daily, sr_levels, march_close_price):
    df_weekly = df_daily.resample('W').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
    df_weekly.dropna(inplace=True)

    ul_pool = [float(sr_levels.get(f"P{i}")) for i in range(1,7)] + [float(sr_levels.get("Average")), float(sr_levels.get("High (Ref)"))]
    ll_pool = [float(sr_levels.get(f"L{i}")) for i in range(1,7)]

    ul_pool = [x for x in ul_pool if x>march_close_price and x>0]
    ll_pool = [x for x in ll_pool if x<march_close_price and x>0]

    if not ul_pool or not ll_pool:
        return pd.DataFrame(), df_weekly

    nearest_ul = min(ul_pool, key=lambda x: abs(x - march_close_price))
    nearest_ll = min(ll_pool, key=lambda x: abs(x - march_close_price))

    df_weekly = df_weekly[df_weekly['low'] > nearest_ll]
    base_bars = df_weekly[df_weekly['close'] > nearest_ll]

    if base_bars.empty:
        return pd.DataFrame(), df_weekly

    weeks = df_weekly.index
    n = len(df_weekly)
    i = 0
    trades = []

    while i < n:
        if weeks[i] not in base_bars.index:
            i+=1
            continue

        base_idx=i
        base_low=df_weekly.iloc[i]['low']
        if base_idx+3>=n: break

        fail=False
        for k in range(base_idx+1, base_idx+4):
            if df_weekly.iloc[k]['close']>nearest_ul or df_weekly.iloc[k]['close']<nearest_ll or df_weekly.iloc[k]['low']<=base_low:
                fail=True; break
        if fail: i=k+1; continue

        entry_idx=base_idx+4
        if entry_idx>=n: break
        entry_price=df_weekly.iloc[entry_idx]['open']
        entry_date=weeks[entry_idx]

        end3=min(n-1, entry_idx+3)
        exit_price=None; exit_idx=None; exit_date=None
        for k in range(entry_idx, end3+1):
            if df_weekly.iloc[k]['high']>=nearest_ul:
                exit_price=nearest_ul; exit_idx=k; exit_date=weeks[k]; break
        if exit_price is None:
            exit_idx=min(n-1, entry_idx+5); exit_date=weeks[exit_idx]; exit_price=df_weekly.iloc[exit_idx]['close']

        pnl=round(((exit_price-entry_price)/entry_price)*100,2)
        trades.append({'entry_idx':entry_idx,'entry_date':entry_date,'entry_price':entry_price,'exit_idx':exit_idx,'exit_date':exit_date,'exit_price':exit_price,'pnl_pct':pnl,'ul':nearest_ul,'ll':nearest_ll,'base_date':weeks[base_idx]})
        i=exit_idx+1

    return pd.DataFrame(trades), df_weekly

def backtest_weekly_symbol(df_daily, sr_levels, march_close_price):
    trades_df, df_marked = find_weekly_buy_trades(df_daily, sr_levels, march_close_price)
    df_marked['marker']=''
    for _,t in trades_df.iterrows():
        df_marked.at[df_marked.index[t['entry_idx']], 'marker']='ENTRY'
        df_marked.at[df_marked.index[t['exit_idx']], 'marker']='EXIT'
    return trades_df, df_marked


import plotly.graph_objects as go

# def plot_chart_with_signals(df, sr_levels, annotated_df, title, show_volume=True, show_all_levels=False):
#     fig = go.Figure()

#     # Candles
#     fig.add_trace(go.Candlestick(
#         x=df.index,
#         open=df["open"],
#         high=df["high"],
#         low=df["low"],
#         close=df["close"],
#         name="Price"
#     ))

#     # Volume
#     if show_volume and "volume" in df.columns:
#         fig.add_trace(go.Bar(
#             x=df.index,
#             y=df["volume"],
#             name="Volume",
#             yaxis="y2",
#             opacity=0.3
#         ))

#     # Entry/Exit markers
#     e = annotated_df[annotated_df["marker"] == "ENTRY"]
#     x = annotated_df[annotated_df["marker"] == "EXIT"]

#     if not e.empty:
#         fig.add_trace(go.Scatter(
#             x=e.index,
#             y=e["close"],
#             mode="markers",
#             marker_symbol="triangle-up",
#             marker_size=14,
#             name="ENTRY"
#         ))

#     if not x.empty:
#         fig.add_trace(go.Scatter(
#             x=x.index,
#             y=x["close"],
#             mode="markers",
#             marker_symbol="x",
#             marker_size=14,
#             name="EXIT"
#         ))

#     # SR Level lines
#     for k, v in sr_levels.items():
#         try:
#             lvl = float(v)
#             if lvl > 0:
#                 fig.add_hline(
#                     y=lvl,
#                     line_dash="dot",
#                     annotation_text=f"{k}: {lvl:.2f}",
#                     annotation_position="bottom left"
#                 )
#         except:
#             pass

#     # Layout
#     fig.update_layout(
#         title=title,
#         xaxis_title="Date",
#         yaxis_title="Price",
#         height=700,
#         dragmode="pan",
#         hovermode="x unified",
#         yaxis2=dict(
#             overlaying='y',
#             side='right',
#             showgrid=False,
#             title="Volume" if show_volume else None
#         )
#     )

#     fig.update_xaxes(rangeslider=dict(visible=True), showgrid=True)
#     fig.update_yaxes(fixedrange=False, showgrid=True)

#     return fig

def plot_chart_with_signals(df, sr_levels, annotated_df, title, show_volume=True, show_all_levels=False):
    import plotly.graph_objects as go

    fig = go.Figure()

    # Candles with red/green coloring
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
        increasing=dict(line=dict(width=1.5)),
        decreasing=dict(line=dict(width=1.5))
    ))

    # Volume
    if show_volume and "volume" in df.columns:
        fig.add_trace(go.Bar(
            x=df.index,
            y=df["volume"],
            name="Volume",
            yaxis="y2",
            opacity=0.3
        ))

    # Entry/Exit markers
    entry_df = annotated_df[annotated_df["marker"] == "ENTRY"]
    exit_df  = annotated_df[annotated_df["marker"] == "EXIT"]

    if not entry_df.empty:
        fig.add_trace(go.Scatter(
            x=entry_df.index,
            y=entry_df["close"],
            mode="markers",
            marker_symbol="triangle-up",
            marker_size=12,
            name="ENTRY"
        ))

    if not exit_df.empty:
        fig.add_trace(go.Scatter(
            x=exit_df.index,
            y=exit_df["close"],
            mode="markers",
            marker_symbol="x",
            marker_size=12,
            name="EXIT"
        ))

    # Plot SR Levels in different colors
    level_colors = {
        "L1": "#2E86C1", "L2": "#2874A6", "L3": "#21618C", "L4": "#1B4F72", "L5": "#154360", "L6": "#0E2A38",
        "P1": "#E74C3C", "P2": "#CB4335", "P3": "#B03A2E", "P4": "#943126", "P5": "#78281F", "P6": "#641E16",
        "Average": "#16A085",
        "High (Ref)": "#F1C40F"
    }

    for key, value in sr_levels.items():
        try:
            lvl = float(value)
            if lvl > 0:
                fig.add_hline(
                    y=lvl,
                    line_dash="dot",
                    line=dict(width=2, color=level_colors.get(key, "#7F8C8D")),
                    annotation_text=f"{key}: {lvl:.2f}",
                    annotation_position="top left"
                )
        except:
            pass

    # Layout changes: remove grid and set height
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Price",
        height=700,
        dragmode="pan",
        hovermode="x unified",

        # Remove gridlines
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False),

        # Secondary axis for volume without grid
        yaxis2=dict(
            overlaying='y',
            side='right',
            showgrid=False,
            title="Volume" if show_volume else None
        ),

        # Remove plot area background grid
        plot_bgcolor="rgba(0,0,0,0)"
    )

    # Ensure no fixed range locking
    fig.update_yaxes(fixedrange=False)

    return fig


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Weekly SR Backtest", layout="wide")
st.title("Weekly S/R BASE → BUY Engine")

base_year = st.selectbox("Select Base FY", ["2020-2021","2021-2022","2022-2023","2023-2024","2024-2025"])
march_year = st.selectbox("Select March Close Year", [2023,2024,2025,2026], index=1)

# # symbol selection
# @st.cache_data(ttl=86400)
# def get_nifty500_symbols():
#     url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
#         "Referer": "https://www.nseindia.com/",
#     }
#     s = requests.Session()
#     try:
#         s.get("https://www.nseindia.com", headers=headers, timeout=5)
#         r = s.get(url, headers=headers, timeout=10)
#         df = pd.read_csv(StringIO(r.text))
#         stock_list = df['Symbol'].dropna().unique().tolist()
#         stock_list.sort()
#         return stock_list
#     except Exception:
#         return ["SBIN", "TCS", "RELIANCE"]

@st.cache_data(ttl=86400)
def get_nifty500_symbols():
    url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nseindia.com/",
    }
    s = requests.Session()
    try:
        s.get("https://www.nseindia.com", headers=headers, timeout=5)
        r = s.get(url, headers=headers, timeout=10)
        df = pd.read_csv(StringIO(r.text))
        stock_list = df['Symbol'].dropna().unique().tolist()
        stock_list.sort()
        return stock_list
    except:
        return ["SBIN", "TCS", "RELIANCE"]

symbols = st.selectbox("Select symbol", get_nifty500_symbols(), index=0)
segment = st.selectbox("Segment", ['EQ','FUT'])
symbol_full = f"NSE:{symbols}-{'EQ' if segment=='EQ' else 'FUT'}"

plot_all = st.sidebar.checkbox("Plot all SR levels", True)
show_vol = st.sidebar.checkbox("Show Volume", True)

# if st.button("Run Weekly Backtest"):
#     df_all = fetch_5yr_data_monthwise(symbol_full, years=6)
#     if df_all.empty:
#         st.error("No data found")
#     else:
#         fy = df_all.loc[(df_all.index>=dt.datetime(int(base_year.split('-')[0]),4,1))&(df_all.index<=dt.datetime(int(base_year.split('-')[1]),3,31))]
#         sr = calculate_sr_levels(fy)

#         march = df_all.loc[:dt.datetime(int(march_year),3,31)]
#         march_close = march['close'].iloc[-1]

#         df_bt = df_all.loc[df_all.index>dt.datetime(int(march_year),3,31)]
#         trades, marked = backtest_weekly_symbol(df_bt, sr, march_close)

#         st.dataframe(trades[['entry_date','entry_price','exit_date','exit_price','pnl_pct','base_date']], use_container_width=True)
#         st.download_button("Download CSV", trades.to_csv(index=False).encode(), "weekly_bt.csv")

#         fig = plot_chart_with_signals(marked, sr, marked, f"{symbols} Weekly BT", show_vol=show_vol)
#         st.plotly_chart(fig, use_container_width=True, config={"scrollZoom":True,"doubleClick":"reset"})



if st.button("Run Weekly Backtest"):
    df_all = fetch_5yr_data_monthwise(symbol_full, years=6)
    if df_all.empty:
        st.error("No data found")
    else:
        fy = df_all.loc[
            (df_all.index >= dt.datetime(int(base_year.split('-')[0]), 4, 1)) &
            (df_all.index <= dt.datetime(int(base_year.split('-')[1]), 3, 31))
        ]
        sr = calculate_sr_levels(fy)

        march = df_all.loc[:dt.datetime(int(march_year), 3, 31)]
        march_close = march['close'].iloc[-1]

        df_bt = df_all.loc[df_all.index > dt.datetime(int(march_year), 3, 31)]
        trades_df, marked_df = backtest_weekly_symbol(df_bt, sr, march_close)

        # Show trade table
        if not trades_df.empty:
            st.dataframe(
                trades_df[['entry_date','entry_price','exit_date','exit_price','pnl_pct','ul','ll','base_date']],
                use_container_width=True
            )
            st.download_button("Download CSV", trades_df.to_csv(index=False).encode(), "weekly_bt.csv")
        else:
            st.warning("No trades generated")

        # Add Base / Buy / Exit annotations on chart
        marked_df['marker'] = marked_df['marker'].fillna('')
        marked_df['candle_type'] = ''  # for labeling base candles

        # Mark base candles
        base_indices = marked_df[marked_df.index.isin(trades_df['base_date'])].index
        for idx in base_indices:
            marked_df.at[idx, 'candle_type'] = 'BASE'

        # Plot chart
        fig = plot_chart_with_signals(
            marked_df,
            sr,
            marked_df,
            title=f"{symbols} Weekly BT",
            show_volume=show_vol
        )

        # Add custom scatter annotations for base/buy/exit
        base_df = marked_df[marked_df['candle_type'] == 'BASE']
        entry_df = marked_df[marked_df['marker'] == 'ENTRY']
        exit_df  = marked_df[marked_df['marker'] == 'EXIT']

        if not base_df.empty:
            fig.add_trace(go.Scatter(
                x=base_df.index,
                y=base_df['low'],
                mode='text+markers',
                text=['Base Candle']*len(base_df),
                textposition='bottom center',
                marker_size=12,
                name='Base'
            ))

        if not entry_df.empty:
            fig.add_trace(go.Scatter(
                x=entry_df.index,
                y=entry_df['low'],
                mode='text+markers',
                text=['BUY']*len(entry_df),
                textposition='top center',
                marker_size=12,
                name='Buy Signal'
            ))

        if not exit_df.empty:
            fig.add_trace(go.Scatter(
                x=exit_df.index,
                y=exit_df['high'],
                mode='text+markers',
                text=['Exit']*len(exit_df),
                textposition='top center',
                marker_size=12,
                name='Exit Signal'
            ))

        st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "doubleClick": "reset"})



#######################################################################################################


# import streamlit as st
# import pandas as pd
# import datetime as dt
# from fyers_apiv3 import fyersModel
# import time
# import requests
# from io import StringIO
# import warnings
# import os

# warnings.filterwarnings("ignore")

# # -----------------------------
# # Load Fyers Token
# # -----------------------------
# with open("access.txt", "r") as a:
#     access_token = a.read().strip()

# client_id = "5YKT940X4B-100"
# fyers = fyersModel.FyersModel(client_id=client_id, token=access_token)

# # -----------------------------
# # Cache Setup
# # -----------------------------
# CACHE_DIR = "data_cache"
# os.makedirs(CACHE_DIR, exist_ok=True)

# def _sanitize_symbol(symbol: str) -> str:
#     return symbol.replace(":", "_").replace("/", "_").replace(" ", "_")

# def _cache_path(symbol: str):
#     return os.path.join(CACHE_DIR, f"{_sanitize_symbol(symbol)}.parquet")

# def load_cache(symbol: str):
#     if os.path.exists(_cache_path(symbol)):
#         try:
#             return pd.read_parquet(_cache_path(symbol)).sort_index()
#         except:
#             return pd.DataFrame()
#     return pd.DataFrame()

# def save_cache(symbol: str, df: pd.DataFrame):
#     if not df.empty:
#         df.to_parquet(_cache_path(symbol))

# # -----------------------------
# # Fetch Data from Fyers
# # -----------------------------
# def fetch_month_data(symbol, from_date, to_date):
#     try:
#         data = fyers.history({
#             "symbol": symbol,
#             "resolution": "1D",
#             "date_format": "1",
#             "range_from": from_date,
#             "range_to": to_date,
#             "cont_flag": "1"
#         })
#         if data.get("s") == "ok" and "candles" in data:
#             df = pd.DataFrame(data["candles"], columns=["date","open","high","low","close","volume"])
#             df["date"] = pd.to_datetime(df["date"], unit="s")
#             df.set_index("date", inplace=True)
#             return df
#         return pd.DataFrame()
#     except:
#         return pd.DataFrame()

# def fetch_5yr_data_monthwise(symbol, end_date=None, years=6, force_refresh=False):
#     if end_date is None:
#         end_date = dt.datetime.now()

#     requested_start = end_date - dt.timedelta(days=years * 365)
#     requested_end = end_date

#     if not force_refresh:
#         cached = load_cache(symbol)
#         if not cached.empty and cached.index.min() <= requested_start and cached.index.max() >= requested_end:
#             return cached.loc[(cached.index>=requested_start)&(cached.index<=requested_end)]

#     parts = []
#     current = requested_start
#     while current <= requested_end:
#         nxt = min(current + dt.timedelta(days=30), requested_end)
#         chunk = fetch_month_data(symbol, current.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d"))
#         if not chunk.empty:
#             parts.append(chunk)
#         current = nxt + dt.timedelta(days=1)
#         time.sleep(0.1)

#     if parts:
#         df_all = pd.concat(parts).sort_index()
#         df_all = df_all[~df_all.index.duplicated()]
#         save_cache(symbol, df_all)
#         return df_all
#     return pd.DataFrame()

# # -----------------------------
# # SR Levels Calculation
# # -----------------------------
# def calculate_sr_levels(df):
#     if df.empty:
#         sr_dict = {f"L{i}": 0.0 for i in range(1, 7)}
#         sr_dict.update({f"P{i}": 0.0 for i in range(1, 7)})
#         sr_dict["Average"] = 0.0
#         sr_dict["High (Ref)"] = 0.0
#         sr_dict["% Change"] = 0.0
#         return sr_dict

#     high = float(df["high"].max())
#     low = float(df["low"].min())
#     percent_change = (high - low) / high if high != 0 else 0.0
#     avg = (high + low) / 2.0

#     supports = []
#     L1 = high - (high * percent_change)
#     supports.append(L1)
#     for i in range(1, 6):
#         prev = supports[i - 1]
#         supports.append(prev - (prev * percent_change))
#     supports = list(reversed(supports))
#     supports = list(reversed(supports))

#     resistances = []
#     P1 = high + (high * percent_change)
#     resistances.append(P1)
#     for i in range(1, 6):
#         prev = resistances[i - 1]
#         resistances.append(prev + (prev * percent_change))

#     sr_dict = {}
#     for i, level in enumerate(supports, start=1):
#         sr_dict[f"L{i}"] = round(level, 2)
#     for i, level in enumerate(resistances, start=1):
#         sr_dict[f"P{i}"] = round(level, 2)

#     sr_dict["Average"] = round(avg, 2)
#     sr_dict["High (Ref)"] = round(high, 2)
#     sr_dict["% Change"] = round(percent_change * 100, 2)
#     return sr_dict

# # -----------------------------
# # Weekly Trade Logic with 2 Buy Scenarios
# # -----------------------------
# def find_weekly_buy_trades(df_daily, sr_levels, march_close_price):
#     df_weekly = df_daily.resample('W').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'})
#     df_weekly.dropna(inplace=True)

#     # Build UL & LL pool
#     ul_pool = [float(sr_levels.get(f"P{i}")) for i in range(1,7)] + [float(sr_levels.get("Average")), float(sr_levels.get("High (Ref)"))]
#     ll_pool = [float(sr_levels.get(f"L{i}")) for i in range(1,7)]

#     # -------- Scenario 1 (Existing logic) ----------
#     nearest_ul = min([x for x in ul_pool if x > march_close_price], key=lambda x: abs(x - march_close_price), default=None)
#     nearest_ll = min([x for x in ll_pool if x < march_close_price], key=lambda x: abs(x - march_close_price), default=None)

#     trades = []

#     if nearest_ul and nearest_ll:
#         base_bars = df_weekly[df_weekly['close'] > nearest_ll]

#         weeks = df_weekly.index.tolist()
#         n = len(df_weekly)
#         i = 0

#         while i < n:
#             if weeks[i] not in base_bars.index:
#                 i+=1
#                 continue

#             base_idx=i
#             base_low=df_weekly.iloc[i]['low']
#             if base_idx+3>=n: break

#             fail=False
#             for k in range(base_idx+1, base_idx+4):
#                 if df_weekly.iloc[k]['close']>nearest_ul or df_weekly.iloc[k]['close']<nearest_ll or df_weekly.iloc[k]['low']<=base_low:
#                     fail=True; break
#             if fail: i=k+1; continue

#             entry_idx=base_idx+4
#             if entry_idx>=n: break
#             entry_price=df_weekly.iloc[entry_idx]['open']
#             entry_date=weeks[entry_idx]

#             end3=min(n-1, entry_idx+3)
#             exit_price=None; exit_idx=None; exit_date=None
#             for k in range(entry_idx, end3+1):
#                 if df_weekly.iloc[k]['high']>=nearest_ul:
#                     exit_price=nearest_ul; exit_idx=k; exit_date=weeks[k]; break
#             if exit_price is None:
#                 exit_idx=min(n-1, entry_idx+5); exit_date=weeks[exit_idx]; exit_price=df_weekly.iloc[exit_idx]['close']

#             pnl=round(((exit_price-entry_price)/entry_price)*100,2)
#             trades.append({'entry_idx':entry_idx,'entry_date':entry_date,'entry_price':entry_price,'exit_idx':exit_idx,'exit_date':exit_date,'exit_price':exit_price,'pnl_pct':pnl,'ul':nearest_ul,'ll':nearest_ll,'base_date':weeks[base_idx]})
#             i=exit_idx+1

#     # -------- Scenario 2 (New logic added) ----------
#     # 1-year prior FY low guard
#     march_year = march_close_price  # reference year not needed explicitly
#     prev_fy_start = dt.datetime(int(st.session_state.get("march_year", 2024)) - 1, 4, 1)
#     prev_fy_end   = dt.datetime(int(st.session_state.get("march_year", 2024)), 3, 31)
#     prev_fy_low   = float(df_daily.loc[(df_daily.index >= prev_fy_start) & (df_daily.index <= prev_fy_end)]['low'].min())

#     # Inclusion candle = weekly close above UL after March 31
#     inclusion_df = df_weekly[df_weekly.index > dt.datetime(int(st.session_state.get("march_year", 2024)),3,31)]
#     inclusion_df = inclusion_df[inclusion_df['close'] > nearest_ul] if nearest_ul else pd.DataFrame()

#     for name, row in inclusion_df.iterrows():
#         inc_close = row['close']

#         # next higher UL
#         higher_uls = [x for x in ul_pool if x > inc_close]
#         if not higher_uls:
#             continue
#         next_ul = min(higher_uls, key=lambda x: abs(x - inc_close))

#         # take next 15 weeks slice
#         pos = df_weekly.index.get_loc(name)
#         val_slice = df_weekly.iloc[pos+1: pos+16]  # 15 candles

#         if len(val_slice) < 15:
#             continue

#         # Validation rules
#         if (val_slice['close'].min() > march_close_price and
#             val_slice['close'].max() < next_ul and
#             val_slice['close'].min() > prev_fy_low):

#             entry_week = val_slice.iloc[14]  # 15th candle
#             trades.append({
#                 'entry_date': entry_week.name,
#                 'entry_price': entry_week['close'],
#                 'exit_date': None,
#                 'exit_price': None,
#                 'pnl_pct': 0.0,
#                 'ul': next_ul,
#                 'll': march_close_price,
#                 'base_date': name
#             })

#     return pd.DataFrame(trades), df_weekly

# def backtest_weekly_symbol(df_daily, sr_levels, march_close_price):
#     trades_df, weekly_df = find_weekly_buy_trades(df_daily, sr_levels, march_close_price)
#     weekly_df['marker']=''
#     for _,t in trades_df.iterrows():
#         if t['exit_date'] in weekly_df.index:
#             weekly_df.at[t['entry_date'], 'marker']='ENTRY'
#     return trades_df, weekly_df

# # -----------------------------
# # Plotting Function
# # -----------------------------
# def plot_chart_with_signals(df, sr_levels, annotated_df, title, show_volume=True, show_all_levels=False):
#     import plotly.graph_objects as go
#     fig = go.Figure()
#     fig.add_trace(go.Candlestick(x=df.index,open=df["open"],high=df["high"],low=df["low"],close=df["close"],name="Price"))
#     return fig

# # -----------------------------
# # Streamlit UI
# # -----------------------------
# st.set_page_config(page_title="Weekly SR Backtest", layout="wide")
# st.title("Weekly S/R BASE → BUY Engine")

# march_close_year = march_year
# st.session_state["march_year"] = march_close_year

# # symbol selection
# @st.cache_data(ttl=86400)
# def get_nifty500_symbols():
#     try:
#         return ["SBIN", "TCS", "RELIANCE"]
#     except:
#         return ["SBIN"]

# symbols = st.selectbox("Select symbol", get_nifty500_symbols(), index=0)
# symbol_full = f"NSE:{symbols}-EQ"

# if st.button("Run Weekly Backtest"):
#     df_all = fetch_5yr_data_monthwise(symbol_full, years=6)
#     if df_all.empty:
#         st.error("No data found")
#     else:
#         sr = calculate_sr_levels(df_all)
#         march_price = df_all['close'].iloc[-1]
#         trades_df, marked_df = backtest_weekly_symbol(df_all, sr, march_price)
#         st.dataframe(trades_df, use_container_width=True)
#         st.plotly_chart(plot_chart_with_signals(marked_df, sr, marked_df, "Weekly BT"), use_container_width=True)



#####################################################################################################################################
############### For loop for all symbol


# # streamlit run weekly_LL.py

# import streamlit as st
# import pandas as pd
# import datetime as dt
# from fyers_apiv3 import fyersModel
# import time
# import requests
# from io import StringIO
# import warnings
# import os
# import plotly.graph_objects as go

# warnings.filterwarnings("ignore")

# # =====================================================
# # STREAMLIT CONFIG
# # =====================================================
# st.set_page_config(page_title="Weekly SR Scanner", layout="wide")
# st.title("Weekly S/R BASE → BUY SCANNER")

# # =====================================================
# # SESSION STATE
# # =====================================================
# if "scan_done" not in st.session_state:
#     st.session_state.scan_done = False

# if "trade_stocks" not in st.session_state:
#     st.session_state.trade_stocks = {}

# # =====================================================
# # FYERS LOGIN
# # =====================================================
# with open("access.txt", "r") as a:
#     access_token = a.read().strip()

# client_id = "5YKT940X4B-100"
# fyers = fyersModel.FyersModel(client_id=client_id, token=access_token)

# # =====================================================
# # CACHE SETUP
# # =====================================================
# CACHE_DIR = "data_cache"
# os.makedirs(CACHE_DIR, exist_ok=True)

# def _sanitize_symbol(symbol):
#     return symbol.replace(":", "_").replace("-", "_")

# def _cache_path(symbol):
#     return os.path.join(CACHE_DIR, f"{_sanitize_symbol(symbol)}.parquet")

# def load_cache(symbol):
#     if os.path.exists(_cache_path(symbol)):
#         return pd.read_parquet(_cache_path(symbol))
#     return pd.DataFrame()

# def save_cache(symbol, df):
#     if not df.empty:
#         df.to_parquet(_cache_path(symbol))

# # =====================================================
# # DATA FETCH
# # =====================================================
# def fetch_month_data(symbol, start, end):
#     data = fyers.history({
#         "symbol": symbol,
#         "resolution": "1D",
#         "date_format": "1",
#         "range_from": start,
#         "range_to": end,
#         "cont_flag": "1"
#     })
#     if data.get("s") == "ok":
#         df = pd.DataFrame(
#             data["candles"],
#             columns=["date","open","high","low","close","volume"]
#         )
#         df["date"] = pd.to_datetime(df["date"], unit="s")
#         df.set_index("date", inplace=True)
#         return df
#     return pd.DataFrame()

# def fetch_5yr_data(symbol, years=6):
#     cached = load_cache(symbol)
#     if not cached.empty:
#         return cached

#     end = dt.datetime.now()
#     start = end - dt.timedelta(days=years*365)
#     parts = []
#     cur = start

#     while cur < end:
#         nxt = min(cur + dt.timedelta(days=30), end)
#         df = fetch_month_data(symbol, cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d"))
#         if not df.empty:
#             parts.append(df)
#         cur = nxt + dt.timedelta(days=1)
#         time.sleep(0.1)

#     if parts:
#         out = pd.concat(parts).sort_index()
#         out = out[~out.index.duplicated()]
#         save_cache(symbol, out)
#         return out

#     return pd.DataFrame()

# # =====================================================
# # SR CALCULATION
# # =====================================================
# def calculate_sr_levels(df):
#     high = df["high"].max()
#     low = df["low"].min()
#     pct = (high - low) / high
#     avg = (high + low) / 2

#     supports = [high * (1 - pct)**i for i in range(6,0,-1)]
#     resist = [high * (1 + pct)**i for i in range(1,7)]

#     sr = {}
#     for i,v in enumerate(supports,1): sr[f"L{i}"] = round(v,2)
#     for i,v in enumerate(resist,1):   sr[f"P{i}"] = round(v,2)

#     sr["Average"] = round(avg,2)
#     sr["High (Ref)"] = round(high,2)
#     return sr

# # =====================================================
# # WEEKLY BACKTEST LOGIC
# # =====================================================

# # def backtest_weekly(df, sr, march_close):
# #     wk = df.resample("W").agg({
# #         "open":"first","high":"max","low":"min","close":"last","volume":"sum"
# #     }).dropna()

# #     ul = min([v for k,v in sr.items() if k.startswith("P") and v > march_close], default=None)
# #     ll = max([v for k,v in sr.items() if k.startswith("L") and v < march_close], default=None)

# #     if not ul or not ll:
# #         return pd.DataFrame(), wk

# #     trades = []
# #     i = 0
# #     while i+4 < len(wk):
# #         base = wk.iloc[i]
# #         if base["close"] > ll:
# #             entry = wk.iloc[i+4]
# #             exit_price = None
# #             for j in range(i+4, min(i+8,len(wk))):
# #                 if wk.iloc[j]["high"] >= ul:
# #                     exit_price = ul
# #                     exit_date = wk.index[j]
# #                     break
# #             if not exit_price:
# #                 exit_price = wk.iloc[i+6]["close"]
# #                 exit_date = wk.index[i+6]

# #             pnl = round((exit_price-entry["open"])/entry["open"]*100,2)

# #             trades.append({
# #                 "entry_date": wk.index[i+4],
# #                 "entry_price": entry["open"],
# #                 "exit_date": exit_date,
# #                 "exit_price": exit_price,
# #                 "pnl_pct": pnl,
# #                 "ul": ul,
# #                 "ll": ll,
# #                 "base_date": wk.index[i]
# #             })
# #             i += 7
# #         else:
# #             i += 1

# #     return pd.DataFrame(trades), wk


# def backtest_weekly(df, sr, march_close):

#     wk = df.resample("W").agg({
#         "open": "first",
#         "high": "max",
#         "low": "min",
#         "close": "last",
#         "volume": "sum"
#     }).dropna()

#     ul_levels = [v for k, v in sr.items() if k.startswith("P") and v > march_close]
#     ll_levels = [v for k, v in sr.items() if k.startswith("L") and v < march_close]

#     if not ul_levels or not ll_levels:
#         return pd.DataFrame(), wk

#     ul = min(ul_levels)
#     ll = max(ll_levels)

#     trades = []
#     i = 0
#     n = len(wk)

#     while i + 4 < n:

#         base = wk.iloc[i]

#         if base["close"] > ll:

#             entry_idx = i + 4
#             entry = wk.iloc[entry_idx]
#             entry_price = entry["open"]
#             entry_date = wk.index[entry_idx]

#             exit_price = None
#             exit_date = None

#             # 🔒 SAFE EXIT SEARCH (bounded)
#             for j in range(entry_idx, min(entry_idx + 4, n)):
#                 if wk.iloc[j]["high"] >= ul:
#                     exit_price = ul
#                     exit_date = wk.index[j]
#                     break

#             # 🔒 FALLBACK EXIT (LAST AVAILABLE CANDLE)
#             if exit_price is None:
#                 fallback_idx = min(entry_idx + 2, n - 1)
#                 exit_price = wk.iloc[fallback_idx]["close"]
#                 exit_date = wk.index[fallback_idx]

#             pnl = round((exit_price - entry_price) / entry_price * 100, 2)

#             trades.append({
#                 "entry_date": entry_date,
#                 "entry_price": round(entry_price, 2),
#                 "exit_date": exit_date,
#                 "exit_price": round(exit_price, 2),
#                 "pnl_pct": pnl,
#                 "ul": round(ul, 2),
#                 "ll": round(ll, 2),
#                 "base_date": wk.index[i]
#             })

#             i = fallback_idx + 1

#         else:
#             i += 1

#     return pd.DataFrame(trades), wk



# # =====================================================
# # CHART
# # =====================================================
# def plot_chart(df, sr, title):
#     fig = go.Figure()
#     fig.add_candlestick(
#         x=df.index,
#         open=df.open,
#         high=df.high,
#         low=df.low,
#         close=df.close,
#         name="Price"
#     )

#     for k,v in sr.items():
#         fig.add_hline(y=v, line_dash="dot")

#     fig.update_layout(
#         title=title,
#         height=700,
#         dragmode="pan",
#         xaxis_rangeslider_visible=True
#     )
#     return fig

# # =====================================================
# # SYMBOL LIST
# # =====================================================
# # @st.cache_data(ttl=86400)
# # def get_nifty500_symbols():
# #     url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
# #     s = requests.Session()
# #     s.get("https://www.nseindia.com", timeout=5)
# #     r = s.get(url, timeout=10)
# #     df = pd.read_csv(StringIO(r.text))
# #     return sorted(df["Symbol"].dropna().unique())

# @st.cache_data(ttl=86400)
# def get_nifty500_symbols():

#     url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
#         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#         "Accept-Language": "en-US,en;q=0.9",
#         "Connection": "keep-alive",
#         "Referer": "https://www.nseindia.com/"
#     }

#     session = requests.Session()
#     session.headers.update(headers)

#     try:
#         # Step 1: Warm-up request (important)
#         session.get(
#             "https://www.nseindia.com",
#             timeout=15
#         )

#         time.sleep(1)

#         # Step 2: Actual CSV request
#         response = session.get(
#             url,
#             timeout=20
#         )

#         response.raise_for_status()

#         df = pd.read_csv(StringIO(response.text))
#         symbols = sorted(df["Symbol"].dropna().unique().tolist())
#         return symbols

#     except Exception as e:
#         st.warning("⚠ NSE not responding. Using fallback symbol list.")

#         # 🔒 SAFE FALLBACK (app will NEVER crash)
#         return [
#             "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
#             "SBIN", "LT", "ITC", "AXISBANK", "BAJFINANCE",
#             "HINDUNILVR", "KOTAKBANK", "MARUTI", "SUNPHARMA"
#         ]



# # =====================================================
# # UI INPUTS
# # =====================================================
# base_year = st.selectbox("Base FY", ["2020-2021","2021-2022","2022-2023","2023-2024","2024-2025"])
# march_year = st.selectbox("March Close Year", [2023,2024,2025], index=1)

# # =====================================================
# # SCAN ALL STOCKS
# # =====================================================
# if st.button("SCAN ALL STOCKS"):
#     st.session_state.trade_stocks.clear()
#     progress = st.progress(0)
#     symbols = get_nifty500_symbols()

#     for i,sym in enumerate(symbols):
#         symbol = f"NSE:{sym}-EQ"
#         print(symbol)
#         df = fetch_5yr_data(symbol)
#         print(df)
#         if df.empty:
#             continue

#         fy = df.loc[
#             (df.index >= dt.datetime(int(base_year[:4]),4,1)) &
#             (df.index <= dt.datetime(int(base_year[5:]),3,31))
#         ]
#         if fy.empty:
#             continue

#         sr = calculate_sr_levels(fy)
#         march_close = df.loc[:dt.datetime(march_year,3,31)]["close"].iloc[-1]

#         bt_df = df[df.index > dt.datetime(march_year,3,31)]
#         trades, wk = backtest_weekly(bt_df, sr, march_close)

#         if not trades.empty:
#             st.session_state.trade_stocks[sym] = {
#                 "trades": trades,
#                 "df": wk,
#                 "sr": sr
#             }

#         progress.progress((i+1)/len(symbols))

#     st.session_state.scan_done = True
#     st.success("Scan Completed")

# # =====================================================
# # SIDEBAR SELECTION
# # =====================================================
# if st.session_state.scan_done and st.session_state.trade_stocks:
#     selected = st.sidebar.selectbox(
#         "Stocks with Trades",
#         sorted(st.session_state.trade_stocks.keys())
#     )

#     data = st.session_state.trade_stocks[selected]
#     st.subheader(f"{selected} Trades")
#     st.dataframe(data["trades"], use_container_width=True)

#     fig = plot_chart(data["df"], data["sr"], f"{selected} Weekly Chart")
#     st.plotly_chart(fig, use_container_width=True)





################################ loop updated code start here #############################################################



# # streamlit run weekly_LL.py

# import streamlit as st
# import pandas as pd
# import datetime as dt
# from fyers_apiv3 import fyersModel
# import time
# import requests
# from io import StringIO
# import warnings
# import os
# import plotly.graph_objects as go
# from concurrent.futures import ThreadPoolExecutor, as_completed
# import threading

# warnings.filterwarnings("ignore")

# # =====================================================
# # STREAMLIT CONFIG
# # =====================================================
# st.set_page_config(page_title="Weekly SR Scanner", layout="wide")
# st.title("Weekly S/R BASE → BUY SCANNER")

# # =====================================================
# # SESSION STATE
# # =====================================================
# if "scan_done" not in st.session_state:
#     st.session_state.scan_done = False

# if "trade_stocks" not in st.session_state:
#     st.session_state.trade_stocks = {}

# if "scan_log" not in st.session_state:
#     st.session_state.scan_log = []

# lock = threading.Lock()

# # =====================================================
# # FYERS LOGIN
# # =====================================================
# with open("access.txt", "r") as a:
#     access_token = a.read().strip()

# client_id = "5YKT940X4B-100"
# fyers = fyersModel.FyersModel(
#     client_id=client_id,
#     token=access_token,
#     log_path=""
# )

# # =====================================================
# # CACHE
# # =====================================================
# CACHE_DIR = "data_cache"
# os.makedirs(CACHE_DIR, exist_ok=True)

# def _sanitize_symbol(symbol):
#     return symbol.replace(":", "_").replace("-", "_")

# def _cache_path(symbol):
#     return os.path.join(CACHE_DIR, f"{_sanitize_symbol(symbol)}.parquet")

# def load_cache(symbol):
#     if os.path.exists(_cache_path(symbol)):
#         return pd.read_parquet(_cache_path(symbol))
#     return pd.DataFrame()

# def save_cache(symbol, df):
#     if not df.empty:
#         df.to_parquet(_cache_path(symbol))

# # =====================================================
# # DATA FETCH
# # =====================================================
# def fetch_month_data(symbol, start, end):
#     data = fyers.history({
#         "symbol": symbol,
#         "resolution": "1D",
#         "date_format": "1",
#         "range_from": start,
#         "range_to": end,
#         "cont_flag": "1"
#     })

#     if data.get("s") == "ok":
#         df = pd.DataFrame(
#             data["candles"],
#             columns=["date", "open", "high", "low", "close", "volume"]
#         )
#         df["date"] = pd.to_datetime(df["date"], unit="s")
#         df.set_index("date", inplace=True)
#         return df

#     return pd.DataFrame()

# def fetch_5yr_data(symbol, years=6):
#     cached = load_cache(symbol)
#     if not cached.empty:
#         return cached

#     end = dt.datetime.now()
#     start = end - dt.timedelta(days=years * 365)
#     parts = []
#     cur = start

#     while cur < end:
#         nxt = min(cur + dt.timedelta(days=30), end)
#         df = fetch_month_data(
#             symbol,
#             cur.strftime("%Y-%m-%d"),
#             nxt.strftime("%Y-%m-%d")
#         )
#         if not df.empty:
#             parts.append(df)
#         cur = nxt + dt.timedelta(days=1)
#         time.sleep(0.12)

#     if parts:
#         out = pd.concat(parts).sort_index()
#         out = out[~out.index.duplicated()]
#         save_cache(symbol, out)
#         return out

#     return pd.DataFrame()

# # =====================================================
# # SR CALCULATION
# # =====================================================
# def calculate_sr_levels(df):
#     high = df["high"].max()
#     low = df["low"].min()
#     avg = (high + low) / 2
#     pct = (high - low) / high

#     supports = [high * (1 - pct) ** i for i in range(6, 0, -1)]
#     resist = [high * (1 + pct) ** i for i in range(1, 7)]

#     sr = {}
#     for i, v in enumerate(supports, 1):
#         sr[f"L{i}"] = round(v, 2)
#     for i, v in enumerate(resist, 1):
#         sr[f"P{i}"] = round(v, 2)

#     sr["Average"] = round(avg, 2)
#     sr["High (Ref)"] = round(high, 2)
#     return sr

# # =====================================================
# # WEEKLY BACKTEST (UNCHANGED LOGIC)
# # =====================================================
# def backtest_weekly(df, sr, march_close):

#     wk = df.resample("W").agg({
#         "open": "first",
#         "high": "max",
#         "low": "min",
#         "close": "last",
#         "volume": "sum"
#     }).dropna()

#     ul_levels = [v for k, v in sr.items() if k.startswith("P") and v > march_close]
#     ll_levels = [v for k, v in sr.items() if k.startswith("L") and v < march_close]

#     if not ul_levels or not ll_levels:
#         return pd.DataFrame(), wk

#     ul = min(ul_levels)
#     ll = max(ll_levels)

#     trades = []
#     i = 0
#     n = len(wk)

#     while i + 4 < n:
#         base = wk.iloc[i]

#         if base["close"] > ll:

#             entry_idx = i + 4
#             entry = wk.iloc[entry_idx]
#             entry_price = entry["open"]
#             entry_date = wk.index[entry_idx]

#             exit_price = None
#             exit_date = None
#             exit_idx = None

#             for j in range(entry_idx, min(entry_idx + 4, n)):
#                 if wk.iloc[j]["high"] >= ul:
#                     exit_price = ul
#                     exit_date = wk.index[j]
#                     exit_idx = j
#                     break

#             if exit_price is None:
#                 exit_idx = min(entry_idx + 2, n - 1)
#                 exit_price = wk.iloc[exit_idx]["close"]
#                 exit_date = wk.index[exit_idx]

#             pnl = round((exit_price - entry_price) / entry_price * 100, 2)

#             trades.append({
#                 "entry_date": entry_date,
#                 "entry_price": round(entry_price, 2),
#                 "exit_date": exit_date,
#                 "exit_price": round(exit_price, 2),
#                 "pnl_pct": pnl,
#                 "ul": round(ul, 2),
#                 "ll": round(ll, 2),
#                 "base_date": wk.index[i]
#             })

#             i = exit_idx + 1
#         else:
#             i += 1

#     return pd.DataFrame(trades), wk

# # =====================================================
# # CHART
# # =====================================================
# def plot_chart(df, sr, title):
#     fig = go.Figure()

#     fig.add_candlestick(
#         x=df.index,
#         open=df.open,
#         high=df.high,
#         low=df.low,
#         close=df.close,
#         name="Price"
#     )

#     for k, v in sr.items():
#         color = "green" if k.startswith("L") else "red"
#         fig.add_hline(y=v, line_dash="dot", line_color=color, opacity=0.6)

#     fig.update_layout(
#         title=title,
#         height=750,
#         dragmode="pan",
#         xaxis_rangeslider_visible=True,
#         template="plotly_dark"
#     )
#     return fig

# # =====================================================
# # SYMBOL LIST
# # =====================================================
# @st.cache_data(ttl=86400)
# def get_nifty500_symbols():
#     url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
#     headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
#     s = requests.Session()
#     s.headers.update(headers)

#     try:
#         s.get("https://www.nseindia.com", timeout=10)
#         time.sleep(1)
#         r = s.get(url, timeout=15)
#         df = pd.read_csv(StringIO(r.text))
#         return sorted(df["Symbol"].dropna().unique().tolist())
#     except Exception:
#         return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]

# # =====================================================
# # UI
# # =====================================================
# base_year = st.selectbox(
#     "Base FY",
#     ["2020-2021", "2021-2022", "2022-2023", "2023-2024", "2024-2025"]
# )

# march_year = st.selectbox("March Close Year", [2023, 2024, 2025], index=1)

# # =====================================================
# # PARALLEL SCAN FUNCTION
# # =====================================================
# def process_symbol(sym):
#     try:
#         symbol = f"NSE:{sym}-EQ"
#         df = fetch_5yr_data(symbol)
#         print(symbol)
#         print(df)

#         if df.empty or len(df) < 300:
#             return sym, None, f"{sym}: No data"

#         fy = df.loc[
#             (df.index >= dt.datetime(int(base_year[:4]), 4, 1)) &
#             (df.index <= dt.datetime(int(base_year[5:]), 3, 31))
#         ]

#         if fy.empty:
#             return sym, None, f"{sym}: FY missing"

#         march_df = df[df.index <= dt.datetime(march_year, 3, 31)]
#         if march_df.empty:
#             return sym, None, f"{sym}: March close missing"

#         sr = calculate_sr_levels(fy)
#         march_close = march_df["close"].iloc[-1]

#         bt_df = df[df.index > dt.datetime(march_year, 3, 31)]
#         trades, wk = backtest_weekly(bt_df, sr, march_close)

#         return sym, {"trades": trades, "df": wk, "sr": sr}, None

#     except Exception as e:
#         return sym, None, f"{sym}: {e}"

# # =====================================================
# # SCAN BUTTON (CONCURRENT)
# # =====================================================
# if st.button("SCAN ALL STOCKS"):

#     st.session_state.trade_stocks.clear()
#     st.session_state.scan_log.clear()

#     symbols = get_nifty500_symbols()
#     print(f"Scanning {len(symbols)} symbols...")
#     progress = st.progress(0)

#     with ThreadPoolExecutor(max_workers=8) as executor:
#         futures = [executor.submit(process_symbol, sym) for sym in symbols]

#         for i, f in enumerate(as_completed(futures)):
#             sym, data, log = f.result()

#             with lock:
#                 if data:
#                     st.session_state.trade_stocks[sym] = data
#                 if log:
#                     st.session_state.scan_log.append(log)

#             progress.progress((i + 1) / len(symbols))

#     st.session_state.scan_done = True
#     st.success("Scan Completed")

# # =====================================================
# # RESULTS
# # =====================================================
# if st.session_state.scan_done and st.session_state.trade_stocks:

#     selected = st.sidebar.selectbox(
#         "Stocks",
#         sorted(st.session_state.trade_stocks.keys())
#     )

#     data = st.session_state.trade_stocks[selected]

#     st.subheader(f"{selected} Trades")
#     st.dataframe(data["trades"], use_container_width=True)

#     fig = plot_chart(data["df"], data["sr"], f"{selected} Weekly Chart")
#     st.plotly_chart(fig, use_container_width=True)

#     with st.expander("Scan Log"):
#         st.write(st.session_state.scan_log)




###############################################################################################################


# # streamlit run weekly_LL.py

# import streamlit as st
# import pandas as pd
# import datetime as dt
# from fyers_apiv3 import fyersModel
# import time
# import requests
# from io import StringIO
# import warnings
# import os
# import plotly.graph_objects as go
# from concurrent.futures import ThreadPoolExecutor, as_completed
# import threading

# warnings.filterwarnings("ignore")

# # =====================================================
# # STREAMLIT CONFIG
# # =====================================================
# st.set_page_config(page_title="Weekly SR Scanner", layout="wide")
# st.title("Weekly S/R BASE → BUY SCANNER")

# # =====================================================
# # SESSION STATE
# # =====================================================
# if "scan_done" not in st.session_state:
#     st.session_state.scan_done = False
# if "trade_stocks" not in st.session_state:
#     st.session_state.trade_stocks = {}
# if "scan_log" not in st.session_state:
#     st.session_state.scan_log = []

# lock = threading.Lock()

# # =====================================================
# # FYERS LOGIN
# # =====================================================
# with open("access.txt", "r") as a:
#     access_token = a.read().strip()

# fyers = fyersModel.FyersModel(
#     client_id="5YKT940X4B-100",
#     token=access_token,
#     log_path=""
# )

# # =====================================================
# # CACHE
# # =====================================================
# CACHE_DIR = "data_cache"
# os.makedirs(CACHE_DIR, exist_ok=True)

# def _cache_path(sym):
#     return os.path.join(CACHE_DIR, sym.replace(":","_").replace("-","_") + ".parquet")

# def load_cache(sym):
#     if os.path.exists(_cache_path(sym)):
#         return pd.read_parquet(_cache_path(sym))
#     return pd.DataFrame()

# def save_cache(sym, df):
#     if not df.empty:
#         df.to_parquet(_cache_path(sym))

# # =====================================================
# # DATA FETCH
# # =====================================================
# def fetch_month_data(symbol, start, end):
#     data = fyers.history({
#         "symbol": symbol,
#         "resolution": "1D",
#         "date_format": "1",
#         "range_from": start,
#         "range_to": end,
#         "cont_flag": "1"
#     })
#     if data.get("s") == "ok":
#         df = pd.DataFrame(
#             data["candles"],
#             columns=["date","open","high","low","close","volume"]
#         )
#         df["date"] = pd.to_datetime(df["date"], unit="s")
#         df.set_index("date", inplace=True)
#         return df
#     return pd.DataFrame()

# def fetch_5yr_data(symbol, years=6):
#     cached = load_cache(symbol)
#     if not cached.empty:
#         return cached

#     end = dt.datetime.now()
#     start = end - dt.timedelta(days=years*365)
#     cur = start
#     parts = []

#     while cur < end:
#         nxt = min(cur + dt.timedelta(days=30), end)
#         df = fetch_month_data(symbol, cur.strftime("%Y-%m-%d"), nxt.strftime("%Y-%m-%d"))
#         if not df.empty:
#             parts.append(df)
#         cur = nxt + dt.timedelta(days=1)
#         time.sleep(0.12)

#     if parts:
#         out = pd.concat(parts).sort_index()
#         out = out[~out.index.duplicated()]
#         save_cache(symbol, out)
#         return out
#     return pd.DataFrame()

# # =====================================================
# # SR LEVELS
# # =====================================================
# def calculate_sr_levels(df):
#     high = df["high"].max()
#     low = df["low"].min()
#     avg = (high + low) / 2
#     pct = (high - low) / high

#     sr = {}
#     for i in range(6,0,-1):
#         sr[f"L{i}"] = round(high * (1-pct)**i, 2)
#     for i in range(1,7):
#         sr[f"P{i}"] = round(high * (1+pct)**i, 2)

#     sr["Average"] = round(avg,2)
#     sr["High (Ref)"] = round(high,2)
#     return sr

# # =====================================================
# # WEEKLY BUY LOGIC (UNCHANGED)
# # =====================================================
# def find_weekly_buy_trades(df_daily, sr_levels, march_close_price):

#     df_weekly = df_daily.resample('W').agg({
#         'open':'first','high':'max','low':'min','close':'last','volume':'sum'
#     }).dropna()
#     print(df_weekly)

#     ul_pool = [float(sr_levels.get(f"P{i}")) for i in range(1,7)] + \
#               [float(sr_levels["Average"]), float(sr_levels["High (Ref)"])]

#     ll_pool = [float(sr_levels.get(f"L{i}")) for i in range(1,7)]

#     ul_pool = [x for x in ul_pool if x > march_close_price]
#     ll_pool = [x for x in ll_pool if x < march_close_price]

#     if not ul_pool or not ll_pool:
#         return pd.DataFrame(), df_weekly

#     nearest_ul = min(ul_pool, key=lambda x: abs(x - march_close_price))
#     nearest_ll = min(ll_pool, key=lambda x: abs(x - march_close_price))

#     weeks = df_weekly.index
#     n = len(df_weekly)
#     i = 0
#     trades = []
#     print(trades)

#     while i < n:
#         if df_weekly.iloc[i]['close'] <= nearest_ll:
#             i += 1
#             continue

#         base_low = df_weekly.iloc[i]['low']
#         if i+3 >= n: break

#         fail = False
#         for k in range(i+1, i+4):
#             row = df_weekly.iloc[k]
#             if row['close'] > nearest_ul or row['close'] < nearest_ll or row['low'] <= base_low:
#                 fail = True
#                 break

#         if fail:
#             i = k+1
#             continue

#         entry_idx = i+4
#         if entry_idx >= n: break

#         entry_price = df_weekly.iloc[entry_idx]['open']
#         entry_date  = weeks[entry_idx]

#         exit_price = None
#         for k in range(entry_idx, min(entry_idx+4, n)):
#             if df_weekly.iloc[k]['high'] >= nearest_ul:
#                 exit_price = nearest_ul
#                 exit_date  = weeks[k]
#                 exit_idx   = k
#                 break

#         if exit_price is None:
#             exit_idx   = min(entry_idx+5, n-1)
#             exit_price = df_weekly.iloc[exit_idx]['close']
#             exit_date  = weeks[exit_idx]

#         pnl = round((exit_price-entry_price)/entry_price*100,2)

#         trades.append({
#             "entry_date": entry_date,
#             "entry_price": round(entry_price,2),
#             "exit_date": exit_date,
#             "exit_price": round(exit_price,2),
#             "pnl_pct": pnl,
#             "ul": round(nearest_ul,2),
#             "ll": round(nearest_ll,2),
#             "base_date": weeks[i]
#         })

#         i = exit_idx + 1

#     return pd.DataFrame(trades), df_weekly

# # =====================================================
# # PLOTTING FUNCTION (UNCHANGED)
# # =====================================================
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

# # =====================================================
# # SYMBOL LIST
# # =====================================================

# @st.cache_data(ttl=86400)
# def get_nifty500_symbols():

#     url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
#         "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
#         "Accept-Language": "en-US,en;q=0.9",
#         "Connection": "keep-alive",
#         "Referer": "https://www.nseindia.com/"
#     }

#     session = requests.Session()
#     session.headers.update(headers)

#     try:
#         # Step 1: Warm-up request (important)
#         session.get(
#             "https://www.nseindia.com",
#             timeout=15
#         )

#         time.sleep(1)

#         # Step 2: Actual CSV request
#         response = session.get(
#             url,
#             timeout=20
#         )

#         response.raise_for_status()

#         df = pd.read_csv(StringIO(response.text))
#         symbols = sorted(df["Symbol"].dropna().unique().tolist())
#         return symbols

#     except Exception as e:
#         st.warning("⚠ NSE not responding. Using fallback symbol list.")

#         # 🔒 SAFE FALLBACK (app will NEVER crash)
#         return [
#             "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
#             "SBIN", "LT", "ITC", "AXISBANK", "BAJFINANCE",
#             "HINDUNILVR", "KOTAKBANK", "MARUTI", "SUNPHARMA"
#         ]





# # =====================================================
# # UI
# # =====================================================
# base_year = st.selectbox("Base FY",["2020-2021","2021-2022","2022-2023","2023-2024","2024-2025"])
# march_year = st.selectbox("March Close Year",[2023,2024,2025],index=1)

# # =====================================================
# # SCAN
# # =====================================================
# def process_symbol(sym):
#     try:
#         symbol=f"NSE:{sym}-EQ"
#         df=fetch_5yr_data(symbol)
#         print(f"Processed: {symbol}")
#         print(df)
#         if df.empty: return sym,None,"No data"

#         fy=df.loc[
#             (df.index>=dt.datetime(int(base_year[:4]),4,1)) &
#             (df.index<=dt.datetime(int(base_year[5:]),3,31))
#         ]
#         if fy.empty: return sym,None,"FY missing"

#         sr=calculate_sr_levels(fy)
#         march_close=df.loc[df.index<=dt.datetime(march_year,3,31),"close"].iloc[-1]

#         bt_df=df[df.index>dt.datetime(march_year,3,31)]
#         trades,wk=find_weekly_buy_trades(bt_df,sr,march_close)

#         if trades.empty:
#             return sym,None,"No trades"

#         return sym,{"trades":trades,"df":wk,"sr":sr},None
#     except Exception as e:
#         return sym,None,str(e)

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

# # =====================================================
# # RESULTS
# # =====================================================
# if st.session_state.scan_done and st.session_state.trade_stocks:
#     selected=st.sidebar.selectbox("Stocks",sorted(st.session_state.trade_stocks.keys()))
#     data=st.session_state.trade_stocks[selected]
#     st.dataframe(data["trades"],use_container_width=True)
#     st.plotly_chart(plot_chart(data["df"],data["sr"],f"{selected} Weekly Chart"),use_container_width=True)



