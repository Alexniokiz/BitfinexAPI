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

# Initialize session state for alerts if not exists
if 'alerts' not in st.session_state:
    st.session_state.alerts = {}  # Dictionary to store active alerts
if 'triggered_alerts' not in st.session_state:
    st.session_state.triggered_alerts = set()  # Set to track triggered alerts

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

def create_orderbook_display(df, is_bids=True):
    """Create a styled DataFrame with a background gradient starting from the inner side of the row"""
    if df is None or df.empty:
        return None

    # Calculate the maximum cumulative value for scaling (avoid division by zero)
    max_cumulative = max(df['Cumulative'].max(), 1)

    # Create a copy for display and format columns
    display_df = df.copy()
    display_df['Rate'] = display_df['Rate'].map(lambda x: f"{x:.6f}")
    display_df['Amount'] = display_df['Amount'].abs().map(format_amount)
    display_df['Period'] = display_df['Periods'].map(format_period_range)
    display_df['Total'] = display_df['Cumulative'].map(format_amount)

    # Set column order and display names based on order type
    if is_bids:
        columns = ['Period', 'Amount', 'Total', 'Rate']
        display_names = ['PER', 'AMOUNT', 'TOTAL', 'RATE']
    else:
        columns = ['Rate', 'Total', 'Amount', 'Period']
        display_names = ['RATE', 'TOTAL', 'AMOUNT', 'PER']
    
    # Map the columns to new display names
    col_mapping = dict(zip(columns, display_names))
    final_df = display_df[columns].rename(columns=col_mapping)

    # Choose color (red for bids, green for asks)
    color = "#ff3b69" if is_bids else "#26a69a"

    # Start building the HTML table
    html = '<table class="dataframe">'
    # Header
    html += '<thead><tr>'
    for col in final_df.columns:
        html += f'<th>{col}</th>'
    html += '</tr></thead>'

    # Body: for each row, compute the cumulative percentage and apply a background gradient
    html += '<tbody>'
    for _, row in display_df.iterrows():
        # Compute fill percentage relative to the maximum cumulative value
        fill_percent = (row['Cumulative'] / max_cumulative) * 100

        # For bids, the gradient starts from the right (inside) and for asks from the left (inside)
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


async def fetch_period_data(session, period):
    """Fetch funding orderbook data for a specific period"""
    url = f"https://api-pub.bitfinex.com/v2/book/fUSD/P{period}?len=250"
    headers = {"accept": "application/json"}
    try:
        async with session.get(url, headers=headers) as response:
            return await response.json()
    except Exception as e:
        st.error(f"Error fetching P{period}: {str(e)}")
        return []

async def fetch_all_periods():
    """Fetch funding orderbook data for all periods (P0-P4)"""
    # Create SSL context with certifi certificates
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    conn = aiohttp.TCPConnector(ssl=ssl_context)
    
    async with aiohttp.ClientSession(connector=conn) as session:
        tasks = [fetch_period_data(session, i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        return results

def fetch_funding_orderbook():
    try:
        # Fetch data from all periods
        all_data = asyncio.run(fetch_all_periods())
        
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
        
        # Check if we parsed any valid orders
        if not orders:
            st.error("No valid orders found in data")
            return None, None
            
        # Convert to DataFrame
        df = pd.DataFrame(orders)
        
        # Group by Rate and collect all periods and sum amounts
        df_grouped = df.groupby('Rate').agg({
            'Amount': 'sum',
            'Orders': 'sum',
            'Period': lambda x: list(x)  # Collect all periods
        }).reset_index()
        
        # Rename Period column to Periods for clarity
        df_grouped = df_grouped.rename(columns={'Period': 'Periods'})
        
        # Split into bids and asks based on Amount sign
        bids_df = df_grouped[df_grouped['Amount'] > 0].copy()
        asks_df = df_grouped[df_grouped['Amount'] < 0].copy()
        
        # Sort appropriately (bids descending, asks ascending by rate)
        bids_df = bids_df.sort_values('Rate', ascending=True)
        asks_df = asks_df.sort_values('Rate', ascending=False)
        
        # Calculate cumulative amounts
        bids_df['Cumulative'] = bids_df['Amount'].cumsum()
        asks_df['Cumulative'] = asks_df['Amount'].abs().cumsum()
        
        return bids_df, asks_df
    except Exception as e:
        st.error(f"Error fetching order book: {str(e)}")
        return None, None

def main():
    st.set_page_config(page_title="Bitfinex fUSD Funding Order Book", layout="wide")
    
    # Custom CSS for Bitfinex-like styling
    st.markdown("""
        <style>
        .stApp {
            background-color: #1b262d;
        }
        div[data-testid="stToolbar"] {
            display: none;
        }
        .stMarkdown {
            color: #7f8c8d;
            font-family: monospace;
        }
        .dataframe {
            font-family: "Courier New", Courier, monospace !important;
            font-size: 13px !important;
            width: 100% !important;
            border-collapse: collapse !important;
            border: none !important;
            position: relative !important;
        }
        .dataframe th {
            background-color: #1b262d !important;
            color: #7f8c8d !important;
            font-weight: normal !important;
            padding: 8px 12px !important;
            border: none !important;
            text-align: right !important;
            position: relative !important;
            z-index: 2 !important;
        }
        .dataframe td {
            background-color: transparent !important;
            color: #ffffff !important;
            padding: 8px 12px !important;
            border: none !important;
            text-align: right !important;
            white-space: nowrap !important;
            position: relative !important;
            height: 24px !important;
            z-index: 2 !important;
        }
        .dataframe tr {
            position: relative !important;
            height: 24px !important;
        }
        thead tr {
            border-bottom: 1px solid #2c3940 !important;
        }
        tbody tr:hover {
            background-color: #232f36 !important;
        }
        div[data-testid="stHeader"] {
            display: none;
        }
        section[data-testid="stSidebar"] {
            display: none;
        }
        div.stTitle {
            display: none;
        }
        div[data-testid="stMetricValue"] {
            color: #ffffff;
            font-family: monospace;
        }
        div[data-testid="stMetricLabel"] {
            color: #7f8c8d;
        }
        .alert {
            background-color: #ff3b69;
            color: white;
            padding: 10px;
            border-radius: 4px;
            margin: 10px 0;
            animation: blink 1s infinite;
            position: relative;
            padding-right: 30px;
        }
        .alert-close {
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            cursor: pointer;
            color: white;
            font-weight: bold;
            text-decoration: none;
        }
        .alert-close:hover {
            color: #ddd;
        }
        .alert-container {
            max-height: 200px;
            overflow-y: auto;
            margin-bottom: 10px;
        }
        @keyframes blink {
            50% { opacity: 0.5; }
        }
        </style>
        
        <!-- Add sound element -->
        <audio id="alert-sound" preload="auto">
            <source src="data:audio/mpeg;base64,//uQxAAAAAAAAAAAAAAAAAAAAAAASW5mbwAAAA8AAAADAAAGhgBVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVWqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqr///////////////////////////////////////////8AAAA5TEFNRTMuOTlyAc0AAAAAAAAAABSAJAOkQgAAgAAABobXZzfKAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//sQxAADwAABpAAAACAAADSAAAAETEFNRTMuOTkuNVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVU=" type="audio/mpeg">
        </audio>
        
        <script>
        function playAlertSound() {
            document.getElementById('alert-sound').play();
        }
        </script>
    """, unsafe_allow_html=True)
    
    # Add alert settings in a collapsible section
    with st.expander("Alert Settings"):
        col_rate, col_amount, col_name = st.columns(3)
        with col_rate:
            alert_rate = st.number_input("Alert Rate (%)", 
                                       min_value=0.0, 
                                       max_value=100.0, 
                                       value=0.2, 
                                       step=0.01,
                                       format="%.3f")
        with col_amount:
            alert_amount = st.number_input("Target Amount (M$)", 
                                         min_value=0.0, 
                                         max_value=1000.0, 
                                         value=5.0, 
                                         step=0.1,
                                         format="%.1f")
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
                    st.session_state.alerts[alert_id] = {
                        'name': alert_name or f"Alert {len(st.session_state.alerts) + 1}",
                        'rate': alert_rate,
                        'amount': alert_amount
                    }
                    st.success("Alert added successfully!")
    
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
                    st.rerun()
    
    # Add auto-refresh option with custom styling
    col_refresh = st.columns([1, 8])[0]
    with col_refresh:
        auto_refresh = st.checkbox("Auto-refresh", value=True)
    
    # Create placeholder containers
    alert_placeholder = st.empty()
    time_placeholder = st.empty()
    col1, col2 = st.columns(2)
    
    # Create placeholders for dataframes
    with col1:
        st.markdown('<p style="color: #7f8c8d; margin-bottom: 5px; font-size: 14px;">BIDS</p>', unsafe_allow_html=True)
        bids_placeholder = st.empty()
    
    with col2:
        st.markdown('<p style="color: #7f8c8d; margin-bottom: 5px; font-size: 14px;">ASKS</p>', unsafe_allow_html=True)
        asks_placeholder = st.empty()
    
    # Create placeholders for statistics
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    bid_metric = stat_col1.empty()
    ask_metric = stat_col2.empty()
    spread_metric = stat_col3.empty()
    
    while True:
        bids_df, asks_df = fetch_funding_orderbook()
        
        if bids_df is not None and asks_df is not None:
            # Update current time
            time_placeholder.markdown(
                f'<p style="color: #7f8c8d; font-size: 12px; text-align: right;">Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>',
                unsafe_allow_html=True
            )
            
            # Check for alerts if enabled and there are active alerts
            if alert_enabled and st.session_state.alerts:
                alert_messages = []
                play_sound = False
                
                # Check each alert
                for alert_id, alert in st.session_state.alerts.items():
                    # Check bids at or below the target rate
                    matching_bids = bids_df[bids_df['Rate'] <= alert['rate']]
                    if not matching_bids.empty:
                        # Get the total amount at this rate level
                        rate_index = bids_df['Rate'].le(alert['rate']).idxmax()
                        total_at_rate = bids_df.loc[rate_index, 'Cumulative'] / 1_000_000  # Convert to millions
                        
                        if total_at_rate >= alert['amount']:
                            alert_key = f"{alert_id}_{total_at_rate:.1f}"
                            if alert_key not in st.session_state.triggered_alerts:
                                play_sound = True
                                st.session_state.triggered_alerts.add(alert_key)
                            
                            alert_messages.append({
                                'id': alert_key,
                                'message': f"🔔 {alert['name']}: Total bid amount {total_at_rate:.1f}M$ at {alert['rate']:.3f}% or lower"
                            })
                
                # Display alerts with close buttons
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
                        alert_html += '<script>playAlertSound();</script>'
                    alert_placeholder.markdown(alert_html, unsafe_allow_html=True)
                else:
                    alert_placeholder.empty()
            
            # Create styled displays for bids and asks
            bids_display = create_orderbook_display(bids_df, is_bids=True)
            asks_display = create_orderbook_display(asks_df, is_bids=False)
            
            # Display the styled dataframes
            if bids_display is not None:
                bids_placeholder.write(bids_display, unsafe_allow_html=True)
            
            if asks_display is not None:
                asks_placeholder.write(asks_display, unsafe_allow_html=True)
            
            # Update statistics
            bid_metric.metric("Best Bid Rate", f"{bids_df['Rate'].max():.6f}%")
            ask_metric.metric("Best Ask Rate", f"{asks_df['Rate'].min():.6f}%")
            spread = asks_df['Rate'].min() - bids_df['Rate'].max()
            spread_metric.metric("Spread", f"{spread:.6f}%")
        
        if not auto_refresh:
            break
            
        time.sleep(5)

if __name__ == "__main__":
    main() 