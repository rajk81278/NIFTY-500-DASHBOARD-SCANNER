

# # streamlit run copy_upper_buy.py

import streamlit as st
import pandas as pd
import datetime as dt
from fyers_apiv3 import fyersModel
import plotly.graph_objects as go
import time
import requests
from io import StringIO
import concurrent.futures
import warnings
import os

warnings.filterwarnings("ignore", message=".*missing ScriptRunContext!.*")

# -----------------------------
# Fyers client (ensure access.txt exists with valid token)
# -----------------------------
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
        if not data:
            return pd.DataFrame()
        if data.get("s") == "ok" and "candles" in data:
            df = pd.DataFrame(data["candles"], columns=["date", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["date"], unit="s")
            df.set_index("date", inplace=True)
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        try:
            st.warning(f"fetch_month_data exception for {symbol} {from_date} -> {to_date}: {e}")
        except Exception:
            pass
        return pd.DataFrame()


CACHE_DIR = "data_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

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
    path = _cache_path(symbol)
    df.to_parquet(path)

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

def resample_monthly(df):
    df_monthly = df.resample('M').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'})
    df_monthly.dropna(inplace=True)
    return df_monthly

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
        if data and data.get("s") == "ok" and data.get("d"):
            return float(data["d"][0].get("v", {}).get("lp", 0))
    except Exception:
        return None


###############################################################
# UPDATED — FIND BASE ABOVE UL (WITH MARKERS)
###############################################################


# def find_base_candles_upper(df, level_value):
#     trades = []
#     n = len(df)
#     dates = df.index
#     i = 0

#     while i < n:

#         # ========================================================
#         # RULE 1: Reject any base formation until first UL breakout
#         # ========================================================
#         # Confirm at least one candle before i has closed OR opened above UL
#         above_ul_visible = False
#         for j in range(i):
#             if df.iloc[j]['close'] > level_value or df.iloc[j]['open'] > level_value:
#                 above_ul_visible = True
#                 break

#         if not above_ul_visible:
#             i += 1
#             continue

#         # ========================================================
#         # RULE 2: base1 must be 100% above UL (no overlap allowed)
#         # ========================================================
#         if df.iloc[i]['low'] <= level_value:
#             i += 1
#             continue

#         base1_idx = i
#         base1_low = df.iloc[i]['low']

#         # ========================================================
#         # RULE 3: 5-day stability condition
#         # ========================================================
#         if base1_idx + 5 >= n:
#             break

#         fail = False
#         for k in range(base1_idx + 1, base1_idx + 6):

#             # must remain above UL
#             if df.iloc[k]['low'] <= level_value:
#                 fail = True
#                 break

#             # cannot violate base low
#             if df.iloc[k]['low'] <= base1_low:
#                 fail = True
#                 break

#         if fail:
#             i = k + 1
#             continue

#         # ========================================================
#         # RULE 4: breakout must exceed the 5-day high
#         # ========================================================
#         win = df.iloc[base1_idx + 1 : base1_idx + 6]
#         five_high = win['high'].max()

#         breakout_idx = None
#         for k in range(base1_idx + 6, n):
#             if df.iloc[k]['close'] > five_high and df.iloc[k]['close'] > level_value:
#                 breakout_idx = k
#                 break

#         if breakout_idx is None:
#             i = base1_idx + 1
#             continue

#         # ========================================================
#         # RULE 5: retest must stay ABOVE UL and ABOVE five_high
#         # ========================================================
#         retest_idx = None
#         for k in range(breakout_idx + 1, n):

#             # if retest goes below UL – cancel
#             if df.iloc[k]['low'] <= level_value:
#                 break

#             # valid retest
#             if df.iloc[k]['low'] < five_high:
#                 retest_idx = k
#                 break

#         if retest_idx is None:
#             i = breakout_idx + 1
#             continue

#         # ========================================================
#         # RULE 6: second base must form ABOVE UL
#         # ========================================================
#         base2_idx = None
#         base2_low = None
#         for k in range(retest_idx + 1, n):

#             # must remain above UL
#             if df.iloc[k]['low'] <= level_value:
#                 break

#             # close must exceed five_high
#             if df.iloc[k]['close'] > five_high:
#                 base2_idx = k
#                 base2_low = df.iloc[k]['low']
#                 break

#         if base2_idx is None:
#             i = retest_idx + 1
#             continue

#         # ========================================================
#         # RULE 7: second base 5-day stability check
#         # ========================================================
#         if base2_idx + 5 >= n:
#             break

#         fail2 = False
#         for k in range(base2_idx + 1, base2_idx + 6):

#             # cannot go below UL
#             if df.iloc[k]['low'] <= level_value:
#                 fail2 = True
#                 break

#             # cannot break second base low
#             if df.iloc[k]['low'] <= base2_low:
#                 fail2 = True
#                 break

#         if fail2:
#             i = base2_idx + 1
#             continue

#         # ========================================================
#         # RULE 8: ENTRY must be ABOVE UL
#         # ========================================================
#         entry_idx = base2_idx + 6
#         if entry_idx >= n:
#             break

#         if df.iloc[entry_idx]['close'] <= level_value:
#             i = entry_idx + 1
#             continue

#         entry_price = df.iloc[entry_idx]['close']

#         trades.append({
#             'entry_idx'       : entry_idx,
#             'entry_date'      : dates[entry_idx],
#             'entry_price'     : entry_price,
#             'mode'            : 'A',
#             'ul'              : level_value,

#             'base1_idx'       : base1_idx,
#             'five_high'       : five_high,
#             'breakout_idx'    : breakout_idx,
#             'retest_idx'      : retest_idx,
#             'base2_idx'       : base2_idx,
#         })

#         i = entry_idx + 1

#     return trades

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
        dragmode="pan",
        plot_bgcolor="#0d1117",
        paper_bgcolor="#0d1117",
        font=dict(color="white"),
        hovermode="x unified",
        yaxis2=dict(
            overlaying='y', side='right', showgrid=False,
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
        spikesnap='cursor', rangeslider=dict(visible=True),
        showgrid=True, gridcolor="rgba(255,255,255,0.05)"
    )

    fig.update_yaxes(
        fixedrange=False, showspikes=True, spikemode='across',
        spikecolor='white', showgrid=True, gridcolor="rgba(255,255,255,0.05)"
    )

    return fig


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="SR Backtest (Fixed Fetch + Markers)", layout="wide")
st.title("SR Backtester — fixed data fetching + positional rules (with markers)")

# Manual selectors
base_year = st.selectbox("📘 Select Base FY (for S/R Levels)", ["2020-2021", "2021-2022", "2022-2023", "2023-2024", "2024-2025"])
march_year = st.selectbox("📅 Select March Closing Year (Backtest starts AFTER this March)", [2023, 2024, 2025, 2026], index=1)

# symbol selection
@st.cache_data(ttl=86400)
def get_nifty500_symbols():
    url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
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
    except Exception:
        return ["SBIN", "TCS", "RELIANCE"]

nifty500_symbols = get_nifty500_symbols()
user_symbol = st.selectbox("Select symbol for backtest", nifty500_symbols, index=0)
segment = st.selectbox("Segment", ['EQ', 'FUT'])
symbol_full = f"NSE:{user_symbol}-{'EQ' if segment=='EQ' else 'FUT'}"

# Sidebar controls
plot_all_levels = st.sidebar.checkbox("Plot all S/R levels (L1–L6, Average, P1–P6)", value=True)
show_volume_sidebar = st.sidebar.checkbox("Show volume on chart", value=True)

# Run backtest
if st.button("🔁 Run Backtest (fetch & test)"):
    with st.spinner("Fetching data (30-day chunks) and running backtest..."):
        df_all = fetch_5yr_data_monthwise(symbol_full, end_date=None, years=6)

        if df_all.empty:
            st.error("No historical data returned. Possible reasons:\n- invalid token / fyers API limit\n- symbol not available for requested period\nCheck logs above for chunk-level debug messages.")
        else:
            df_all = df_all.sort_index()

            # --------- SR LEVELS: based on selected base_year ----------
            fy_start = dt.datetime(int(base_year.split('-')[0]), 4, 1)
            fy_end  = dt.datetime(int(base_year.split('-')[1]), 3, 31)
            sr_df   = df_all[(df_all.index >= fy_start) & (df_all.index <= fy_end)]
            sr      = calculate_sr_levels(sr_df)

            # ---------------------------
            # SHOW S/R LEVELS ON STREAMLIT
            # ---------------------------
            show_levels = st.sidebar.checkbox("Show S/R Levels & FY summary", value=True)

            if show_levels:
                st.markdown("### 🔢 S/R Levels (from selected Base FY)")

                supports = {f"L{i}": sr.get(f"L{i}", "") for i in range(6, 0, -1)}
                resistances = {f"P{i}": sr.get(f"P{i}", "") for i in range(1, 7)}
                meta = {
                    "Average": sr.get("Average", ""),
                    "High (Ref)": sr.get("High (Ref)", ""),
                    "% Change": sr.get("% Change", "")
                }

                col1, col2, col3 = st.columns([2,1,2])

                with col1:
                    st.markdown("**Supports (L6 → L1)**")
                    st.table(pd.DataFrame.from_dict(supports, orient='index', columns=["Price"]))

                with col2:
                    st.markdown("**Summary**")
                    st.metric("Average", meta["Average"])
                    st.metric("High (Ref)", meta["High (Ref)"])
                    st.metric("% Change", f"{meta['% Change']}%")

                with col3:
                    st.markdown("**Resistances (P1 → P6)**")
                    st.table(pd.DataFrame.from_dict(resistances, orient='index', columns=["Price"]))

                with st.expander("Raw Levels + Download"):
                    raw_df = pd.DataFrame([sr])
                    st.dataframe(raw_df.T, use_container_width=True)
                    csv = raw_df.to_csv(index=False).encode('utf-8')
                    st.download_button("Download SR Levels CSV", csv, "sr_levels.csv", "text/csv")

            # --------- BACKTEST RANGE: start AFTER selected March closing ----------
            backtest_start = dt.datetime(int(march_year), 3, 31)

            # March close price for filtering levels
            march_close_price = None
            march_rows = df_all[df_all.index <= backtest_start]
            if not march_rows.empty:
                march_idx = march_rows.index.max()
                march_close_price = float(df_all.loc[march_idx, 'close'])
                st.info(f"March closing used for filtering levels: {march_idx.date()} close = {march_close_price:.2f}")
            else:
                st.warning("Could not find a March closing price in historical data; level filtering will not be applied.")

            df_backtest = df_all[df_all.index > backtest_start].copy()

            if df_backtest.empty:
                st.error("No data available AFTER the selected March closing date for backtest.")
            else:
                trades_df, annotated = backtest_for_symbol(df_backtest, sr, march_close_price=march_close_price)

                if trades_df.empty:
                    st.warning("No trades found by the strategy on this symbol / period.")
                    fig = plot_chart_with_signals(
                        df_backtest,
                        sr,
                        annotated,
                        f"{user_symbol} Backtest (no trades found)",
                        show_volume=show_volume_sidebar,
                        show_all_levels=plot_all_levels
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True,"doubleClick": "reset"})
                else:
                    st.subheader("Backtest Report")
                    display_cols = ['entry_date', 'entry_price', 'exit_date', 'exit_price',
                                    'pnl_pct', 'target', 'reason', 'type', 'mode',
                                    'base_date', 'breakout_date', 'second_base_date']
                    trades_df_display = trades_df[[c for c in display_cols if c in trades_df.columns]]
                    trades_df_display['entry_date'] = pd.to_datetime(trades_df_display['entry_date'])
                    trades_df_display['exit_date'] = pd.to_datetime(trades_df_display['exit_date'])
                    if 'breakout_date' in trades_df_display.columns:
                        trades_df_display['breakout_date'] = pd.to_datetime(trades_df_display['breakout_date'])
                    if 'second_base_date' in trades_df_display.columns:
                        trades_df_display['second_base_date'] = pd.to_datetime(trades_df_display['second_base_date'])

                    st.dataframe(trades_df_display, use_container_width=True)

                    csv = trades_df_display.to_csv(index=False).encode('utf-8')
                    st.download_button('📥 Download Backtest CSV', csv, f'backtest_{user_symbol}_{base_year}.csv', 'text/csv')

                    st.subheader("Chart with signals (post-March backtest zone)")
                    fig = plot_chart_with_signals(
                        df_backtest,
                        sr,
                        annotated,
                        f"{user_symbol} Backtest",
                        show_volume=show_volume_sidebar,
                        show_all_levels=plot_all_levels
                    )

                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        config={
                            "scrollZoom": True,
                            "doubleClick": "reset",
                        },
                    )

                    total_trades = len(trades_df)
                    win_rate = (trades_df['pnl_pct'] > 0).mean() * 100
                    avg_pnl = trades_df['pnl_pct'].mean()
                    st.info(f"Trades: {total_trades} | Win rate: {win_rate:.2f}% | Avg PnL%: {avg_pnl:.2f}%")

            # DEBUG: show which levels were used
            try:
                p_levels_all = [sr.get(f"P{i}") for i in range(1, 7)]
                high_ref_dbg = sr.get("High (Ref)")
                if high_ref_dbg:
                    p_levels_all.append(high_ref_dbg)
                avg_dbg = sr.get("Average")
                if avg_dbg:
                    p_levels_all.append(avg_dbg)

                l_levels_all = [sr.get(f"L{i}") for i in range(1, 7)]

                st.markdown("**(debug) All computed P-levels (incl High(Ref)+Avg):** " +
                            ", ".join([str(x) for x in p_levels_all if x]))
                st.markdown("**(debug) All computed L-levels:** " +
                            ", ".join([str(x) for x in l_levels_all if x]))

                if march_close_price is not None:
                    used_p = [p for p in p_levels_all if p and float(p) > march_close_price]
                    used_l = [l for l in l_levels_all if l and float(l) < march_close_price]
                    st.markdown(f"**(debug) Levels used for UL (above March close, incl High(Ref)+Avg):** {used_p}")
                    st.markdown(f"**(debug) Levels used for LL (below March close):** {used_l}")
            except Exception:
                pass
