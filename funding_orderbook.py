import ccxt
import streamlit as st
import pandas as pd
from datetime import datetime
import time
import requests

def fetch_funding_orderbook():
    try:
        # Fetch funding stats for fUSD from Bitfinex public API
        url = "https://api-pub.bitfinex.com/v2/book/fUSD/P0?len=25"
        headers = {"accept": "application/json"}
        response = requests.get(url, headers=headers)
        data = response.json()

        # Check if data is empty or not a list
        if not data or not isinstance(data, list):
            st.error("Invalid response from API")
            return None, None
    
        # Convert list of lists to DataFrame
        orders = []
        for order_data in data:
            # Each order is a list of [rate, period, amount, orders]
            try:
                rate = float(order_data[0]) * 100  # Convert to percentage
                period = int(order_data[1])
                amount = float(order_data[2])
                num_orders = float(order_data[3])
                
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
            st.error("No valid orders found in data. Raw data received: " + str(data[:20]))
            return None, None
            
        # Convert to DataFrame
        df = pd.DataFrame(orders)
        
        # Split into bids and asks
        bids_df = df[df['Amount'] > 0].copy()
        asks_df = df[df['Amount'] < 0].copy()
        
        # Make amounts positive for asks
        asks_df['Amount'] = asks_df['Amount'].abs()
        
        # Calculate cumulative amounts
        bids_df['Cumulative'] = bids_df['Amount'].cumsum()
        asks_df['Cumulative'] = asks_df['Amount'].cumsum()
        
        return bids_df, asks_df
    except Exception as e:
        st.error(f"Error fetching order book: {str(e)}")
        return None, None

def main():
    st.set_page_config(page_title="Bitfinex fUSD Funding Order Book", layout="wide")
    st.title("Bitfinex fUSD Funding Order Book")
    
    # Add auto-refresh option
    auto_refresh = st.checkbox("Auto-refresh every 5 seconds", value=True)
    
    # Create placeholder containers
    time_placeholder = st.empty()
    col1, col2 = st.columns(2)
    
    # Create placeholders for dataframes
    with col1:
        st.subheader("Bids (Buy Orders)")
        bids_placeholder = st.empty()
    
    with col2:
        st.subheader("Asks (Sell Orders)")
        asks_placeholder = st.empty()
    
    # Create placeholders for statistics
    st.subheader("Order Book Statistics")
    stat_col1, stat_col2, stat_col3 = st.columns(3)
    bid_metric = stat_col1.empty()
    ask_metric = stat_col2.empty()
    spread_metric = stat_col3.empty()
    
    while True:
        bids_df, asks_df = fetch_funding_orderbook()
        
        if bids_df is not None and asks_df is not None:
            # Update current time
            time_placeholder.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Update the order book data
            bids_placeholder.dataframe(bids_df.style.format({
                'Rate': '{:.4f}',
                'Amount': '{:.2f}',
                'Period': '{:d}',
                'Orders': '{:.2f}',
                'Cumulative': '{:.2f}'
            }))
            
            asks_placeholder.dataframe(asks_df.style.format({
                'Rate': '{:.4f}',
                'Amount': '{:.2f}',
                'Period': '{:d}',
                'Orders': '{:.2f}',
                'Cumulative': '{:.2f}'
            }))
            
            # Update statistics
            bid_metric.metric("Best Bid Rate", f"{bids_df['Rate'].max():.4f}%")
            ask_metric.metric("Best Ask Rate", f"{asks_df['Rate'].min():.4f}%")
            spread = asks_df['Rate'].min() - bids_df['Rate'].max()
            spread_metric.metric("Spread", f"{spread:.4f}%")
        
        if not auto_refresh:
            break
            
        time.sleep(5)

if __name__ == "__main__":
    main() 