import yfinance as yf
import pandas as pd
import base64
from io import BytesIO
from datetime import datetime, timedelta
import random


def get_market_data():
    indices = {
        'sp500': {
            'symbol': '^GSPC',
            'name': 'S&P 500',
            'price': 0,
            'change': 0,
            'change_percent': 0
        },
        'dow': {
            'symbol': '^DJI',
            'name': 'Dow Jones',
            'price': 0,
            'change': 0,
            'change_percent': 0
        },
        'nasdaq': {
            'symbol': '^IXIC',
            'name': 'NASDAQ',
            'price': 0,
            'change': 0,
            'change_percent': 0
        }
    }

    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=2)

        for key, index in indices.items():
            ticker = yf.Ticker(index['symbol'])
            hist = ticker.history(start=start_date, end=end_date)

            if not hist.empty and len(hist) >= 2:
                prev_close = hist['Close'].iloc[-2]
                current = hist['Close'].iloc[-1]

                index['price'] = round(current, 2)
                index['change'] = round(current - prev_close, 2)
                index['change_percent'] = round(
                    (current - prev_close) / prev_close * 100, 2)
            else:
                # Use mock data if real data fetch fails
                generate_mock_data(index)
    except Exception as e:
        for key, index in indices.items():
            generate_mock_data(index)

    return indices


def generate_mock_data(index):
    base_prices = {
        '^GSPC': 4500,  # S&P 500
        '^DJI': 35000,  # Dow Jones
        '^IXIC': 14000  # NASDAQ
    }

    base_price = base_prices.get(index['symbol'], 1000)
    price = base_price + (random.random() * base_price * 0.1)
    change_percent = (random.random() * 2) - \
        1  
    change = price * change_percent / 100

    index['price'] = round(price, 2)
    index['change'] = round(change, 2)
    index['change_percent'] = round(change_percent, 2)
