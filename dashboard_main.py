# streamlit run dashboard_main.py



import streamlit as st
import pandas as pd
import datetime as dt
from fyers_apiv3 import fyersModel
import plotly.graph_objects as go
import time
import requests
from io import StringIO
import concurrent.futures

# ==============================
# Load Nifty 500 Symbols
# ==============================
@st.cache_data(ttl=86400)
def get_nifty500_symbols():
    url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.nseindia.com/",
    }
    s = requests.Session()
    s.get("https://www.nseindia.com", headers=headers)
    r = s.get(url, headers=headers)
    df = pd.read_csv(StringIO(r.text))
    stock_list = df['Symbol'].dropna().unique().tolist()
    stock_list.sort()
    return stock_list


# ==============================
# Fyers API Setup
# ==============================
with open("access.txt", "r") as a:
    access_token = a.read().strip()

client_id = "5YKT940X4B-100"
fyers = fyersModel.FyersModel(client_id=client_id, token=access_token)


# ==============================
# Utility Functions
# ==============================
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
        if data["s"] == "ok":
            df = pd.DataFrame(data["candles"], columns=["date", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["date"], unit="s")
            df.set_index("date", inplace=True)
            return df
        else:
            return pd.DataFrame()
    except:
        return pd.DataFrame()


def fetch_5yr_data_monthwise(symbol):
    end_date = dt.datetime.now()
    start_date = end_date - dt.timedelta(days=5 * 365)
    all_data = pd.DataFrame()

    current_date = start_date
    while current_date < end_date:
        next_date = current_date + dt.timedelta(days=30)
        df = fetch_month_data(symbol, current_date.strftime("%Y-%m-%d"), next_date.strftime("%Y-%m-%d"))
        if not df.empty:
            all_data = pd.concat([all_data, df])
        current_date = next_date
        time.sleep(0.2)
    return all_data


def resample_monthly(df):
    df_monthly = df.resample('M').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
    df_monthly.dropna(inplace=True)
    return df_monthly


# Renamed support levels correctly
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


def calculate_fy_summary(df):
    fy_data = []
    current_year = dt.datetime.now().year
    for fy in range(current_year - 4, current_year + 1):
        start_date = dt.datetime(fy, 4, 1)
        end_date = dt.datetime(fy + 1, 3, 31)
        fy_df = df[(df.index >= start_date) & (df.index <= end_date)]
        if not fy_df.empty:
            low = round(fy_df['low'].min(), 2)
            high = round(fy_df['high'].max(), 2)
            percent_change = (high - low) / high if high else 0
            sr_levels = calculate_sr_levels(fy_df)
            row = {
                "FY": f"{fy}-{fy+1}",
                "High": high,
                "Low": low,
                "%": f"{round(percent_change * 100, 2)}%",
                **{f"L{i}": sr_levels.get(f"L{i}") for i in range(1, 7)},
                "Average": sr_levels.get("Average"),
                "High (Ref)": high,
                **{f"P{i}": sr_levels.get(f"P{i}") for i in range(1, 7)}
            }
            fy_data.append(row)
    return pd.DataFrame(fy_data)


def get_cmp(symbol):
    try:
        data = fyers.quotes({"symbols": symbol})
        if data["s"] == "ok":
            return float(data["d"][0].get("v", {}).get("lp", 0))
    except:
        return None



# ==============================
# CHART PLOTTING FUNCTION
# # ==============================
# def plot_chart(df, sr_levels, title, show_volume=True):
#     fig = go.Figure()

#     fig.add_trace(go.Candlestick(
#         x=df.index, open=df["open"], high=df["high"],
#         low=df["low"], close=df["close"], name="Price"
#     ))

#     if show_volume:
#         fig.add_trace(go.Bar(
#             x=df.index, y=df["volume"], name="Volume", yaxis="y2", opacity=0.3
#         ))

#     # Corrected Label order for plotting (L1 highest support, L6 lowest)
#     for i in range(1, 7):
#         keyL = f"L{i}"
#         if keyL in sr_levels:
#             fig.add_hline(y=sr_levels[keyL], line_dash="dot", line_color="green",
#                           annotation_text=f"{keyL}: {sr_levels[keyL]}",
#                           annotation_position="top left")

#     for i in range(1, 7):
#         keyP = f"P{i}"
#         if keyP in sr_levels:
#             fig.add_hline(y=sr_levels[keyP], line_dash="dot", line_color="red",
#                           annotation_text=f"{keyP}: {sr_levels[keyP]}",
#                           annotation_position="bottom left")

#     fig.update_layout(
#         title=title, xaxis_title="Date", yaxis_title="Price",
#         template="plotly_dark", height=700, dragmode="pan",
#         plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
#         font=dict(color="white"), hovermode="x unified",
#         yaxis2=dict(overlaying='y', side='right', showgrid=False, title='Volume' if show_volume else None),
#         updatemenus=[dict(type="buttons", showactive=False,
#                           buttons=[dict(label="Reset Zoom", method="relayout",
#                                         args=[{"xaxis.autorange": True, "yaxis.autorange": True}])])]
#     )

#     fig.update_xaxes(showspikes=True, spikemode='across', spikecolor='white',
#                      spikesnap='cursor', rangeslider=dict(visible=True))
#     fig.update_yaxes(fixedrange=False, showspikes=True, spikemode='across', spikecolor='white')
#     return fig

# ==============================
# CHART PLOTTING FUNCTION WITH AVERAGE LINE
# ==============================
# def plot_chart(df, sr_levels, title, show_volume=True):
#     fig = go.Figure()

#     # Candlestick
#     fig.add_trace(go.Candlestick(
#         x=df.index, open=df["open"], high=df["high"],
#         low=df["low"], close=df["close"], name="Price"
#     ))

#     # Volume bars
#     if show_volume:
#         fig.add_trace(go.Bar(
#             x=df.index, y=df["volume"], name="Volume", yaxis="y2", opacity=0.3
#         ))

#     # Support levels (L1 highest, L6 lowest)
#     for i in range(1, 7):
#         keyL = f"L{i}"
#         if keyL in sr_levels:
#             fig.add_hline(y=sr_levels[keyL], line_dash="dot", line_color="green",
#                           annotation_text=f"{keyL}: {sr_levels[keyL]}",
#                           annotation_position="top left")

#     # Resistance levels (P1 highest, P6 lowest)
#     for i in range(1, 7):
#         keyP = f"P{i}"
#         if keyP in sr_levels:
#             fig.add_hline(y=sr_levels[keyP], line_dash="dot", line_color="red",
#                           annotation_text=f"{keyP}: {sr_levels[keyP]}",
#                           annotation_position="bottom left")

#     # Average line (mean of close prices)
#     avg_price = df["close"].mean()
#     fig.add_hline(y=avg_price, line_dash="dash", line_color="yellow",
#                   annotation_text=f"Avg: {avg_price:.2f}",
#                   annotation_position="top right")

#     # Layout settings
#     fig.update_layout(
#         title=title, xaxis_title="Date", yaxis_title="Price",
#         template="plotly_dark", height=700, dragmode="pan",
#         plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
#         font=dict(color="white"), hovermode="x unified",
#         yaxis2=dict(overlaying='y', side='right', showgrid=False, title='Volume' if show_volume else None),
#         updatemenus=[dict(type="buttons", showactive=False,
#                           buttons=[dict(label="Reset Zoom", method="relayout",
#                                         args=[{"xaxis.autorange": True, "yaxis.autorange": True}])])],
#     )

#     fig.update_xaxes(showspikes=True, spikemode='across', spikecolor='white',
#                      spikesnap='cursor', rangeslider=dict(visible=True))
#     fig.update_yaxes(fixedrange=False, showspikes=True, spikemode='across', spikecolor='white')
#     return fig

def plot_chart(df, sr_levels, title, show_volume=True):
    fig = go.Figure()

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="Price"
    ))

    # Volume bars
    if show_volume:
        fig.add_trace(go.Bar(
            x=df.index, y=df["volume"], name="Volume", yaxis="y2", opacity=0.3
        ))

    # Support levels (L1 highest, L6 lowest)
    for i in range(1, 7):
        keyL = f"L{i}"
        if keyL in sr_levels:
            fig.add_hline(y=sr_levels[keyL], line_dash="dot", line_color="green",
                          annotation_text=f"{keyL}: {sr_levels[keyL]}",
                          annotation_position="top left")

    # Resistance levels (P1 highest, P6 lowest)
    for i in range(1, 7):
        keyP = f"P{i}"
        if keyP in sr_levels:
            fig.add_hline(y=sr_levels[keyP], line_dash="dot", line_color="red",
                          annotation_text=f"{keyP}: {sr_levels[keyP]}",
                          annotation_position="bottom left")

    # Average line
    avg_price = df["close"].mean()
    fig.add_hline(y=avg_price, line_dash="dash", line_color="yellow",
                  annotation_text=f"Avg: {avg_price:.2f}",
                  annotation_position="top right")

    # Layout and style
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Price",
        template="plotly_dark",
        height=700,
        dragmode="pan",
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font=dict(color="white"),
        hovermode="x unified",
        yaxis2=dict(overlaying='y', side='right', showgrid=False,
                    title='Volume' if show_volume else None),
        updatemenus=[dict(type="buttons", showactive=False,
                          buttons=[dict(label="Reset Zoom", method="relayout",
                                        args=[{"xaxis.autorange": True, "yaxis.autorange": True}])])]
    )

    # Light gridlines (less distracting)
    fig.update_xaxes(showspikes=True, spikemode='across', spikecolor='white',
                     spikesnap='cursor', rangeslider=dict(visible=True),
                     showgrid=True, gridcolor="rgba(255,255,255,0.05)")
    fig.update_yaxes(fixedrange=False, showspikes=True, spikemode='across',
                     spikecolor='white', showgrid=True, gridcolor="rgba(255,255,255,0.05)")

    return fig


# ==============================
# Streamlit Tabs
# ==============================
st.set_page_config(page_title="📊 SR Dashboard + Scanner", layout="wide")
tab1, tab2 = st.tabs(["📊 Dashboard", "🔍 Scanner"])

# ==========================================================
# TAB 1 — Dashboard
# ==========================================================
with tab1:
    st.title("📊 Support & Resistance Dashboard")

    nifty500_symbols = get_nifty500_symbols()
    user_symbol = st.sidebar.selectbox(
        "🔍 Select Stock Symbol (Nifty 500):",
        nifty500_symbols,
        index=nifty500_symbols.index("SBIN") if "SBIN" in nifty500_symbols else 0
    )
    segment = st.sidebar.selectbox("Select Segment:", ["EQ", "FUT"], index=0)
    chart_type = st.sidebar.radio("Chart Type:", ["Daily", "Monthly"], horizontal=True)
    show_volume = st.sidebar.checkbox("Show Volume", True)
    symbol = f"NSE:{user_symbol}-{'EQ' if segment == 'EQ' else 'FUT'}"

    if "raw_data" not in st.session_state:
        st.session_state.raw_data = pd.DataFrame()

    if st.sidebar.button("📥 Fetch 5-Year Data"):
        with st.spinner(f"Fetching 5-year historical data for {user_symbol}..."):
            raw_data = fetch_5yr_data_monthwise(symbol)
            if not raw_data.empty:
                st.session_state.raw_data = raw_data
                st.success(f"✅ Data fetched successfully for {user_symbol}!")

    if not st.session_state.raw_data.empty:
        raw_data = st.session_state.raw_data
        data = resample_monthly(raw_data) if chart_type == "Monthly" else raw_data.copy()
        fy_summary = calculate_fy_summary(data)

        # ✅ Updated order (L6 lowest → L1 highest)
        cols_order = [
            "FY", "Low", "High", "%", 
            "L6", "L5", "L4", "L3", "L2", "L1", 
            "Average", "High (Ref)", 
            "P1", "P2", "P3", "P4", "P5", "P6"
        ]

        fy_summary = fy_summary[[c for c in cols_order if c in fy_summary.columns]]

        st.subheader(f"📈 Financial Year Summary for {user_symbol} ({segment})")
        st.dataframe(fy_summary, use_container_width=True)

        base_year = st.sidebar.selectbox(
            "Select Base Year for SR Levels",
            options=fy_summary["FY"].tolist(),
            index=len(fy_summary) - 1
        )
        selected_row = fy_summary[fy_summary["FY"] == base_year].iloc[0]

        year_start = dt.datetime(int(base_year.split('-')[0]), 4, 1)
        year_end = dt.datetime(int(base_year.split('-')[1]), 3, 31)
        year_df = data[(data.index >= year_start) & (data.index <= year_end)]
        sr_levels = calculate_sr_levels(year_df)

        st.subheader(f"📊 {chart_type} Candlestick Chart for {user_symbol} ({segment})")
        fig = plot_chart(data, sr_levels, f"{user_symbol} ({segment}) — Base Year {base_year}", show_volume)
        st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True})
    else:
        st.info("ℹ️ Please select a stock and click **📥 Fetch 5-Year Data** to start.")


# ==========================================================
# TAB 2 — Nifty 500 Scanner
# ==========================================================
with tab2:
    st.title("⚡ Fast Nifty 500 Support/Resistance Scanner")

    nifty500_symbols = get_nifty500_symbols()

    base_year = st.selectbox(
        "Select Financial Year for SR Levels",
        [f"{fy}-{fy+1}" for fy in range(dt.datetime.now().year - 4, dt.datetime.now().year + 1)],
        index=4
    )

    # ✅ Only labels updated; logic same
    condition = st.selectbox(
        "Select Condition:",
        [
            "Above P1 but below P2",
            "Above P2 but below P3",
            "Above Average but below P1",
            "Below L1 but above L2",
            "Below L2 but above L3"
        ]
    )

    @st.cache_data(ttl=86400)
    def get_sr_for_symbol(symbol_name, base_year):
        fy_start = int(base_year.split("-")[0])
        fy_end = int(base_year.split("-")[1])
        symbol = f"NSE:{symbol_name}-EQ"
        df = fetch_month_data(symbol, f"{fy_start}-04-01", f"{fy_end}-03-31")
        if df.empty:
            return None
        sr = calculate_sr_levels(df)
        return sr

    def check_condition(symbol_name, sr, cmp_price):
        if not sr or cmp_price is None:
            return False

        if condition == "Above P1 but below P2":
            return sr["P1"] < cmp_price < sr["P2"]
        elif condition == "Above P2 but below P3":
            return sr["P2"] < cmp_price < sr["P3"]
        elif condition == "Above Average but below P1":
            return sr["Average"] < cmp_price < sr["P1"]
        elif condition == "Below L1 but above L2":
            return sr["L1"] > cmp_price > sr["L2"]
        elif condition == "Below L2 but above L3":
            return sr["L2"] > cmp_price > sr["L3"]
        return False

    if st.button("🚀 Run Fast Scanner"):
        st.info("Running optimized multi-threaded scanner... Please wait 1–3 minutes.")
        progress = st.progress(0)
        results = []
        total = len(nifty500_symbols)

        all_symbols_str = ",".join([f"NSE:{s}-EQ" for s in nifty500_symbols])
        cmp_data = fyers.quotes({"symbols": all_symbols_str})
        cmp_map = {}
        if cmp_data.get("s") == "ok":
            for d in cmp_data["d"]:
                sym = d["n"].split(":")[1].split("-")[0]
                cmp_map[sym] = d.get("v", {}).get("lp", None)

        def process_stock(symbol_name):
            sr = get_sr_for_symbol(symbol_name, base_year)
            cmp_price = cmp_map.get(symbol_name)
            if sr and cmp_price is not None and check_condition(symbol_name, sr, cmp_price):
                return {
                    "Symbol": symbol_name,
                    "CMP": round(cmp_price, 2),
                    "FY": base_year,
                    **sr
                }
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(process_stock, s): s for s in nifty500_symbols}
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                res = future.result()
                if res:
                    results.append(res)
                progress.progress((i + 1) / total)

        if results:
            df_results = pd.DataFrame(results)
            st.success(f"✅ Found {len(df_results)} stocks matching '{condition}'")
            st.dataframe(df_results, use_container_width=True)
            csv = df_results.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", csv, f"scanner_results_{base_year}.csv", "text/csv")
        else:
            st.warning("No stocks matched your condition.")

