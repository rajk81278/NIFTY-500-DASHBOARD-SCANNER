# # streamlit run main_with_login.py

# # ==============================================
# # 🔐 FYERS LOGIN PAGE (Unmodified)
# # ==============================================
# import streamlit as st
# import webbrowser
# import time
# import pyotp as tp
# from fyers_apiv3 import fyersModel
# import credentials as crs

# # -------------------------------
# # Streamlit Page Config
# # -------------------------------
# st.set_page_config(page_title="🔐 Fyers Login Dashboard", layout="wide")
# st.title("🔐 Fyers Login — Get Your Access Token")

# # -------------------------------
# # Session State Setup
# # -------------------------------
# if "access_token" not in st.session_state:
#     st.session_state.access_token = None
# if "auth_code" not in st.session_state:
#     st.session_state.auth_code = None
# if "auth_url" not in st.session_state:
#     st.session_state.auth_url = None
# if "totp" not in st.session_state:
#     st.session_state.totp = None

# # -------------------------------
# # Fyers Credentials
# # -------------------------------
# client_id = crs.client_id
# secret_key = crs.secret_key
# redirect_uri = crs.redirect_uri
# response_type = "code"
# state = "sample_state"

# # -------------------------------
# # Sidebar Section for TOTP
# # -------------------------------
# st.sidebar.header("🔢 Generate TOTP for Fyers Login")

# totp_key = "WS27N6R2XVJI3WW6SKPTZSK3RC7DF24C"

# if st.sidebar.button("Generate TOTP Code"):
#     try:
#         code = tp.TOTP(totp_key).now()
#         st.sidebar.success(f"✅ Your TOTP: **{code}**")
#         st.sidebar.info("Enter this TOTP on the Fyers login page.")
#         st.session_state.totp = code
#     except Exception as e:
#         st.sidebar.error(f"Failed to generate TOTP: {e}")

# # -------------------------------
# # Main Instructions
# # -------------------------------
# st.markdown(
#     """
#     ### 🧭 Instructions
#     1. Click **Open Fyers Login Page** below — Fyers login page will open in a new browser tab.
#     2. Enter your **mobile number** and then use the **TOTP code** from the sidebar.
#     3. Enter your **PIN** and finish login on Fyers.
#     4. After redirect, **copy the full redirected URL** from your browser.
#     5. Paste the URL in the box below to generate your **access token** automatically.
#     """
# )

# # -------------------------------
# # Step 1: Generate Auth URL
# # -------------------------------
# # if st.button("➡ Open Fyers Login Page"):
# #     try:
# #         session = fyersModel.SessionModel(
# #             client_id=client_id,
# #             secret_key=secret_key,
# #             redirect_uri=redirect_uri,
# #             response_type=response_type
# #         )
# #         response = session.generate_authcode()
# #         st.session_state.auth_url = response

# #         try:
# #             webbrowser.open(response, new=1)
# #             st.success("Fyers login page opened in your browser. Complete login there using your TOTP and PIN.")
# #         except Exception:
# #             st.info("Could not open browser automatically — click the link below:")
# #             st.markdown(f"[👉 Open Fyers Login Page]({response})", unsafe_allow_html=True)
# #     except Exception as e:
# #         st.error(f"Error generating Fyers login URL: {e}")

# # # -------------------------------
# # # Step 1: Generate Auth URL (Modified for Streamlit Cloud)
# # # -------------------------------
# # if st.button("➡ Open Fyers Login Page"):
# #     try:
# #         session = fyersModel.SessionModel(
# #             client_id=client_id,
# #             secret_key=secret_key,
# #             redirect_uri=redirect_uri,
# #             response_type=response_type
# #         )
# #         response = session.generate_authcode()
# #         st.session_state.auth_url = response

# #         # ✅ Streamlit Cloud safe redirect
# #         st.markdown(
# #             f"""
# #             <meta http-equiv="refresh" content="0; url={response}" />
# #             """,
# #             unsafe_allow_html=True
# #         )
# #         st.info("Redirecting to Fyers login page... If not redirected, click below:")
# #         st.markdown(f"[👉 Open Fyers Login Page]({response})", unsafe_allow_html=True)

# #     except Exception as e:
# #         st.error(f"Error generating Fyers login URL: {e}")

# # -------------------------------
# # Step 1: Generate Auth URL (Open in New Tab)
# # -------------------------------
# if st.button("➡ Open Fyers Login Page"):
#     try:
#         session = fyersModel.SessionModel(
#             client_id=client_id,
#             secret_key=secret_key,
#             redirect_uri=redirect_uri,
#             response_type=response_type
#         )
#         response = session.generate_authcode()
#         st.session_state.auth_url = response

#         # ✅ Open in new browser tab (instead of redirecting same page)
#         st.markdown(
#             f'''
#             <a href="{response}" target="_blank" style="text-decoration:none;">
#                 <button style="
#                     background-color:#4CAF50;
#                     color:white;
#                     padding:10px 20px;
#                     border:none;
#                     border-radius:5px;
#                     cursor:pointer;">
#                     👉 Open Fyers Login Page
#                 </button>
#             </a>
#             ''',
#             unsafe_allow_html=True
#         )

#         st.info("Fyers login page will open in a new tab. Use the TOTP shown in the sidebar to log in.")
#         st.markdown(f"Or manually open: [🔗 {response}]({response})", unsafe_allow_html=True)

#     except Exception as e:
#         st.error(f"Error generating Fyers login URL: {e}")


# # -------------------------------
# # Step 2: Paste Redirected URL
# # -------------------------------
# redirected_url = st.text_input("Paste the redirected URL here after logging in on Fyers:")

# if redirected_url:
#     try:
#         auth_code = redirected_url[redirected_url.index("auth_code=") + 10: redirected_url.index("&state")]
#         st.session_state.auth_code = auth_code
#         st.success("✅ Auth code extracted successfully.")
#     except Exception as e:
#         st.error("❌ Could not extract auth_code. Please paste the full URL.")
#         st.write(e)

# # -------------------------------
# # Step 3: Generate Access Token
# # -------------------------------
# if st.session_state.auth_code and st.session_state.access_token is None:
#     if st.button("🔑 Generate Access Token"):
#         try:
#             grant_type = "authorization_code"
#             session2 = fyersModel.SessionModel(
#                 client_id=client_id,
#                 secret_key=secret_key,
#                 redirect_uri=redirect_uri,
#                 response_type=response_type,
#                 grant_type=grant_type
#             )
#             session2.set_token(st.session_state.auth_code)
#             token_response = session2.generate_token()

#             if "access_token" in token_response:
#                 access_token = token_response["access_token"]
#                 with open("access.txt", "w") as f:
#                     f.write(access_token)
#                 st.session_state.access_token = access_token
#                 st.success("✅ Access token generated successfully and saved to access.txt!")
#             else:
#                 st.error(f"Failed to generate access token: {token_response}")
#         except Exception as e:
#             st.error(f"Error while generating access token: {e}")

# # -------------------------------
# # Step 4: Verify Connection
# # -------------------------------
# if st.session_state.access_token:
#     st.subheader("✅ Login Successful")
#     st.write("Access Token ready — now you can use your dashboard or scanner.")

#     try:
#         fyers = fyersModel.FyersModel(
#             client_id=client_id,
#             token=st.session_state.access_token,
#             log_path="log/"
#         )
#         data = fyers.quotes({"symbols": "NSE:SBIN-EQ"})
#         if "d" in data:
#             cmp = data["d"][0]["v"]["lp"]
#             st.success(f"✅ Fyers Connected Successfully! SBIN CMP: ₹{cmp}")
#         else:
#             st.info("Fyers connection successful, but quote data not returned.")
#     except Exception as e:
#         st.warning(f"Token valid but test request failed: {e}")

# # -------------------------------
# # Optional Debug
# # -------------------------------
# if st.checkbox("Show Access Token (debug)"):
#     st.code(st.session_state.access_token or "No token yet")

# # ==============================================
# # 🧭 If Logged In — Show Main Dashboard
# # ==============================================
# if st.session_state.access_token:
#     st.markdown("---")
#     st.subheader("📊 Proceed to Dashboard Below")
#     st.markdown("Once logged in successfully, your dashboard will load below.")
#     # Import main dashboard only when access token available
#     # exec(open("dashboard_main.py").read())
#     exec(open("dashboard_main.py", encoding="utf-8").read())

# else:
#     st.stop()

# # ==============================================
# # END OF LOGIN + DASHBOARD COMBINATION
# # ==============================================

# ### second code ############
# # ==============================================
# # 🔐 FYERS LOGIN PAGE with Daily Auto-Login
# # ==============================================
# import streamlit as st
# import webbrowser
# import time
# import os
# import pyotp as tp
# from fyers_apiv3 import fyersModel
# import credentials as crs

# # -------------------------------
# # Streamlit Page Config
# # -------------------------------
# st.set_page_config(page_title="🔐 Fyers Login Dashboard", layout="wide")
# st.title("🔐 Fyers Login — Get Your Access Token")

# # -------------------------------
# # Session State Setup
# # -------------------------------
# if "access_token" not in st.session_state:
#     st.session_state.access_token = None
# if "auth_code" not in st.session_state:
#     st.session_state.auth_code = None
# if "auth_url" not in st.session_state:
#     st.session_state.auth_url = None
# if "totp" not in st.session_state:
#     st.session_state.totp = None

# # -------------------------------
# # Fyers Credentials
# # -------------------------------
# client_id = crs.client_id
# secret_key = crs.secret_key
# redirect_uri = crs.redirect_uri
# response_type = "code"
# state = "sample_state"

# # -------------------------------
# # Function: Check if access token is valid
# # -------------------------------
# def is_token_valid(token):
#     try:
#         fyers = fyersModel.FyersModel(client_id=client_id, token=token, log_path="log/")
#         data = fyers.quotes({"symbols": "NSE:SBIN-EQ"})
#         if "d" in data:
#             return True
#         else:
#             return False
#     except Exception:
#         return False


# # -------------------------------
# # Step 0: Try using saved token first
# # -------------------------------
# access_token_path = "access.txt"
# saved_token = None

# if os.path.exists(access_token_path):
#     with open(access_token_path, "r") as f:
#         saved_token = f.read().strip()

# if saved_token and is_token_valid(saved_token):
#     st.session_state.access_token = saved_token
#     st.success("✅ Existing access token is valid — skipping login!")
# else:
#     st.info("⚠️ No valid token found — please log in below to generate a new one.")


# # =========================================================
# # 🚀 IF TOKEN IS VALID → LOAD DASHBOARD DIRECTLY
# # =========================================================
# if st.session_state.access_token:
#     st.subheader("✅ Login Successful")
#     st.write("Access Token ready — you can now use your dashboard or scanner.")

#     try:
#         fyers = fyersModel.FyersModel(
#             client_id=client_id,
#             token=st.session_state.access_token,
#             log_path="log/"
#         )
#         data = fyers.quotes({"symbols": "NSE:SBIN-EQ"})
#         if "d" in data:
#             cmp = data["d"][0]["v"]["lp"]
#             st.success(f"✅ Fyers Connected Successfully! SBIN CMP: ₹{cmp}")
#         else:
#             st.info("Fyers connection successful, but quote data not returned.")
#     except Exception as e:
#         st.warning(f"Token valid but test request failed: {e}")

#     # ---- Load your main dashboard ----
#     st.markdown("---")
#     st.subheader("📊 Proceed to Dashboard Below")
#     exec(open("dashboard_main.py", encoding="utf-8").read())

#     st.stop()

# # =========================================================
# # 🧭 IF TOKEN INVALID → SHOW LOGIN PROCESS
# # =========================================================

# # -------------------------------
# # Sidebar Section for TOTP
# # -------------------------------
# st.sidebar.header("🔢 Generate TOTP for Fyers Login")

# totp_key = "WS27N6R2XVJI3WW6SKPTZSK3RC7DF24C"

# if st.sidebar.button("Generate TOTP Code"):
#     try:
#         code = tp.TOTP(totp_key).now()
#         st.sidebar.success(f"✅ Your TOTP: **{code}**")
#         st.sidebar.info("Enter this TOTP on the Fyers login page.")
#         st.session_state.totp = code
#     except Exception as e:
#         st.sidebar.error(f"Failed to generate TOTP: {e}")

# # -------------------------------
# # Main Instructions
# # -------------------------------
# st.markdown(
#     """
#     ### 🧭 Instructions
#     1. Click **Open Fyers Login Page** below — Fyers login page will open in a new browser tab.
#     2. Enter your **mobile number** and then use the **TOTP code** from the sidebar.
#     3. Enter your **PIN** and finish login on Fyers.
#     4. After redirect, **copy the full redirected URL** from your browser.
#     5. Paste the URL in the box below to generate your **access token** automatically.
#     """
# )

# # -------------------------------
# # Step 1: Generate Auth URL (Open in New Tab)
# # -------------------------------
# if st.button("➡ Open Fyers Login Page"):
#     try:
#         session = fyersModel.SessionModel(
#             client_id=client_id,
#             secret_key=secret_key,
#             redirect_uri=redirect_uri,
#             response_type=response_type
#         )
#         response = session.generate_authcode()
#         st.session_state.auth_url = response

#         # ✅ Open in new browser tab (instead of redirecting same page)
#         st.markdown(
#             f'''
#             <a href="{response}" target="_blank" style="text-decoration:none;">
#                 <button style="
#                     background-color:#4CAF50;
#                     color:white;
#                     padding:10px 20px;
#                     border:none;
#                     border-radius:5px;
#                     cursor:pointer;">
#                     👉 Open Fyers Login Page
#                 </button>
#             </a>
#             ''',
#             unsafe_allow_html=True
#         )

#         st.info("Fyers login page will open in a new tab. Use the TOTP shown in the sidebar to log in.")
#         st.markdown(f"Or manually open: [🔗 {response}]({response})", unsafe_allow_html=True)

#     except Exception as e:
#         st.error(f"Error generating Fyers login URL: {e}")

# # -------------------------------
# # Step 2: Paste Redirected URL
# # -------------------------------
# redirected_url = st.text_input("Paste the redirected URL here after logging in on Fyers:")

# if redirected_url:
#     try:
#         auth_code = redirected_url[redirected_url.index("auth_code=") + 10: redirected_url.index("&state")]
#         st.session_state.auth_code = auth_code
#         st.success("✅ Auth code extracted successfully.")
#     except Exception as e:
#         st.error("❌ Could not extract auth_code. Please paste the full URL.")
#         st.write(e)

# # -------------------------------
# # Step 3: Generate Access Token
# # -------------------------------
# if st.session_state.auth_code and st.session_state.access_token is None:
#     if st.button("🔑 Generate Access Token"):
#         try:
#             grant_type = "authorization_code"
#             session2 = fyersModel.SessionModel(
#                 client_id=client_id,
#                 secret_key=secret_key,
#                 redirect_uri=redirect_uri,
#                 response_type=response_type,
#                 grant_type=grant_type
#             )
#             session2.set_token(st.session_state.auth_code)
#             token_response = session2.generate_token()

#             if "access_token" in token_response:
#                 access_token = token_response["access_token"]
#                 with open("access.txt", "w") as f:
#                     f.write(access_token)
#                 st.session_state.access_token = access_token
#                 st.success("✅ Access token generated successfully and saved to access.txt!")
#                 st.rerun()  # Reload to auto-load dashboard
#             else:
#                 st.error(f"Failed to generate access token: {token_response}")
#         except Exception as e:
#             st.error(f"Error while generating access token: {e}")

# # -------------------------------
# # Optional Debug
# # -------------------------------
# if st.checkbox("Show Access Token (debug)"):
#     st.code(st.session_state.access_token or "No token yet")

######################## 3rd code ###########################################################################################3
# ==============================================
# 🔐 FYERS LOGIN PAGE with Robust Token Save + Auto-Refresh
# ==============================================
import streamlit as st
import os
import time
import json
import pyotp as tp
from urllib.parse import urlparse, parse_qs
from fyers_apiv3 import fyersModel
import credentials as crs

# -------------------------------
# Streamlit Page Config
# -------------------------------
st.set_page_config(page_title="🔐 Fyers Login Dashboard", layout="wide")
st.title("🔐 Fyers Login — Get Your Access Token")

# -------------------------------
# Session State Setup
# -------------------------------
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "auth_code" not in st.session_state:
    st.session_state.auth_code = None
if "auth_url" not in st.session_state:
    st.session_state.auth_url = None
if "totp" not in st.session_state:
    st.session_state.totp = None
if "token_data" not in st.session_state:
    st.session_state.token_data = None  # will hold parsed access.json data

# -------------------------------
# Fyers Credentials
# -------------------------------
client_id = crs.client_id
secret_key = crs.secret_key
redirect_uri = crs.redirect_uri
response_type = "code"

# -------------------------------
# Token storage paths
# -------------------------------
ACCESS_JSON = "access.json"

# -------------------------------
# Helpers
# -------------------------------
def save_token_data(token_response: dict):
    """
    Save full token response + expiry timestamp to access.json
    token_response: expected to include at least 'access_token' and optionally 'refresh_token' and 'expires_in' (seconds)
    """
    data = token_response.copy()
    now = int(time.time())
    expires_in = None
    if "expires_in" in token_response:
        try:
            expires_in = int(token_response.get("expires_in"))
        except Exception:
            expires_in = None

    # compute absolute expiry if possible
    if expires_in:
        data["_saved_at"] = now
        data["_expires_at"] = now + expires_in
    else:
        # fallback - set _expires_at to now + 3600 (1 hour) as a safe default if not provided
        data["_saved_at"] = now
        data["_expires_at"] = now + 3600

    # write to file
    with open(ACCESS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    st.session_state.token_data = data
    st.success("✅ Token data saved to access.json")

def load_token_data():
    if os.path.exists(ACCESS_JSON):
        try:
            with open(ACCESS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            st.session_state.token_data = data
            return data
        except Exception as e:
            st.error(f"Failed to read {ACCESS_JSON}: {e}")
            return None
    return None

def is_token_expired(token_data: dict) -> bool:
    if not token_data:
        return True
    expires_at = token_data.get("_expires_at")
    if not expires_at:
        return True
    return int(time.time()) >= int(expires_at)

def is_token_valid(token: str) -> bool:
    """
    Validate the access token by calling a cheap API endpoint.
    Returns True if valid, False otherwise.
    """
    if not token:
        return False
    try:
        fyers = fyersModel.FyersModel(client_id=client_id, token=token, log_path="log/")
        data = fyers.quotes({"symbols": "NSE:SBIN-EQ"})
        # the fyers quotes response includes key 'd' when successful
        return isinstance(data, dict) and "d" in data
    except Exception:
        return False

def attempt_refresh(refresh_token: str) -> dict:
    """
    Try to refresh using grant_type=refresh_token (if SDK uses that).
    Returns the new token_response dict on success, or {} on failure.
    """
    try:
        session = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=redirect_uri,
            response_type=response_type,
            grant_type="refresh_token"
        )
        # set_token for refresh flow — SDK convention may accept refresh token here
        session.set_token(refresh_token)
        new_tokens = session.generate_token()
        return new_tokens or {}
    except Exception as e:
        st.warning(f"Refresh attempt failed: {e}")
        return {}

# -------------------------------
# On load: try to read existing token data
# -------------------------------
load_token_data()

# -------------------------------------------------------
# UI: Manual Check Access Token Button (main troubleshooting)
# -------------------------------------------------------
st.markdown("---")
st.subheader("🔍 Access Token Validation & Debug")

if st.button("✅ Check Access Token"):
    data = st.session_state.token_data or load_token_data()
    if not data:
        st.info("No saved token data found. Please login to generate a new token.")
    else:
        # show saved summary for debugging
        st.write("Saved token summary:")
        st.json({
            "access_token_present": "access_token" in data,
            "refresh_token_present": "refresh_token" in data,
            "_saved_at": data.get("_saved_at"),
            "_expires_at": data.get("_expires_at"),
            "is_expired": is_token_expired(data)
        })

        if not data.get("access_token"):
            st.error("Saved token file does not contain 'access_token'. You may have saved the wrong value.")
        else:
            if not is_token_expired(data):
                # try direct validation
                if is_token_valid(data["access_token"]):
                    st.success("🎉 Access token is valid (and not expired). Dashboard can load.")
                    st.session_state.access_token = data["access_token"]
                    st.experimental_rerun()
                else:
                    st.error("❌ Access token seems invalid (API call failed).")
                    # try refresh if refresh_token exists
                    if data.get("refresh_token"):
                        st.info("Attempting to refresh using saved refresh_token...")
                        new_tokens = attempt_refresh(data["refresh_token"])
                        if new_tokens.get("access_token"):
                            save_token_data(new_tokens)
                            st.success("🔁 Refresh successful — new access token saved.")
                            st.session_state.access_token = new_tokens["access_token"]
                            st.experimental_rerun()
                        else:
                            st.error("Refresh failed. Please perform full login again.")
                    else:
                        st.info("No refresh_token found — please perform full login to generate a new token.")
            else:
                st.warning("⏳ Saved token has expired according to its expiry timestamp.")
                # attempt refresh if refresh token exists
                if data.get("refresh_token"):
                    st.info("Attempting to refresh using saved refresh_token...")
                    new_tokens = attempt_refresh(data["refresh_token"])
                    if new_tokens.get("access_token"):
                        save_token_data(new_tokens)
                        st.success("🔁 Refresh successful — new access token saved.")
                        st.session_state.access_token = new_tokens["access_token"]
                        st.experimental_rerun()
                    else:
                        st.error("Refresh failed. Please perform full login again.")
                else:
                    st.info("No refresh_token found — please perform full login to generate a new token.")

# =========================================================
# 🚀 IF TOKEN IS VALID → LOAD DASHBOARD DIRECTLY
# =========================================================
if st.session_state.access_token:
    st.subheader("✅ Login Successful")
    st.write("Access Token ready — you can now use your dashboard or scanner.")
    if st.button("🔁 Re-check Token Validity"):
        if is_token_valid(st.session_state.access_token):
            st.success("✅ Token still valid.")
        else:
            st.error("❌ Token expired or invalid — please log in again.")
            st.session_state.access_token = None
            st.experimental_rerun()

    try:
        fyers = fyersModel.FyersModel(
            client_id=client_id,
            token=st.session_state.access_token,
            log_path="log/"
        )
        data = fyers.quotes({"symbols": "NSE:SBIN-EQ"})
        if "d" in data:
            cmp = data["d"][0]["v"]["lp"]
            st.success(f"✅ Fyers Connected Successfully! SBIN CMP: ₹{cmp}")
        else:
            st.info("Fyers connection successful, but quote data not returned.")
    except Exception as e:
        st.warning(f"Token valid but test request failed: {e}")

    # ---- Load your main dashboard ----
    st.markdown("---")
    st.subheader("📊 Proceed to Dashboard Below")
    exec(open("dashboard_main.py", encoding="utf-8").read())
    st.stop()

# =========================================================
# 🧭 IF TOKEN INVALID / NOT PRESENT → SHOW LOGIN PROCESS
# =========================================================

# -------------------------------
# Sidebar Section for TOTP
# -------------------------------
st.sidebar.header("🔢 Generate TOTP for Fyers Login")

totp_key = "WS27N6R2XVJI3WW6SKPTZSK3RC7DF24C"

if st.sidebar.button("Generate TOTP Code"):
    try:
        code = tp.TOTP(totp_key).now()
        st.sidebar.success(f"✅ Your TOTP: **{code}**")
        st.sidebar.info("Enter this TOTP on the Fyers login page.")
        st.session_state.totp = code
    except Exception as e:
        st.sidebar.error(f"Failed to generate TOTP: {e}")

# -------------------------------
# Main Instructions
# -------------------------------
st.markdown(
    """
    ### 🧭 Instructions
    1. Click **Open Fyers Login Page** below — Fyers login page will open in a new browser tab.
    2. Enter your **mobile number** and then use the **TOTP code** from the sidebar.
    3. Enter your **PIN** and finish login on Fyers.
    4. After redirect, **copy the full redirected URL** from your browser.
    5. Paste the URL in the box below to generate your **access token** automatically.
    """
)

# -------------------------------
# Step 1: Generate Auth URL (Open in New Tab)
# -------------------------------
if st.button("➡ Open Fyers Login Page"):
    try:
        session = fyersModel.SessionModel(
            client_id=client_id,
            secret_key=secret_key,
            redirect_uri=redirect_uri,
            response_type=response_type
        )
        response = session.generate_authcode()
        st.session_state.auth_url = response

        st.markdown(
            f'''
            <a href="{response}" target="_blank" style="text-decoration:none;">
                <button style="
                    background-color:#4CAF50;
                    color:white;
                    padding:10px 20px;
                    border:none;
                    border-radius:5px;
                    cursor:pointer;">
                    👉 Open Fyers Login Page
                </button>
            </a>
            ''',
            unsafe_allow_html=True
        )

        st.info("Fyers login page will open in a new tab. Use the TOTP shown in the sidebar to log in.")
        st.markdown(f"Or manually open: [🔗 {response}]({response})", unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Error generating Fyers login URL: {e}")

# -------------------------------
# Step 2: Paste Redirected URL (Robust parsing using urllib.parse)
# -------------------------------
redirected_url = st.text_input("Paste the redirected URL here after logging in on Fyers:")

if redirected_url:
    try:
        # parse query parameters robustly
        parsed = urlparse(redirected_url)
        qs = parse_qs(parsed.query)
        # Fyers may return 'auth_code' or 'authCode' depending on SDK/version; try both
        auth_code = None
        if "auth_code" in qs:
            auth_code = qs["auth_code"][0]
        elif "authCode" in qs:
            auth_code = qs["authCode"][0]
        elif "code" in qs:
            auth_code = qs["code"][0]
        else:
            # sometimes the auth code is present in fragment (after #)
            frag_qs = parse_qs(parsed.fragment)
            if "auth_code" in frag_qs:
                auth_code = frag_qs["auth_code"][0]

        if not auth_code:
            raise ValueError("Could not find auth code in the provided URL. Paste the full redirected URL (including query parameters).")

        st.session_state.auth_code = auth_code
        st.success("✅ Auth code extracted successfully.")
    except Exception as e:
        st.error("❌ Could not extract auth_code. Please paste the full URL (copy the address bar after redirect).")
        st.write(e)

# -------------------------------
# Step 3: Generate Access Token (and save full response)
# -------------------------------
if st.session_state.auth_code and (not st.session_state.token_data or not st.session_state.token_data.get("access_token")):
    if st.button("🔑 Generate Access Token"):
        try:
            grant_type = "authorization_code"
            session2 = fyersModel.SessionModel(
                client_id=client_id,
                secret_key=secret_key,
                redirect_uri=redirect_uri,
                response_type=response_type,
                grant_type=grant_type
            )
            session2.set_token(st.session_state.auth_code)
            token_response = session2.generate_token()

            if not token_response:
                st.error("Failed to generate token: empty response from SDK")
            elif "access_token" in token_response:
                # Save full response (includes refresh_token & expires_in if SDK provides)
                save_token_data(token_response)
                st.session_state.access_token = token_response["access_token"]
                st.success("✅ Access token generated successfully and saved to access.json!")
                st.experimental_rerun()
            else:
                # show full response for debugging
                st.error("Failed to find 'access_token' in the token response. See the raw response below.")
                st.write(token_response)
        except Exception as e:
            st.error(f"Error while generating access token: {e}")

# -------------------------------
# Optional Debug UI
# -------------------------------
if st.checkbox("Show saved token file (debug)"):
    data = st.session_state.token_data or load_token_data()
    if data:
        st.json(data)
    else:
        st.write("No token file saved yet.")

if st.checkbox("Show Access Token (debug)"):
    data = st.session_state.token_data or load_token_data()
    if data and data.get("access_token"):
        st.code(data.get("access_token"))
    else:
        st.write("No access token available.")

