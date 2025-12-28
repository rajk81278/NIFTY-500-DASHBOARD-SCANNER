

# ==============================================
# 🔐 FYERS LOGIN PAGE with Daily Auto-Login + Manual Token Check
# ==============================================
import streamlit as st
import webbrowser
import time
import os
import pyotp as tp
from fyers_apiv3 import fyersModel
import credentials as crs

import os

# Force-create log directory at runtime (works in cloud + local)
os.makedirs("log", exist_ok=True)


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

# -------------------------------
# Fyers Credentials
# -------------------------------
client_id = crs.client_id
secret_key = crs.secret_key
redirect_uri = crs.redirect_uri
response_type = "code"
state = "sample_state"

# -------------------------------
# Function: Check if access token is valid
# -------------------------------
def is_token_valid(token):
    try:
        fyers = fyersModel.FyersModel(client_id=client_id, token=token, log_path="log/")
        data = fyers.quotes({"symbols": "NSE:SBIN-EQ"})
        if "d" in data:
            return True
        else:
            return False
    except Exception:
        return False


# -------------------------------
# Step 0: Try using saved token first
# -------------------------------
access_token_path = "access.txt"
saved_token = None

if os.path.exists(access_token_path):
    with open(access_token_path, "r") as f:
        saved_token = f.read().strip()

if saved_token and is_token_valid(saved_token):
    st.session_state.access_token = saved_token
else:
    st.info("⚠️ No valid token found — please log in or check below.")

# =========================================================
# 🔍 Manual Check Access Token Button
# =========================================================
st.markdown("---")
st.subheader("🔍 Access Token Validation")

if st.button("✅ Check Access Token"):
    if os.path.exists(access_token_path):
        with open(access_token_path, "r") as f:
            saved_token = f.read().strip()

        if saved_token and is_token_valid(saved_token):
            st.session_state.access_token = saved_token
            st.success("🎉 Access token is valid — Fyers connected successfully!")
            # st.experimental_rerun()
            st.rerun()

        else:
            st.warning("⚠️ Token invalid or expired — please log in again.")
    else:
        st.info("No saved access token found — please log in to generate a new one.")

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
            st.error("❌ Token expired — please log in again.")
            st.session_state.access_token = None
            # st.experimental_rerun()
            st.rerun()


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
# 🧭 IF TOKEN INVALID → SHOW LOGIN PROCESS
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
# Step 2: Paste Redirected URL
# -------------------------------
redirected_url = st.text_input("Paste the redirected URL here after logging in on Fyers:")

if redirected_url:
    try:
        auth_code = redirected_url[redirected_url.index("auth_code=") + 10: redirected_url.index("&state")]
        st.session_state.auth_code = auth_code
        st.success("✅ Auth code extracted successfully.")
    except Exception as e:
        st.error("❌ Could not extract auth_code. Please paste the full URL.")
        st.write(e)

# -------------------------------
# Step 3: Generate Access Token
# -------------------------------
if st.session_state.auth_code and st.session_state.access_token is None:
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

            if "access_token" in token_response:
                access_token = token_response["access_token"]
                with open("access.txt", "w") as f:
                    f.write(access_token)
                st.session_state.access_token = access_token
                st.success("✅ Access token generated successfully and saved to access.txt!")
                st.rerun()  # Reload to auto-load dashboard
            else:
                st.error(f"Failed to generate access token: {token_response}")
        except Exception as e:
            st.error(f"Error while generating access token: {e}")

# -------------------------------
# Optional Debug
# -------------------------------
if st.checkbox("Show Access Token (debug)"):
    st.code(st.session_state.access_token or "No token yet")



