# # streamlit run dashboard_main.py


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
import yfinance as yf
from io import BytesIO

import warnings
warnings.filterwarnings("ignore", message=".*missing ScriptRunContext!.*")

import os

# Force-create log directory at runtime (works in cloud + local)
os.makedirs("log", exist_ok=True)



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



def plot_chart(df, sr_levels, title, show_volume=True):
    # Sidebar checkboxes for extra levels
    show_extra_supports = st.sidebar.checkbox("Show Extended Supports (L3–L6)", value=False)
    show_extra_resistances = st.sidebar.checkbox("Show Extended Resistances (P3–P6)", value=False)

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

    # ==== Support Levels ====
    # Always show L1 & L2
    for i in [1, 2]:
        keyL = f"L{i}"
        if keyL in sr_levels:
            fig.add_hline(y=sr_levels[keyL], line_dash="dot", line_color="green",
                          annotation_text=f"{keyL}: {sr_levels[keyL]}",
                          annotation_position="top left")

    # Optionally show L3–L6
    if show_extra_supports:
        for i in range(3, 7):
            keyL = f"L{i}"
            if keyL in sr_levels:
                fig.add_hline(y=sr_levels[keyL], line_dash="dot", line_color="lime",
                              annotation_text=f"{keyL}: {sr_levels[keyL]}",
                              annotation_position="top left")

    # ==== Resistance Levels ====
    # Always show P1 & P2
    for i in [1, 2]:
        keyP = f"P{i}"
        if keyP in sr_levels:
            fig.add_hline(y=sr_levels[keyP], line_dash="dot", line_color="red",
                          annotation_text=f"{keyP}: {sr_levels[keyP]}",
                          annotation_position="bottom left")

    # Optionally show P3–P6
    if show_extra_resistances:
        for i in range(3, 7):
            keyP = f"P{i}"
            if keyP in sr_levels:
                fig.add_hline(y=sr_levels[keyP], line_dash="dot", line_color="tomato",
                              annotation_text=f"{keyP}: {sr_levels[keyP]}",
                              annotation_position="bottom left")

    # Average line
    # avg_price = df["close"].mean()
    # fig.add_hline(y=avg_price, line_dash="dash", line_color="yellow",
    #               annotation_text=f"Avg: {avg_price:.2f}",
    #               annotation_position="top right")


        # Average line — use SR calculator's Average for the selected FY (fallback to close-mean)
    avg_price = None
    if isinstance(sr_levels, dict):
        avg_price = sr_levels.get("Average")
    # try convert to float if it's a string/None-like
    try:
        if avg_price is not None:
            avg_price = float(avg_price)
    except Exception:
        avg_price = None

    # Fallback: if sr_levels doesn't contain Average, use df close mean
    if avg_price is None or pd.isna(avg_price):
        avg_price = float(df["close"].mean())

    fig.add_hline(
        y=avg_price,
        line_dash="dash",
        line_color="yellow",
        annotation_text=f"Base FY Avg: {avg_price:.2f}",
        annotation_position="top right"
    )


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
                                        args=[{"xaxis.autorange": True, "yaxis.autorange": True}])])],
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
# st.set_page_config(page_title="📊 SR Dashboard + Scanner", layout="wide")
# tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "🔍 Scanner", 'SR Backtester'])
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Scanner", "SR Backtester", "FY Levels Export"])

st.set_page_config(page_title="SR Dashboard", layout="wide")


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


# # ==========================================================
# # TAB 2 — Nifty 500 Scanner
# # ==========================================================

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

        # if results:
        #     df_results = pd.DataFrame(results)
        #     st.success(f"✅ Found {len(df_results)} stocks matching '{condition}'")
        #     st.dataframe(df_results, use_container_width=True)
        #     csv = df_results.to_csv(index=False).encode('utf-8')
        #     st.download_button("📥 Download CSV", csv, f"scanner_results_{base_year}.csv", "text/csv")
        # else:
        #     st.warning("No stocks matched your condition.")

        if results:
            df_results = pd.DataFrame(results)
        
            # ✅ Reorder columns as per your desired format
            desired_order = [
                "Symbol", "FY", "%", "CMP",
                "L6", "L5", "L4", "L3", "L2", "L1",
                "Average", "P1", "P2", "P3", "P4", "P5", "P6"
            ]
            df_results = df_results[[c for c in desired_order if c in df_results.columns]]
        
            st.success(f"✅ Found {len(df_results)} stocks matching '{condition}'")
            st.dataframe(df_results, use_container_width=True)
        
            # CSV download
            csv = df_results.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV",
                csv,
                f"scanner_results_{base_year}.csv",
                "text/csv"
            )
        else:
            st.warning("No stocks matched your condition.")

# ==========================================================
# TAB 2 — Nifty 500 Scanner (Updated)
# ==========================================================
# with tab2:
#     st.title("Fast Nifty 500 Support/Resistance Scanner")

#     stock_symbols = get_nifty500_symbols()
#     total = len(stock_symbols)

#     selected_fy = st.selectbox(
#         "Select Financial Year:",
#         [f"{fy}-{fy+1}" for fy in range(dt.datetime.now().year - 6, dt.datetime.now().year)],
#         index=5
#     )

#     fy_start = f"{selected_fy.split('-')[0]}-04-01"
#     fy_end   = f"{selected_fy.split('-')[1]}-03-31"

#     condition = st.selectbox(
#         "Select Condition:",
#         [
#             "Above P1 but below P2",
#             "Above P2 but below P3",
#             "Above Average but below P1",
#             "Below L1 but above L2",
#             "Below L2 but above L3"
#         ]
#     )

#     evaluated_count = 0
#     skipped_count = 0
#     results = []
#     progress = st.progress(0)

#     if st.button("Run Scanner"):
#         for i, symbol in enumerate(stock_symbols):
#             evaluated_count += 1
#             sym = f"NSE:{symbol}-EQ"

#             df = fetch_month_data(sym, fy_start, fy_end)
#             cmp_price = get_cmp(sym)

#             if df.empty or cmp_price is None:
#                 skipped_count += 1
#                 progress.progress((i + 1) / total)
#                 continue

#             sr = calculate_sr_levels(df)

#             match = False
#             if condition == "Above P1 but below P2":
#                 match = sr["P1"] < cmp_price < sr["P2"]
#             elif condition == "Above P2 but below P3":
#                 match = sr["P2"] < cmp_price < sr["P3"]
#             elif condition == "Above Average but below P1":
#                 match = sr["Average"] < cmp_price < sr["P1"]
#             elif condition == "Below L1 but above L2":
#                 match = sr["L1"] > cmp_price > sr["L2"]
#             elif condition == "Below L2 but above L3":
#                 match = sr["L2"] > cmp_price > sr["L3"]

#             if match:
#                 results.append({
#                     "Symbol": symbol,
#                     "FY": selected_fy,
#                     "CMP": round(cmp_price, 2),
#                     **sr
#                 })

#             progress.progress((i + 1) / total)

#         # ===== Universe Audit Summary =====
#         st.markdown("---")
#         st.success(f"Total Symbols Attempted: {total}")
#         st.info(f"Total Symbols Evaluated for Condition: {evaluated_count}")
#         st.warning(f"Total Symbols Skipped (No history or CMP missing): {skipped_count}")
#         st.success(f"Total Symbols Matched Condition: {len(results)}")

#         if results:
#             df_results = pd.DataFrame(results)
#             final_order = [
#                 "Symbol","FY","L6","L5","L4","L3","L2","L1",
#                 "Average","High (Ref)","P1","P2","P3","P4","P5","P6",
#                 "% Change","CMP"
#             ]
#             df_results = df_results[[c for c in final_order if c in df_results.columns]]

#             st.dataframe(df_results, use_container_width=True)

#             csv = df_results.to_csv(index=False).encode("utf-8")
#             st.download_button(
#                 "Download CSV",
#                 data=csv,
#                 file_name=f"scanner_results_{selected_fy}.csv",
#                 mime="text/csv"
#             )
#         else:
#             st.error("No symbols matched the selected condition.")



with tab3:

    st.header("SR Backtester — fixed data fetching + positional rules (with markers)")

    import pandas as pd
    import datetime as dt
    import plotly.graph_objects as go
    import time
    import requests
    from io import StringIO
    import os
    from fyers_apiv3 import fyersModel
    import warnings
    warnings.filterwarnings("ignore")

    ##############################
    # READ FYERS ACCESS TOKEN
    ##############################
    with open("access.txt", "r") as a:
        access_token = a.read().strip()

    client_id = "5YKT940X4B-100"
    fyers = fyersModel.FyersModel(client_id=client_id, token=access_token)

    ##############################
    # CACHE DIR
    ##############################
    CACHE_DIR = "data_cache"
    os.makedirs(CACHE_DIR, exist_ok=True)

    ##############################
    # FETCH MONTH DATA
    ##############################
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
            if not data:
                return pd.DataFrame()
            if data.get("s") == "ok" and "candles" in data:
                df = pd.DataFrame(
                    data["candles"],
                    columns=["date", "open", "high", "low", "close", "volume"]
                )
                df["date"] = pd.to_datetime(df["date"], unit="s")
                df.set_index("date", inplace=True)
                return df
            return pd.DataFrame()
        except:
            return pd.DataFrame()

    ##############################
    # CACHE HELPERS
    ##############################
    def _sanitize_symbol(symbol: str) -> str:
        return symbol.replace(":", "_").replace("/", "_").replace(" ", "_")

    def _cache_path(symbol: str):
        name = _sanitize_symbol(symbol)
        return os.path.join(CACHE_DIR, f"{name}.parquet")

    def load_cache(symbol: str):
        path = _cache_path(symbol)
        if os.path.exists(path):
            try:
                df = pd.read_parquet(path)
                if not pd.api.types.is_datetime64_any_dtype(df.index):
                    df.index = pd.to_datetime(df.index)
                return df.sort_index()
            except:
                return pd.DataFrame()
        return pd.DataFrame()

    def save_cache(symbol: str, df: pd.DataFrame):
        if df is None or df.empty:
            return
        df.to_parquet(_cache_path(symbol))

    ##############################
    # FETCH DATA IN CHUNKS
    ##############################
    def fetch_5yr_data_monthwise(symbol, end_date=None, years=6, force_refresh=False):
        if end_date is None:
            end_date = dt.datetime.now()

        requested_start = end_date - dt.timedelta(days=years * 365)
        requested_end = end_date

        cached = pd.DataFrame()
        if not force_refresh:
            cached = load_cache(symbol)

        if not cached.empty:
            cache_min = cached.index.min()
            cache_max = cached.index.max()
            if cache_min <= requested_start and cache_max >= requested_end:
                return cached.loc[(cached.index >= requested_start) & (cached.index <= requested_end)]

        fetch_segments = []
        if cached.empty:
            fetch_segments.append((requested_start, requested_end))
        else:
            cache_min = cached.index.min()
            cache_max = cached.index.max()

            if requested_start < cache_min:
                fetch_segments.append((requested_start, cache_min - dt.timedelta(days=1)))
            if requested_end > cache_max:
                fetch_segments.append((cache_max + dt.timedelta(days=1), requested_end))

        fetched_parts = []
        for seg_start, seg_end in fetch_segments:
            current_date = seg_start
            while current_date < seg_end:
                next_date = min(current_date + dt.timedelta(days=30), seg_end)
                df_chunk = fetch_month_data(
                    symbol,
                    current_date.strftime("%Y-%m-%d"),
                    next_date.strftime("%Y-%m-%d")
                )
                if not df_chunk.empty:
                    fetched_parts.append(df_chunk)
                current_date = next_date + dt.timedelta(days=1)
                time.sleep(0.12)

        all_parts = []
        if not cached.empty:
            all_parts.append(cached)
        if fetched_parts:
            all_parts.extend(fetched_parts)

        if not all_parts:
            return pd.DataFrame()

        df_all = pd.concat(all_parts)
        df_all = df_all[~df_all.index.duplicated(keep='first')]
        df_all = df_all.sort_index()

        save_cache(symbol, df_all)

        return df_all.loc[(df_all.index >= requested_start) & (df_all.index <= requested_end)]

    ##############################
    # SR LEVEL ENGINE
    ##############################
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
        supports = list(reversed(supports))

        resistances = []
        P1 = high + (high * percent_change)
        resistances.append(P1)
        for i in range(1, 6):
            prev = resistances[i - 1]
            next_level = prev + (prev * percent_change)
            resistances.append(next_level)

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

 
        
    def find_base_candles_upper(df, level_value):
        trades = []
        n = len(df)
        dates = df.index
        i = 0

        while i < n:

            # ========================================================
            # RULE 1 — Do not allow base until FIRST breakout above UL
            # ========================================================
            breakout_seen = False
            for j in range(i):
                if df.iloc[j]['close'] > level_value or df.iloc[j]['open'] > level_value:
                    breakout_seen = True
                    break

            if not breakout_seen:
                i += 1
                continue

            # ========================================================
            # RULE 2 — base candle must open & remain ABOVE UL
            # open > UL and low > UL ensures no intraday dip below level
            # ========================================================
            if not (df.iloc[i]['open'] > level_value and df.iloc[i]['low'] > level_value):
                i += 1
                continue

            base1_idx = i
            base1_low = df.iloc[i]['low']

            # 5-candle protection
            if base1_idx + 5 >= n:
                break

            fail = False
            for k in range(base1_idx + 1, base1_idx + 6):

                # must stay above UL
                if df.iloc[k]['low'] <= level_value:
                    fail = True
                    break

                # must stay above base low
                if df.iloc[k]['low'] <= base1_low:
                    fail = True
                    break

            if fail:
                i = k + 1
                continue

            # 5-day high
            win = df.iloc[base1_idx + 1 : base1_idx + 6]
            five_high = win['high'].max()

            # ========================================================
            # RULE 3 — breakout candle MUST be clean GAP ABOVE UL
            # open > UL, low > UL, not wick-dip into UL zone
            # ========================================================
            breakout_idx = None
            for k in range(base1_idx + 6, n):
                if (df.iloc[k]['open'] > level_value and
                    df.iloc[k]['low'] > level_value and
                    df.iloc[k]['close'] > five_high):
                    breakout_idx = k
                    break

            if breakout_idx is None:
                i = base1_idx + 1
                continue

            # ========================================================
            # RULE 4 — retest must remain above UL and dip below five_high
            # ========================================================
            retest_idx = None
            for k in range(breakout_idx + 1, n):

                if df.iloc[k]['low'] <= level_value:
                    break

                if df.iloc[k]['low'] < five_high:
                    retest_idx = k
                    break

            if retest_idx is None:
                i = breakout_idx + 1
                continue

            # ========================================================
            # RULE 5 — second base ABOVE UL
            # ========================================================
            base2_idx = None
            base2_low = None
            for k in range(retest_idx + 1, n):

                if df.iloc[k]['low'] <= level_value:
                    break

                if df.iloc[k]['close'] > five_high:
                    base2_idx = k
                    base2_low = df.iloc[k]['low']
                    break

            if base2_idx is None:
                i = retest_idx + 1
                continue

            if base2_idx + 5 >= n:
                break

            fail2 = False
            for k in range(base2_idx + 1, base2_idx + 6):

                if df.iloc[k]['low'] <= level_value:
                    fail2 = True
                    break

                if df.iloc[k]['low'] <= base2_low:
                    fail2 = True
                    break

            if fail2:
                i = base2_idx + 1
                continue

            # ========================================================
            # RULE 6 — entry ABOVE UL
            # ========================================================
            entry_idx = base2_idx + 6
            if entry_idx >= n:
                break

            if df.iloc[entry_idx]['close'] <= level_value:
                i = entry_idx + 1
                continue

            entry_price = df.iloc[entry_idx]['close']

            trades.append({
                'entry_idx'       : entry_idx,
                'entry_date'      : dates[entry_idx],
                'entry_price'     : entry_price,
                'mode'            : 'A',
                'ul'              : level_value,

                'base1_idx'       : base1_idx,
                'five_high'       : five_high,
                'breakout_idx'    : breakout_idx,
                'retest_idx'      : retest_idx,
                'base2_idx'       : base2_idx,
            })

            i = entry_idx + 1

        return trades



    def find_base_candles_below(df, level_value):
        trades = []
        n = len(df)
        dates = df.index
        i = 0

        while i < n:

            # ========================================================
            # RULE 1 — Do not allow base formation BELOW UL
            # until UL has been crossed DOWN at least once.
            # ========================================================
            down_break_exists = False
            for j in range(i):
                # candle must have been ABOVE UL earlier
                if df.iloc[j]['close'] > level_value or df.iloc[j]['open'] > level_value:
                    # and now below UL later
                    for k in range(j+1, i+1):
                        if df.iloc[k]['close'] < level_value:
                            down_break_exists = True
                            break
                    if down_break_exists:
                        break

            if not down_break_exists:
                i += 1
                continue

            # ========================================================
            # RULE 2 — base2 candle must be fully below UL
            # ========================================================
            if not (df.iloc[i]['close'] < level_value and df.iloc[i]['high'] < level_value):
                i += 1
                continue

            base2_idx = i
            base2_low = df.iloc[i]['low']

            # ========================================================
            # RULE 3 — enforce 5-candle protection
            # ========================================================
            while True:

                if base2_idx + 5 >= n:
                    return trades

                failed = False
                rebase = False

                for k in range(base2_idx + 1, base2_idx + 6):
                    r = df.iloc[k]

                    # cannot touch UL again during base building
                    if r['high'] >= level_value:
                        failed = True
                        break

                    # cannot break lower low
                    if r['low'] <= base2_low:
                        base2_idx = k
                        base2_low = r['low']
                        rebase = True
                        break

                if failed:
                    i = k + 1
                    break

                if not rebase:
                    break

            # ========================================================
            # RULE 4 — after base, must make new lower low (retest)
            # ========================================================
            retest_idx = None
            for k in range(base2_idx + 6, n):

                # must remain below UL
                if df.iloc[k]['high'] >= level_value:
                    break

                if df.iloc[k]['low'] < base2_low:
                    retest_idx = k
                    break

            if retest_idx is None:
                i = base2_idx + 1
                continue

            base3_idx = retest_idx
            base3_low = df.iloc[retest_idx]['low']

            # ========================================================
            # RULE 5 — stability window for BASE3
            # ========================================================
            if base3_idx + 10 >= n:
                break

            ok10 = True
            for k in range(base3_idx + 1, base3_idx + 11):
                r = df.iloc[k]
                if r['low'] <= base3_low:
                    ok10 = False
                    break
                if r['high'] >= level_value:
                    ok10 = False
                    break

            if not ok10:
                i = base3_idx + 1
                continue

            # ========================================================
            # RULE 6 — ENTRY must remain below UL
            # ========================================================
            entry_idx = base3_idx + 11
            if entry_idx >= n:
                break

            if df.iloc[entry_idx]['close'] >= level_value:
                i = entry_idx + 1
                continue

            entry_price = df.iloc[entry_idx]['close']

            trades.append({
                'entry_idx'    : entry_idx,
                'entry_date'   : dates[entry_idx],
                'entry_price'  : entry_price,
                'mode'         : 'B',
                'ul'           : level_value,

                'base2_idx'    : base2_idx,
                'retest_idx'   : retest_idx,
                'base3_idx'    : base3_idx,
            })

            i = entry_idx + 1

        return trades


    def backtest_for_symbol(df_daily, sr_levels, march_close_price=None):

        df = df_daily.copy()
        df['marker'] = ''  
        n = len(df)
        dates = df.index

        ul_levels = []
        for i in range(1, 7):
            p = sr_levels.get(f'P{i}')
            if p: ul_levels.append(float(p))
        h = sr_levels.get("High (Ref)")
        if h: ul_levels.append(float(h))
        a = sr_levels.get("Average")
        if a: ul_levels.append(float(a))

        ul_levels = sorted(set([x for x in ul_levels if x > 0]))

        if march_close_price:
            ul_levels = [x for x in ul_levels if x > march_close_price]

        all_candidates = []

        for ul in ul_levels:
            up = find_base_candles_upper(df, ul)
            dn = find_base_candles_below(df, ul)
            for x in up + dn:
                x['ul'] = ul
                all_candidates.append(x)

        all_candidates.sort(key=lambda x: x['entry_idx'])

        trades = []
        last_exit_idx = -1

        for c in all_candidates:

            entry_idx = c['entry_idx']
            if entry_idx <= last_exit_idx:
                continue

            entry_price = c['entry_price']
            entry_date = c['entry_date']

            df.at[dates[entry_idx], 'marker'] = 'ENTRY'

            if 'base1_idx' in c:
                df.at[dates[c['base1_idx']], 'marker'] = 'BASE1'
                df.at[dates[c['breakout_idx']], 'marker'] = 'BREAKOUT'
                df.at[dates[c['retest_idx']], 'marker'] = 'RETEST'
                df.at[dates[c['base2_idx']], 'marker'] = 'BASE2'

            if 'base2_idx' in c and c['mode'] == 'B':
                df.at[dates[c['base2_idx']], 'marker'] = 'B2'
                df.at[dates[c['retest_idx']], 'marker'] = 'RET2'
                df.at[dates[c['base3_idx']], 'marker'] = 'B3'

            end25 = min(n - 1, entry_idx + 25)
            high25 = df.iloc[entry_idx:end25 + 1]['high'].max()

            exit_price = None
            exit_idx = None
            exit_date = None

            for k in range(entry_idx, end25 + 1):
                if df.iloc[k]['high'] >= high25:
                    exit_price = high25
                    exit_idx = k
                    exit_date = dates[k]
                    break

            if exit_price is None:
                end7A = min(n - 1, end25 + 7)
                for k in range(end25 + 1, end7A + 1):
                    if df.iloc[k]['high'] >= high25:
                        exit_price = high25
                        exit_idx = k
                        exit_date = dates[k]
                        break

            if exit_price is None:
                end7B = min(n - 1, end25 + 14)
                for k in range(end25 + 8, end7B + 1):
                    if df.iloc[k]['high'] >= high25:
                        exit_price = high25
                        exit_idx = k
                        exit_date = dates[k]
                        break

            if exit_price is None:
                exit_idx = end25 + 14
                if exit_idx >= n:
                    exit_idx = n - 1
                exit_price = df.iloc[exit_idx]['close']
                exit_date = dates[exit_idx]

            df.at[exit_date, 'marker'] = 'EXIT'

            pnl = round(((exit_price - entry_price) / entry_price) * 100, 2)

            trades.append({
                'entry_date'  : entry_date,
                'entry_price' : entry_price,
                'exit_date'   : exit_date,
                'exit_price'  : exit_price,
                'pnl_pct'     : pnl,
                'mode'        : c['mode'],
                'ul'          : c['ul'],
            })

            last_exit_idx = exit_idx

        return pd.DataFrame(trades), df


        
    def plot_chart_with_signals(df, sr_levels, annotated_df, title, show_volume=True, show_all_levels=False):
        fig = go.Figure()

        # ========================
        # PRICE CANDLESTICKS
        # ========================
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df["open"], high=df["high"],
            low=df["low"], close=df["close"],
            name="Price"
        ))

        # ========================
        # VOLUME BARS
        # ========================
        if show_volume and "volume" in df.columns:
            fig.add_trace(go.Bar(
                x=df.index, y=df["volume"],
                name="Volume", yaxis="y2", opacity=0.3
            ))

        # ========================
        # MARKERS — ENTRY / EXIT / BASE / RETEST
        # ========================
        if "marker" in annotated_df.columns:

            # ENTRY
            e = annotated_df[annotated_df["marker"] == "ENTRY"]
            if not e.empty:
                fig.add_trace(go.Scatter(
                    x=e.index, y=e["close"], mode="markers",
                    marker_symbol="triangle-up", marker_size=16,
                    marker_color="lime", name="ENTRY"
                ))

            # EXIT
            x = annotated_df[annotated_df["marker"] == "EXIT"]
            if not x.empty:
                fig.add_trace(go.Scatter(
                    x=x.index, y=x["close"], mode="markers",
                    marker_symbol="x", marker_size=16,
                    marker_color="red", name="EXIT"
                ))

            # BASE1
            b1 = annotated_df[annotated_df["marker"] == "BASE1"]
            if not b1.empty:
                fig.add_trace(go.Scatter(
                    x=b1.index, y=b1["low"], mode="markers",
                    marker_symbol="square", marker_size=14,
                    marker_color="yellow", name="BASE1"
                ))

            # BREAKOUT
            bo = annotated_df[annotated_df["marker"] == "BREAKOUT"]
            if not bo.empty:
                fig.add_trace(go.Scatter(
                    x=bo.index, y=bo["close"], mode="markers",
                    marker_symbol="diamond", marker_size=14,
                    marker_color="cyan", name="BREAKOUT"
                ))

            # RETEST
            r1 = annotated_df[annotated_df["marker"] == "RETEST"]
            if not r1.empty:
                fig.add_trace(go.Scatter(
                    x=r1.index, y=r1["low"], mode="markers",
                    marker_symbol="circle", marker_size=12,
                    marker_color="deepskyblue", name="RETEST"
                ))

            # BASE2
            b2 = annotated_df[annotated_df["marker"] == "BASE2"]
            if not b2.empty:
                fig.add_trace(go.Scatter(
                    x=b2.index, y=b2["low"], mode="markers",
                    marker_symbol="hexagon", marker_size=14,
                    marker_color="orange", name="BASE2"
                ))

            # BELOW-UL BASE2
            b2b = annotated_df[annotated_df["marker"] == "B2"]
            if not b2b.empty:
                fig.add_trace(go.Scatter(
                    x=b2b.index, y=b2b["low"], mode="markers",
                    marker_symbol="star", marker_size=14,
                    marker_color="magenta", name="BASE2-B"
                ))

            # BELOW-UL RETEST
            rt2 = annotated_df[annotated_df["marker"] == "RET2"]
            if not rt2.empty:
                fig.add_trace(go.Scatter(
                    x=rt2.index, y=rt2["low"], mode="markers",
                    marker_symbol="triangle-down", marker_size=12,
                    marker_color="pink", name="RETEST-B"
                ))

            # BELOW-UL BASE3
            b3 = annotated_df[annotated_df["marker"] == "B3"]
            if not b3.empty:
                fig.add_trace(go.Scatter(
                    x=b3.index, y=b3["low"], mode="markers",
                    marker_symbol="pentagon", marker_size=14,
                    marker_color="gold", name="BASE3-B"
                ))

        # ========================
        # SR LEVEL LINES
        # ========================
        def safe_level(key):
            val = sr_levels.get(key) if isinstance(sr_levels, dict) else None
            try:
                if val is None:
                    return None
                valf = float(val)
                if pd.isna(valf) or valf == 0.0:
                    return None
                return valf
            except Exception:
                return None

        # L1–L6
        for i in range(1, 7):
            key = f"L{i}"
            lvl = safe_level(key)
            if lvl is not None:
                fig.add_hline(
                    y=lvl, line_dash="dot",
                    line_color="green",
                    annotation_text=f"{key}: {lvl}",
                    annotation_position="top left"
                )

        # P1–P6
        for i in range(1, 7):
            key = f"P{i}"
            lvl = safe_level(key)
            if lvl is not None:
                fig.add_hline(
                    y=lvl, line_dash="dot",
                    line_color="red",
                    annotation_text=f"{key}: {lvl}",
                    annotation_position="bottom left"
                )

        # HIGH REF
        try:
            high_ref_val = sr_levels.get("High (Ref)")
            if high_ref_val is not None:
                high_ref_val = float(high_ref_val)
                fig.add_hline(
                    y=high_ref_val,
                    line_dash="dashdot",
                    line_color="magenta",
                    annotation_text=f"High (Ref): {high_ref_val:.2f}",
                    annotation_position="top left"
                )
        except:
            pass

        # AVG LINE
        avg_price = None
        if isinstance(sr_levels, dict):
            avg_price = sr_levels.get("Average")
        try:
            if avg_price is not None:
                avg_price = float(avg_price)
        except:
            avg_price = None

        if avg_price is None or pd.isna(avg_price):
            avg_price = float(df["close"].mean())

        fig.add_hline(
            y=avg_price,
            line_dash="dash",
            line_color="yellow",
            annotation_text=f"Base FY Avg: {avg_price:.2f}",
            annotation_position="top right"
        )

        # ========================
        # LAYOUT + STYLE
        # ========================
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Price",
            template="plotly_dark",
            height=750,
            uirevision=True,
            plot_bgcolor="#0d1117",
            paper_bgcolor="#0d1117",
            font=dict(color="white"),
            hovermode="x unified",
            yaxis2=dict(
            overlaying='y',
            side='right',
            showgrid=False,
            layer='below traces',
            title='Volume' if show_volume else None
            ),
            updatemenus=[
                dict(
                    type="buttons",
                    showactive=False,
                    buttons=[
                        dict(
                            label="Reset Zoom",
                            method="relayout",
                            args=[{"xaxis.autorange": True, "yaxis.autorange": True}]
                        )
                    ]
                )
            ],
        )

        fig.update_xaxes(
            showspikes=True, spikemode='across', spikecolor='white',
            spikesnap='cursor', rangeslider=dict(visible=False),
            showgrid=True, gridcolor="rgba(255,255,255,0.05)"
        )

        fig.update_yaxes(
            fixedrange=False, showspikes=True, spikemode='across',
            spikecolor='white', showgrid=True, gridcolor="rgba(255,255,255,0.05)"
        )

        return fig



    # def plot_chart_with_signals(df, sr_levels, annotated_df, title, show_volume=True, show_all_levels=False):
    #     fig = go.Figure()

    #     fig.add_trace(go.Candlestick(
    #         x=df.index,
    #         open=df["open"], high=df["high"],
    #         low=df["low"], close=df["close"],
    #         name="Price"
    #     ))

    #     if show_volume and "volume" in df.columns:
    #         fig.add_trace(go.Bar(
    #             x=df.index, y=df["volume"],
    #             name="Volume", yaxis="y2", opacity=0.3
    #         ))

    #     if "marker" in annotated_df.columns:

    #         e = annotated_df[annotated_df["marker"] == "ENTRY"]
    #         if not e.empty:
    #             fig.add_trace(go.Scatter(
    #                 x=e.index, y=e["close"], mode="markers",
    #                 marker_symbol="triangle-up", marker_size=20,
    #                 marker_color="lime", name="ENTRY"
    #             ))

    #         x = annotated_df[annotated_df["marker"] == "EXIT"]
    #         if not x.empty:
    #             fig.add_trace(go.Scatter(
    #                 x=x.index, y=x["close"], mode="markers",
    #                 marker_symbol="x", marker_size=20,
    #                 marker_color="red", name="EXIT"
    #             ))

    #     fig.update_layout(
    #         title=title,
    #         template="plotly_dark",
    #         height=700
    #     )

    #     return fig

    #########################################################
    # UI INPUT SECTION (IN TAB3)
    #########################################################
    base_year = st.selectbox(
        "📘 Select Base FY (for S/R Levels)",
        ["2020-2021", "2021-2022", "2022-2023", "2023-2024", "2024-2025"],
        key="tab3_base_year"
    )

    march_year = st.selectbox(
        "📅 Select March Closing Year (Backtest starts AFTER this March)",
        [2023, 2024, 2025, 2026],
        index=1,
        key="tab3_march_year"
    )

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

    nifty500_symbols = get_nifty500_symbols()

    user_symbol = st.selectbox(
        "Select symbol for backtest",
        nifty500_symbols,
        index=0,
        key="tab3_user_symbol"
    )

    segment = st.selectbox("Segment", ['EQ', 'FUT'], key="tab3_segment")
    symbol_full = f"NSE:{user_symbol}-{'EQ' if segment=='EQ' else 'FUT'}"

    plot_all_levels = st.checkbox("Plot all S/R levels", value=True, key="tab3_plot_levels")
    show_volume_sidebar = st.checkbox("Show volume", value=True, key="tab3_plot_volume")

    #########################################################
    # RUN BUTTON
    #########################################################
    if st.button("🔁 Run Backtest (fetch & test)", key="tab3_run"):

        with st.spinner("Fetching data and running backtest..."):
            df_all = fetch_5yr_data_monthwise(symbol_full, end_date=None, years=6)

            if df_all.empty:
                st.error("No historical data returned.")
            else:
                df_all = df_all.sort_index()

                fy_start = dt.datetime(int(base_year.split('-')[0]), 4, 1)
                fy_end  = dt.datetime(int(base_year.split('-')[1]), 3, 31)
                sr_df   = df_all[(df_all.index >= fy_start) & (df_all.index <= fy_end)]
                sr      = calculate_sr_levels(sr_df)

                show_levels = st.checkbox("Show S/R Levels Table", value=True, key="tab3_sr_show")

                if show_levels:
                    st.dataframe(pd.DataFrame([sr]).T, use_container_width=True)

                backtest_start = dt.datetime(int(march_year), 3, 31)

                march_close_price = None
                march_rows = df_all[df_all.index <= backtest_start]
                if not march_rows.empty:
                    march_idx = march_rows.index.max()
                    march_close_price = float(df_all.loc[march_idx, 'close'])
                    st.info(f"March closing price = {march_close_price}")

                df_backtest = df_all[df_all.index > backtest_start].copy()

                trades_df, annotated = backtest_for_symbol(df_backtest, sr, march_close_price=march_close_price)

                if trades_df.empty:
                    st.warning("No trades found.")
                else:
                    st.subheader("Backtest Result Table")
                    st.dataframe(trades_df, use_container_width=True)

                    csv = trades_df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "📥 Download CSV",
                        csv,
                        f"backtest_{user_symbol}_{base_year}.csv",
                        "text/csv",
                        key="tab3_csv"
                    )

                st.subheader("Chart View")

                fig = plot_chart_with_signals(
                    df_backtest,
                    sr,
                    annotated,
                    f"{user_symbol} Backtest",
                    show_volume=show_volume_sidebar,
                    show_all_levels=plot_all_levels
                )

                st.plotly_chart(fig, use_container_width=True)

                if not trades_df.empty:
                    st.success(
                        f"Trades: {len(trades_df)} | "
                        f"Win Rate: {(trades_df['pnl_pct'] > 0).mean() * 100:.2f}% | "
                        f"Avg PnL%: {trades_df['pnl_pct'].mean():.2f}%"
                    )



# with tab4:
#     st.title("Financial Year SR Levels Export (All Nifty 500)")

#     stock_symbols = get_nifty500_symbols()
#     yahoo_symbols = [s + ".NS" for s in stock_symbols]

#     selected_fy = st.selectbox(
#         "Select Financial Year:",
#         [f"{fy}-{fy+1}" for fy in range(dt.datetime.now().year - 6, dt.datetime.now().year)],
#         index=5
#     )

#     fy_start = f"{selected_fy.split('-')[0]}-04-01"
#     fy_end   = f"{selected_fy.split('-')[1]}-03-31"

#     if st.button("Fetch & Show All Levels"):


#         progress = st.progress(0)
#         results = []
#         no_data = []
#         total = len(yahoo_symbols)

#         for i, symbol in enumerate(yahoo_symbols):
#             try:
#                 df = yf.download(symbol, start=fy_start, end=fy_end, progress=False)

#                 # FIXED MultiIndex flattening
#                 if isinstance(df.columns, pd.MultiIndex):
#                     df.columns = df.columns.droplevel(1)

#                 # Minimum data requirement
#                 if df.empty or len(df) < 30:
#                     no_data.append(symbol.replace(".NS",""))
#                     print("NO DATA:", symbol)
#                     continue

#                 # Rename for your SR function
#                 df = df.rename(columns={
#                     "Open": "open",
#                     "High": "high",
#                     "Low": "low",
#                     "Close": "close",
#                     "Volume": "volume"
#                 })

#                 # Calculate SR using your shared function
#                 sr = calculate_sr_levels(df)

#                 row = {
#                     "FY"        : selected_fy,
#                     "Symbol"    : symbol.replace(".NS",""),
#                     "CMP"       : round(df["close"].iloc[-1], 2),
#                     "Average"   : sr.get("Average"),
#                     "High (Ref)": sr.get("High (Ref)"),  # Now placed next to Average
#                     "% Change"  : sr.get("% Change"),
#                     **{f"L{i}": sr.get(f"L{i}") for i in range(1,7)},
#                     **{f"P{i}": sr.get(f"P{i}") for i in range(1,7)}
#                 }

#                 results.append(row)

#             except Exception as e:
#                 print("FAIL:", symbol, e)
#                 no_data.append(symbol.replace(".NS",""))

#             progress.progress((i + 1) / total)

#         # Show final table + download option
#         if results:
#             df_results = pd.DataFrame(results)

#             # FIXED ORDER → High (Ref) after Average
#             final_order = [
#                 "FY","Symbol","L6","L5","L4","L3","L2","L1",
#                 "Average","High (Ref)","P1","P2","P3","P4","P5","P6",
#                 "% Change","CMP"
#             ]

#             df_results = df_results[[c for c in final_order if c in df_results.columns]]

#             st.success(f"Processed {len(results)} symbols | Skipped {len(no_data)} (insufficient data)")
#             st.dataframe(df_results, use_container_width=True)

#             # Create Excel in memory
#             buffer = BytesIO()
#             with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
#                 df_results.to_excel(writer, index=False, sheet_name="SR Levels")
#             buffer.seek(0)

#             # Download Excel button
#             st.download_button(
#                 label="Download Excel",
#                 data=buffer,
#                 file_name="FY_Nifty500_SR_Levels.xlsx",
#                 mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
#             )

#         else:
#             st.warning("No valid symbols found for selected FY.")

with tab4:
    st.title("Financial Year SR Levels Export (All Nifty 500)")

    import os
    os.makedirs("log", exist_ok=True)

    stock_symbols = get_nifty500_symbols()
    total = len(stock_symbols)
    progress = st.progress(0)

    results = []
    no_data = []

    fy_options = [f"{fy}-{fy+1}" for fy in range(dt.datetime.now().year - 6, dt.datetime.now().year)]
    selected_fy = st.selectbox("Select Financial Year:", fy_options, index=5)

    fy_start = f"{selected_fy.split('-')[0]}-04-01"
    fy_end   = f"{selected_fy.split('-')[1]}-03-31"

    if st.button("Fetch & Show All Levels"):
        for i, symbol in enumerate(stock_symbols):
            try:
                sym = f"NSE:{symbol}-EQ"

                # Fetch 1-year history from Fyers
                df = fetch_month_data(sym, fy_start, fy_end)

                # Skip if no data returned
                if df.empty or len(df) < 5:
                    print("Skipping (No history):", symbol)
                    no_data.append(symbol)
                    progress.progress((i + 1) / total)
                    continue

                # Fetch CMP from Fyers
                cmp_price = None
                try:
                    q = fyers.quotes({"symbols": sym})
                    if q.get("s") == "ok" and q.get("d"):
                        cmp_price = float(q["d"][0]["v"]["lp"])
                except Exception as qe:
                    print("Quote fetch failed:", symbol, qe)

                if cmp_price is None:
                    print("Skipping (No CMP):", symbol)
                    no_data.append(symbol)
                    progress.progress((i + 1) / total)
                    continue

                # Compute SR levels from FY data
                sr = calculate_sr_levels(df)

                # Append result row
                row = {
                    "FY"        : selected_fy,
                    "Symbol"    : symbol,
                    "CMP"       : round(cmp_price, 2),
                    "Average"   : sr.get("Average"),
                    "High (Ref)": sr.get("High (Ref)"),
                    "% Change"  : sr.get("% Change"),
                    **{f"L{j}": sr.get(f"L{j}") for j in range(1,7)},
                    **{f"P{j}": sr.get(f"P{j}") for j in range(1,7)}
                }

                results.append(row)

            except Exception as e:
                print("FAIL:", symbol, e)
                no_data.append(symbol)

            progress.progress((i + 1) / total)

        # Display + Export
        if results:
            df_results = pd.DataFrame(results)

            # Correct column order
            final_order = [
                "FY","Symbol","L6","L5","L4","L3","L2","L1",
                "Average","High (Ref)","P1","P2","P3","P4","P5","P6",
                "% Change","CMP"
            ]
            df_results = df_results[[c for c in final_order if c in df_results.columns]]

            st.success(f"Processed {len(df_results)} symbols | Skipped {len(no_data)} (No data/CMP)")
            st.dataframe(df_results, use_container_width=True)

            # Excel in-memory download
            from io import BytesIO
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df_results.to_excel(writer, index=False, sheet_name="SR Levels")
            buffer.seek(0)

            st.download_button(
                label="Download Excel",
                data=buffer,
                file_name=f"SR_Levels_{selected_fy}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        else:
            st.warning("No valid symbols found for selected FY. Check logs for skipped symbols.")


