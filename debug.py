import requests

def fetch_period_data_sync(period):
    """Fetch funding orderbook data for a specific period synchronously"""
    url = f"https://api-pub.bitfinex.com/v2/book/fUSD/P{period}?len=250"
    headers = {"accept": "application/json"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        # Remove duplicates by converting to tuples and using set
        unique_orders = list({tuple(order) for order in data})
        return unique_orders
    except Exception as e:
        print(f"Error fetching P{period}: {str(e)}")
        return []

def fetch_all_periods_sync():
    """Fetch funding orderbook data for all periods (P0-P4) synchronously"""
    results = []
    result = fetch_period_data_sync(4)
    results.append(result)
    return results

def format_period_range(periods):
    """Format period range as a string"""
    if not periods:
        return ""
    periods = sorted(list(set(periods)))  # Remove duplicates and sort
    if len(periods) == 1:
        return str(periods[0])
    return f"{min(periods)}-{max(periods)}"

# Fetch funding stats for fUSD from Bitfinex public API
data = fetch_all_periods_sync()

target_rate = 0.08  # Fixed at 0.1%

print(f"\nOrders at {target_rate}%:")
print("=" * 40)

for period_data in data:
    for order in period_data:
        if len(order) >= 4:
            rate = order[0] * 100  # Convert to percentage
            amount = order[3]
            period = order[1]
            
            if rate == target_rate and amount > 0:  # Only show bids at exactly 0.1%
                print(f"Period: {period} days, Amount: {amount:,.2f} USD")