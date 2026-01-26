
# import requests
# import pandas as pd
# from io import StringIO
# import yfinance as yf



# def get_nifty500_symbols():
#     url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
#     headers = {
#         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
#         "Referer": "https://www.nseindia.com/",
#     }
#     s = requests.Session()
#     s.get("https://www.nseindia.com", headers=headers)
#     r = s.get(url, headers=headers)
#     df = pd.read_csv(StringIO(r.text))
#     stock_list = df['Symbol'].dropna().unique().tolist()
#     stock_list.sort()
#     return stock_list



# nifty500_symbols = get_nifty500_symbols()

# print("Nifty 500 Symbols:")

# for symbol in nifty500_symbols:
#     symbol+= ".NS"

#     data = yf.download(symbol, period='max', interval='1wk', progress=False)
#     data = data.round(2)
#     data.columns = data.columns.get_level_values(0)

#     data.rename(columns={
#         "Open": "open",
#         "High": "high",
#         "Low": "low",
#         "Close": "close",
#         "Volume": "volume"
#     }, inplace=True)

#     # Convert to IST
#     # data.index = data.index.tz_convert("Asia/Kolkata").tz_localize(None)

#     print(data)
#     print(symbol)


################################################################# first code snippet #####################################################################


# # streamlit run weekly_scanner.py

# import streamlit as st
# import pandas as pd
# import yfinance as yf
# import requests
# from io import StringIO
# import datetime as dt

# st.set_page_config("SR Level Scanner", layout="wide")

# # ======================================================
# # FETCH NIFTY 500 SYMBOLS
# # ======================================================
# @st.cache_data
# def get_nifty500_symbols():
#     url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
#     headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com/"}
#     s = requests.Session()
#     s.get("https://www.nseindia.com", headers=headers)
#     r = s.get(url, headers=headers)
#     df = pd.read_csv(StringIO(r.text))
#     return sorted(df["Symbol"].dropna().tolist())

# # ======================================================
# # SR CALCULATION (UNCHANGED)
# # ======================================================
# def calculate_sr_levels(df):
#     high = df["high"].max()
#     low = df["low"].min()
#     pc = (high - low) / high if high else 0
#     avg = (high + low) / 2

#     supports = []
#     lvl = high - high * pc
#     supports.append(lvl)
#     for _ in range(5):
#         lvl -= lvl * pc
#         supports.append(lvl)
#     supports = supports[::-1]

#     resistances = []
#     lvl = high + high * pc
#     resistances.append(lvl)
#     for _ in range(5):
#         lvl += lvl * pc
#         resistances.append(lvl)

#     sr = {f"L{i+1}": round(supports[i], 2) for i in range(6)}
#     sr.update({f"P{i+1}": round(resistances[i], 2) for i in range(6)})
#     sr["Average"] = round(avg, 2)
#     sr["High (Ref)"] = round(high, 2)

#     return sr

# # ======================================================
# # FY FILTER
# # ======================================================
# def filter_fy(df, fy):
#     start = dt.datetime(fy, 4, 1)
#     end = dt.datetime(fy + 1, 3, 31)
#     return df[(df.index >= start) & (df.index <= end)]

# # ======================================================
# # UI
# # ======================================================
# st.title("📊 FY Support & Resistance Scanner (NIFTY 500)")

# symbols = get_nifty500_symbols()

# fy_list = [f"{y}-{y+1}" for y in range(dt.datetime.now().year - 4, dt.datetime.now().year + 1)]
# selected_fy = st.selectbox("Select Financial Year", fy_list)
# fy_year = int(selected_fy.split("-")[0])

# selected_date = st.date_input("Select Date")

# # ======================================================
# # SCANNER
# # ======================================================
# if st.button("Run SR Scanner"):
#     below_LL, touch_LL, above_UL, touch_UL = [], [], [], []

#     with st.spinner("Scanning NIFTY 500 stocks..."):
#         for sym in symbols:
#             df = yf.download(sym + ".NS", period="max", interval="1wk", progress=False)
#             if df.empty:
#                 continue

#             df.columns = df.columns.get_level_values(0)
#             df.rename(columns={"High": "high", "Low": "low", "Close": "close"}, inplace=True)
#             df.dropna(inplace=True)
#             print(df)

#             fy_df = filter_fy(df, fy_year)
#             if fy_df.empty:
#                 continue

#             sr = calculate_sr_levels(fy_df)
#             LL = sr["L6"]
#             UL = sr["P6"]

#             day = df.loc[df.index.date == selected_date]
#             if day.empty:
#                 continue

#             c, l, h = day.iloc[-1][["close", "low", "high"]]

#             if c < LL:
#                 below_LL.append(sym)
#             elif l <= LL <= c:
#                 touch_LL.append(sym)
#             elif c > UL:
#                 above_UL.append(sym)
#             elif h >= UL >= c:
#                 touch_UL.append(sym)

#     col1, col2, col3, col4 = st.columns(4)

#     col1.subheader(f"🔴 Close Below LL ({len(below_LL)})")
#     col1.write(below_LL)

#     col2.subheader(f"🟡 Low Touch LL ({len(touch_LL)})")
#     col2.write(touch_LL)

#     col3.subheader(f"🟢 Close Above UL ({len(above_UL)})")
#     col3.write(above_UL)

#     col4.subheader(f"🔵 High Touch UL ({len(touch_UL)})")
#     col4.write(touch_UL)






################################################################# Second code snippet #####################################################################



# streamlit run weekly_scanner.py

import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from io import StringIO
import datetime as dt

st.set_page_config("SR Level Scanner", layout="wide")

# ======================================================
# FETCH NIFTY 500 SYMBOLS
# ======================================================
@st.cache_data
def get_nifty500_symbols():
    url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.nseindia.com/"
    }
    s = requests.Session()
    s.get("https://www.nseindia.com", headers=headers)
    r = s.get(url, headers=headers)
    df = pd.read_csv(StringIO(r.text))
    return sorted(df["Symbol"].dropna().tolist())

# ======================================================
# SR CALCULATION
# ======================================================
def calculate_sr_levels(df):
    high = df["high"].max()
    low = df["low"].min()
    pc = (high - low) / high if high else 0
    avg = (high + low) / 2

    supports = []
    lvl = high - high * pc
    supports.append(lvl)
    for _ in range(5):
        lvl -= lvl * pc
        supports.append(lvl)
    supports = supports[::-1]

    resistances = []
    lvl = high + high * pc
    resistances.append(lvl)
    for _ in range(5):
        lvl += lvl * pc
        resistances.append(lvl)

    sr = {f"L{i+1}": round(supports[i], 2) for i in range(6)}
    sr.update({f"P{i+1}": round(resistances[i], 2) for i in range(6)})
    sr["Average"] = round(avg, 2)
    sr["High (Ref)"] = round(high, 2)

    return sr

# ======================================================
# FY FILTER
# ======================================================
def filter_fy(df, fy):
    start = dt.datetime(fy, 4, 1)
    end = dt.datetime(fy + 1, 3, 31)
    return df[(df.index >= start) & (df.index <= end)]

# ======================================================
# UI
# ======================================================
st.title("📊 FY Support & Resistance Scanner (NIFTY 500)")

symbols = get_nifty500_symbols()

fy_list = [f"{y}-{y+1}" for y in range(dt.datetime.now().year - 4, dt.datetime.now().year + 1)]
selected_fy = st.selectbox("Select Financial Year", fy_list)
fy_year = int(selected_fy.split("-")[0])

selected_date = st.date_input("Select Date")

# ======================================================
# SCANNER
# ======================================================
if st.button("Run SR Scanner"):
    below_LL, touch_LL, above_UL, touch_UL = [], [], [], []

    with st.spinner("Scanning NIFTY 500 stocks..."):
        for sym in symbols:
            df = yf.download(sym + ".NS", period="max", interval="1wk", progress=False)

            if df.empty:
                continue

            df.columns = df.columns.get_level_values(0)
            df.rename(columns={"High": "high", "Low": "low", "Close": "close"}, inplace=True)
            df.dropna(inplace=True)

            fy_df = filter_fy(df, fy_year)
            if fy_df.empty:
                continue

            sr = calculate_sr_levels(fy_df)

            # ---- ALL LEVELS (dynamic) ----
            levels = sorted(sr.values())

            # ---- Get nearest weekly candle <= selected date ----
            day = df[df.index.date <= selected_date]
            if day.empty:
                continue

            day = day.iloc[-1]
            c, l, h = day[["close", "low", "high"]]

            # ---- Nearest LL & UL ----
            LL = max([lvl for lvl in levels if lvl <= c], default=None)
            UL = min([lvl for lvl in levels if lvl >= c], default=None)

            if LL is None or UL is None:
                continue

            # ---- SAME CONDITIONS ----
            if c < LL:
                below_LL.append(sym)

            elif l <= LL <= c:
                touch_LL.append(sym)

            elif c > UL:
                above_UL.append(sym)

            elif h >= UL >= c:
                touch_UL.append(sym)

    col1, col2, col3, col4 = st.columns(4)

    col1.subheader(f"🔴 Close Below LL ({len(below_LL)})")
    col1.write(below_LL)

    col2.subheader(f"🟡 Low Touch LL ({len(touch_LL)})")
    col2.write(touch_LL)

    col3.subheader(f"🟢 Close Above UL ({len(above_UL)})")
    col3.write(above_UL)

    col4.subheader(f"🔵 High Touch UL ({len(touch_UL)})")
    col4.write(touch_UL)
