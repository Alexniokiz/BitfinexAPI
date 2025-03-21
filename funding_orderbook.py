import ccxt
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time
import requests
import asyncio
import aiohttp
import ssl
import certifi
import json
import uuid
from streamlit_cookies_manager import EncryptedCookieManager

# Set page config must be the first Streamlit command
st.set_page_config(page_title="Bitfinex fUSD Funding Order Book", layout="wide")

# Initialize cookie manager (it uses an encrypted cookie store)
cookie_manager = EncryptedCookieManager(
    prefix="bitfinex_",
    password="7x!A9yZ#mP2$qR5v"  # Added secure password
)
if not cookie_manager.ready():
    st.stop()  # Wait until the cookie manager is ready

# Initialize session state for alerts if not exists.
if 'alerts' not in st.session_state:
    alerts_cookie = cookie_manager.get("alerts")
    if alerts_cookie:
        try:
            st.session_state.alerts = json.loads(alerts_cookie)
        except Exception as e:
            st.session_state.alerts = {}
    else:
        st.session_state.alerts = {}

if 'triggered_alerts' not in st.session_state:
    st.session_state.triggered_alerts = set()

def format_amount(amount):
    """Format amount to K/M notation like Bitfinex"""
    abs_amount = abs(float(amount))
    if abs_amount >= 1_000_000:
        return f"{abs_amount/1_000_000:.3f}M"
    elif abs_amount >= 1_000:
        return f"{abs_amount/1_000:.3f}K" 
    return f"{abs_amount:.3f}"

def format_period_range(periods):
    """Format period range from list of periods"""
    if not periods:
        return ""
    periods = sorted(list(set(periods)))  # Remove duplicates and sort
    if len(periods) == 1:
        return str(periods[0])
    return f"{min(periods)}-{max(periods)}"

def fetch_period_data_sync(period):
    """Fetch funding orderbook data for a specific period synchronously"""
    url = f"https://api-pub.bitfinex.com/v2/book/fUSD/P{period}?len=250"
    headers = {"accept": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except Exception as e:
        st.error(f"Error fetching P{period}: {str(e)}")
        return []

def fetch_all_periods_sync():
    """Fetch funding orderbook data for all periods (P0-P4) synchronously"""
    results = []
    result = fetch_period_data_sync(0)
    results.append(result)
    return results

@st.cache_data(ttl=5000)
def fetch_funding_orderbook(rate_precision=3):
    try:
        # Fetch data from all periods
        all_data = fetch_all_periods_sync()
        
        # Combine all orders
        orders = []
        for data in all_data:
            if not data or not isinstance(data, list):
                continue
            for order_data in data:
                try:
                    rate = float(order_data[0]) * 100  # Convert to percentage
                    period = int(order_data[1])
                    amount = float(order_data[3])  # Keep original sign
                    num_orders = float(order_data[2])
                    
                    order = {
                        'Rate': rate,
                        'Amount': amount,
                        'Period': period,
                        'Orders': num_orders
                    }
                    orders.append(order)
                except (ValueError, TypeError, IndexError) as e:
                    st.error(f"Error parsing order data: {e}")
                    continue
        
        if not orders:
            st.error("No valid orders found in data")
            return None, None
            
        df = pd.DataFrame(orders)
        # Agglomerate similar rates by rounding according to rate_precision
        df['Rate'] = df['Rate'].round(rate_precision)
        
        # Group by Rate and aggregate data
        df_grouped = df.groupby('Rate').agg({
            'Amount': 'sum',
            'Orders': 'sum',
            'Period': lambda x: list(x)  # Collect all periods
        }).reset_index()
        df_grouped = df_grouped.rename(columns={'Period': 'Periods'})
        
        # Split into bids and asks based on Amount sign
        bids_df = df_grouped[df_grouped['Amount'] > 0].copy()
        asks_df = df_grouped[df_grouped['Amount'] < 0].copy()
        
        # Sort appropriately (bids ascending, asks descending by rate)
        bids_df = bids_df.sort_values('Rate', ascending=True)
        asks_df = asks_df.sort_values('Rate', ascending=False)
        
        # Calculate cumulative amounts
        bids_df['Cumulative'] = bids_df['Amount'].cumsum()
        asks_df['Cumulative'] = asks_df['Amount'].abs().cumsum()
        
        return bids_df, asks_df
    except Exception as e:
        st.error(f"Error fetching order book: {str(e)}")
        return None, None

def create_orderbook_display(df, is_bids=True):
    """Create a styled DataFrame with a background gradient starting from the inner side of the row"""
    if df is None or df.empty:
        return None

    max_cumulative = max(df['Cumulative'].max(), 1)
    display_df = df.copy()
    display_df['Rate'] = display_df['Rate'].map(lambda x: f"{x:.6f}")
    display_df['Amount'] = display_df['Amount'].abs().map(format_amount)
    display_df['Period'] = display_df['Periods'].map(format_period_range)
    display_df['Total'] = display_df['Cumulative'].map(format_amount)

    if is_bids:
        columns = ['Period', 'Amount', 'Total', 'Rate']
        display_names = ['PER', 'AMOUNT', 'TOTAL', 'RATE']
    else:
        columns = ['Rate', 'Total', 'Amount', 'Period']
        display_names = ['RATE', 'TOTAL', 'AMOUNT', 'PER']
    
    col_mapping = dict(zip(columns, display_names))
    final_df = display_df[columns].rename(columns=col_mapping)
    color = "#ff3b69" if is_bids else "#26a69a"
    
    html = '<table class="dataframe"><thead><tr>'
    for col in final_df.columns:
        html += f'<th>{col}</th>'
    html += '</tr></thead><tbody>'
    for _, row in display_df.iterrows():
        fill_percent = (row['Cumulative'] / max_cumulative) * 100
        if is_bids:
            gradient = f"linear-gradient(to left, {color} {fill_percent}%, transparent {fill_percent}%)"
        else:
            gradient = f"linear-gradient(to right, {color} {fill_percent}%, transparent {fill_percent}%)"
        html += f'<tr style="background: {gradient};">'
        for col in columns:
            html += f'<td>{row[col]}</td>'
        html += '</tr>'
    html += '</tbody></table>'
    return html

def main():
    # Custom CSS and sound script (unchanged)
    st.markdown("""
        <style>
        .stApp { background-color: #1b262d; }
        div[data-testid="stToolbar"] { display: none; }
        .stMarkdown { color: #7f8c8d; font-family: monospace; }
        .dataframe { font-family: "Courier New", Courier, monospace !important; font-size: 13px !important; width: 100% !important; border-collapse: collapse !important; border: none !important; position: relative !important; }
        .dataframe th { background-color: #1b262d !important; color: #7f8c8d !important; font-weight: normal !important; padding: 8px 12px !important; border: none !important; text-align: right !important; position: relative !important; z-index: 2 !important; }
        .dataframe td { background-color: transparent !important; color: #ffffff !important; padding: 8px 12px !important; border: none !important; text-align: right !important; white-space: nowrap !important; position: relative !important; height: 24px !important; z-index: 2 !important; }
        .dataframe tr { position: relative !important; height: 24px !important; }
        thead tr { border-bottom: 1px solid #2c3940 !important; }
        tbody tr:hover { background-color: #232f36 !important; }
        div[data-testid="stHeader"] { display: none; }
        section[data-testid="stSidebar"] { display: none; }
        div.stTitle { display: none; }
        div[data-testid="stMetricValue"] { color: #ffffff; font-family: monospace; }
        div[data-testid="stMetricLabel"] { color: #7f8c8d; }
        .alert { background-color: #ff3b69; color: white; padding: 10px; border-radius: 4px; margin: 10px 0; animation: blink 1s infinite; position: relative; padding-right: 30px; }
        .alert-close { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); cursor: pointer; color: white; font-weight: bold; text-decoration: none; }
        .alert-close:hover { color: #ddd; }
        .alert-container { max-height: 200px; overflow-y: auto; margin-bottom: 10px; }
        @keyframes blink { 50% { opacity: 0.5; } }
        </style>
        <audio id="alert-sound" preload="auto">
            <source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
        <script>
        function playAlertSound() {
            const audio = document.getElementById('alert-sound');
            audio.currentTime = 0;
            audio.volume = 1.0;
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise.then(_ => { console.log('Alert sound played successfully'); })
                .catch(error => { console.error('Error playing alert sound:', error); });
            }
        }
        function isSoundEnabled() { return localStorage.getItem('bitfinex_sound_enabled') !== 'false'; }
        function toggleSound(enabled) { localStorage.setItem('bitfinex_sound_enabled', enabled); }
        </script>
    """, unsafe_allow_html=True)
    
    # Add slider to control rate precision
    rate_precision = st.slider("Rate Precision (decimals)", min_value=0, max_value=6, value=3, step=1)
    
    # Alert settings
    with st.expander("Alert Settings"):
        col_rate, col_amount, col_name = st.columns(3)
        with col_rate:
            alert_rate = st.number_input("Alert Rate (%)", min_value=0.0, max_value=100.0, value=0.05, step=0.001, format="%.3f")
        with col_amount:
            alert_amount = st.number_input("Target Amount (M$)", min_value=0.0, max_value=1000.0, value=3.0, step=0.1, format="%.1f")
        with col_name:
            alert_name = st.text_input("Alert Name (optional)", value="")
        col_enabled, col_add = st.columns([1, 4])
        with col_enabled:
            alert_enabled = st.checkbox("Enable Alerts", value=True)
        with col_add:
            if st.button("Add Alert"):
                if alert_name in st.session_state.alerts:
                    st.warning(f"Alert with name '{alert_name}' already exists!")
                else:
                    alert_id = str(uuid.uuid4())
                    new_alert = {
                        'name': alert_name or f"Alert {len(st.session_state.alerts) + 1}",
                        'rate': alert_rate,
                        'amount': alert_amount
                    }
                    st.session_state.alerts[alert_id] = new_alert
                    cookie_manager["alerts"] = json.dumps(st.session_state.alerts)
                    cookie_manager.save()
                    st.success("Alert added successfully!")
        sound_enabled = st.checkbox("Enable Sound", value=True, key="sound_enabled")
        st.markdown(f"""<script>toggleSound({str(sound_enabled).lower()});</script>""", unsafe_allow_html=True)
    
    # Display active alerts
    if st.session_state.alerts:
        st.markdown("### Active Alerts")
        for alert_id, alert in list(st.session_state.alerts.items()):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"**{alert['name']}**: {alert['rate']}% @ {alert['amount']}M$")
            with col3:
                if st.button("Delete", key=f"delete_{alert_id}"):
                    del st.session_state.alerts[alert_id]
                    cookie_manager["alerts"] = json.dumps(st.session_state.alerts)
                    cookie_manager.save()
                    st.experimental_rerun()
    
    col_refresh = st.columns([1, 8])[0]
    with col_refresh:
        auto_refresh = st.checkbox("Auto-refresh", value=True)
    
    alert_placeholder = st.empty()
    time_placeholder = st.empty()
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<p style="color: #7f8c8d; margin-bottom: 5px; font-size: 14px;">BIDS</p>', unsafe_allow_html=True)
        bids_placeholder = st.empty()
    with col2:
        st.markdown('<p style="color: #7f8c8d; margin-bottom: 5px; font-size: 14px;">ASKS</p>', unsafe_allow_html=True)
        asks_placeholder = st.empty()
    
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    bid_metric = stat_col1.empty()
    ask_metric = stat_col2.empty()
    spread_metric = stat_col3.empty()
    
    while True:
        # Use high-precision data (8 decimals) for alert checking
        bids_df_alert, asks_df_alert = fetch_funding_orderbook(rate_precision=8)
        # Use user-selected precision (from slider) for display
        bids_df_disp, asks_df_disp = fetch_funding_orderbook(rate_precision)
        
        if (bids_df_alert is not None and asks_df_alert is not None and
            bids_df_disp is not None and asks_df_disp is not None):
            time_placeholder.markdown(
                f'<p style="color: #7f8c8d; font-size: 12px; text-align: right;">Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>',
                unsafe_allow_html=True
            )
            
            # --- ALERT CHECKING: BIDS BELOW ALERT RATE (using high-precision data) ---
            if alert_enabled and st.session_state.alerts:
                alert_messages = []
                play_sound = False

                for alert_id, alert in st.session_state.alerts.items():
                    # Filter bids with rates strictly below the alert rate from high-precision data
                    good_bids = bids_df_alert[bids_df_alert['Rate'] < alert['rate']]
                    if good_bids.empty:
                        cumulative_bid = 0.0
                        effective_rate_bid = None
                    else:
                        cumulative_bid = good_bids['Amount'].sum() / 1_000_000  # in millions
                        effective_rate_bid = good_bids['Rate'].max()

                    progress_percent = min((cumulative_bid / alert['amount']) * 100, 100)
                    progress_html = f'''<div style="background: #aaa; width: 100%; border-radius: 5px; margin-top: 5px;">
                        <div style="background: #ff3b69; width: {progress_percent:.1f}%; height: 10px; border-radius: 5px;"></div>
                    </div>'''

                    if cumulative_bid < alert['amount']:
                        alarm_message = (f"🔔 {alert['name']}: Only {cumulative_bid:.1f}M$ available at bid rates below "
                                         f"{alert['rate']:.3f}% (target: {alert['amount']:.1f}M$)")
                        if effective_rate_bid is not None:
                            alarm_message += f" (Best bid: {effective_rate_bid:.3f}%)"
                        message = alarm_message + progress_html

                        alert_key = f"{alert_id}_{cumulative_bid:.1f}"
                        if alert_key not in st.session_state.triggered_alerts:
                            play_sound = True
                            st.session_state.triggered_alerts.add(alert_key)
                        alert_messages.append({'id': alert_key, 'message': message})
                    else:
                        message = (f"✅ {alert['name']}: Sufficient liquidity available: {cumulative_bid:.1f}M$ at bid rates below "
                                   f"{alert['rate']:.3f}% (target: {alert['amount']:.1f}M$)") + progress_html
                        alert_key = f"{alert_id}_complete"
                        alert_messages.append({'id': alert_key, 'message': message})

                if alert_messages:
                    alert_html = '<div class="alert-container">'
                    for alert in alert_messages:
                        alert_html += f'''
                            <div class="alert" id="{alert['id']}">
                                {alert['message']}
                                <a href="#" class="alert-close" onclick="this.parentElement.style.display='none'; return false;">×</a>
                            </div>
                        '''
                    alert_html += '</div>'
                    if play_sound:
                        alert_html += '''
                            <script>
                            if (isSoundEnabled()) { playAlertSound(); }
                            </script>
                        '''
                    alert_placeholder.markdown(alert_html, unsafe_allow_html=True)
                else:
                    alert_placeholder.empty()
            
            # Use the display data (user-selected precision) for order book visualization
            bids_display = create_orderbook_display(bids_df_disp, is_bids=True)
            asks_display = create_orderbook_display(asks_df_disp, is_bids=False)
            
            if bids_display is not None:
                bids_placeholder.write(bids_display, unsafe_allow_html=True)
            if asks_display is not None:
                asks_placeholder.write(asks_display, unsafe_allow_html=True)
            
            bid_metric.metric("Best Bid Rate", f"{bids_df_disp['Rate'].max():.6f}%")
            ask_metric.metric("Best Ask Rate", f"{asks_df_disp['Rate'].min():.6f}%")
            spread = asks_df_disp['Rate'].min() - bids_df_disp['Rate'].max()
            spread_metric.metric("Spread", f"{spread:.6f}%")
        
        if not auto_refresh:
            break
        time.sleep(5)


if __name__ == "__main__":
    main()
