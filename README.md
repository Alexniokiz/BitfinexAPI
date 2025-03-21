# Bitfinex fUSD Funding Order Book Viewer

This application displays the real-time funding order book for fUSD on Bitfinex with a graphical interface.

## Features

- Real-time funding order book visualization
- Interactive chart with cumulative amounts
- Auto-refresh capability
- Raw data view
- Beautiful web interface

## Installation

1. Clone this repository
2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the application using Streamlit:
```bash
streamlit run funding_orderbook.py
```

The application will open in your default web browser. You can:
- View the order book chart
- Toggle auto-refresh
- View raw data in expandable sections
- Interact with the chart (zoom, pan, hover for details)

## Note

This application uses the public Bitfinex API, so no authentication is required. The order book updates every 5 seconds when auto-refresh is enabled. 