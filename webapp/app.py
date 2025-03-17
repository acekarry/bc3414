from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, g
import os
import sqlite3
import yfinance as yf
from datetime import date, datetime, timedelta
import pandas as pd
import json

from DatabaseManager import DatabaseManager
from PortfolioManager import PortfolioManager
from StockExplorer import StockExplorer
from NewsScraper import NewsScraper

app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Initialize managers
db_manager = DatabaseManager()
portfolio_manager = PortfolioManager()
stock_explorer = StockExplorer()
news_scraper = NewsScraper()

# Handle database connection teardown


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, 'sqlite_db', None)
    if db is not None:
        db.close()


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['POST'])
def login():
    name = request.form.get('name', '').strip().lower()

    # Basic validation
    if not name:
        flash('Name cannot be empty', 'error')
        return redirect(url_for('index'))
    if any(char.isdigit() for char in name):
        flash('Name cannot contain numbers', 'error')
        return redirect(url_for('index'))
    if not all(char.isalpha() or char.isspace() for char in name):
        flash('Name can only contain letters and spaces', 'error')
        return redirect(url_for('index'))

    # Login or register user
    user_id = portfolio_manager.login(name) or portfolio_manager.register(name)
    if user_id:
        session['user_id'] = user_id
        session['name'] = name

        # Create portfolio if needed
        portfolio_name = f"{name}'s Portfolio"
        portfolio_id = portfolio_manager.create_portfolio(
            user_id, portfolio_name)
        session['portfolio_id'] = portfolio_id

        return redirect(url_for('dashboard'))

    flash('Error logging in', 'error')
    return redirect(url_for('index'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    portfolio_id = session.get('portfolio_id')
    positions = db_manager.check_portfolio(portfolio_id)

    portfolio_data = []
    total_value = 0
    total_cost = 0

    for ticker, data in positions.items():
        if data["quantity"] == 0:
            continue

        # Get current market price
        market_price = portfolio_manager.get_price(ticker)
        if market_price is None:
            continue

        quantity = data["quantity"]
        if quantity > 0:  # Long position
            avg_price = data["total_cost"] / quantity
            current_value = market_price * quantity
            pnl = (market_price - avg_price) * quantity
            position_type = "Long"
        else:  # Short position
            avg_price = abs(data["total_cost"]) / abs(quantity)
            current_value = market_price * quantity
            pnl = (avg_price - market_price) * abs(quantity)
            position_type = "Short"

        # Calculate percent change
        pnl_percent = (pnl / abs(current_value)) * \
            100 if current_value != 0 else 0

        portfolio_data.append({
            'ticker': ticker,
            'name': data['name'],
            'position_type': position_type,
            'quantity': float(abs(quantity)),
            'avg_price': float(avg_price),
            'market_price': float(market_price),
            'current_value': float(current_value),
            'pnl': float(pnl),
            'pnl_percent': float(pnl_percent)
        })

        total_value += current_value
        total_cost += data["total_cost"]

    total_pnl = total_value - total_cost
    total_pnl_percent = (total_pnl / abs(total_value)) * \
        100 if total_value != 0 else 0

    # Get performance data for charts
    performance_data = get_portfolio_performance_data(portfolio_id)

    # Get sector data for pie chart
    sector_data = get_portfolio_sector_data(portfolio_id)

    return render_template('dashboard.html',
                           portfolio_data=portfolio_data,
                           total_value=float(total_value),
                           total_pnl=float(total_pnl),
                           total_pnl_percent=float(total_pnl_percent),
                           performance_data=json.dumps(performance_data),
                           sector_data=json.dumps(sector_data),
                           name=session.get('name', 'User'))


def get_portfolio_sector_data(portfolio_id):
    """Get portfolio sector allocation data for pie chart"""
    positions = db_manager.check_portfolio(portfolio_id)
    sector_values = {}

    for ticker, data in positions.items():
        if data["quantity"] == 0:
            continue

        market_price = portfolio_manager.get_price(ticker)
        if market_price is None:
            continue

        value = market_price * data["quantity"]

        # Get sector for this ticker
        valid_tickers = portfolio_manager.valid_tickers
        if ticker in valid_tickers:
            sector = valid_tickers[ticker].get("sector", "Unknown")
        else:
            sector = "Unknown"

        # Update sector value
        sector_values[sector] = sector_values.get(sector, 0) + value

    # Format for chart - ensure all values are basic Python types
    sector_data = [{'sector': str(sector), 'value': float(
        round(value, 2))} for sector, value in sector_values.items()]
    return sector_data
def get_portfolio_performance_data(portfolio_id):
    """Get portfolio performance data over time for charts"""
    # Fetch all transactions
    cursor = db_manager.get_cursor()
    cursor.execute(
        "SELECT transaction_date, ticker, price, quantity FROM transactions WHERE portfolio_id = ? ORDER BY transaction_date, id",
        (portfolio_id,)
    )
    transactions = cursor.fetchall()
    if not transactions:
        return []

    # Parse transaction dates
    transactions_parsed = []
    for t in transactions:
        trans_date = datetime.strptime(t[0], "%Y-%m-%d").date()
        transactions_parsed.append((trans_date, t[1], t[2], t[3]))

    # Determine date range
    start_date = min(t[0] for t in transactions_parsed)
    end_date = date.today()

    # Generate dates for the chart (monthly intervals for better performance)
    current_date = start_date
    chart_dates = []
    while current_date <= end_date:
        chart_dates.append(current_date)
        # Move to next month
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)

    # Add the current date if it's not already included
    if chart_dates[-1] != end_date:
        chart_dates.append(end_date)

    # Fetch historical price data for all tickers involved
    tickers_involved = set(t[1] for t in transactions_parsed)
    ticker_data = {}
    for ticker in tickers_involved:
        try:
            # Use yfinance to get historical data
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
            stock_data = yf.download(ticker, start=start_str, end=end_str)
            if not stock_data.empty:
                ticker_data[ticker] = stock_data
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")

    # Calculate portfolio value for each date
    performance_data = []
    for current_date in chart_dates:
        # Calculate positions as of this date
        positions = {}
        net_deposits = 0.0

        for trans in transactions_parsed:
            if trans[0] <= current_date:
                ticker = trans[1]
                price = trans[2]
                quantity = trans[3]

                # Track deposits
                net_deposits += price * quantity

                # Update positions
                positions[ticker] = positions.get(ticker, 0) + quantity

        # Calculate portfolio value
        portfolio_value = 0.0
        for ticker, quantity in positions.items():
            if quantity == 0:
                continue

            if ticker in ticker_data:
                # Get price on or before the current date
                price_data = ticker_data[ticker]
                if not price_data.empty:
                    # Find the closest date before or on the current date
                    closest_dates = price_data.index[price_data.index <= pd.Timestamp(
                        current_date)]
                    if len(closest_dates) > 0:
                        closest_date = closest_dates[-1]
                        # Convert pandas Series to float
                        price = float(price_data.loc[closest_date, 'Close'])
                        portfolio_value += price * quantity

        # Calculate returns
        total_return = portfolio_value - net_deposits

        # Add data point - ensure all values are basic Python types
        performance_data.append({
            'date': current_date.strftime("%Y-%m-%d"),
            'value': float(round(portfolio_value, 2)),
            'deposits': float(round(net_deposits, 2)),
            'returns': float(round(total_return, 2))
        })

    return performance_data

@app.route('/buy', methods=['GET', 'POST'])
def buy():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        ticker = request.form.get('ticker', '').upper()
        quantity = request.form.get('quantity', 0)
        order_type = request.form.get('order_type', 'market')

        try:
            quantity = float(quantity)
            if quantity <= 0:
                flash('Quantity must be positive', 'error')
                return redirect(url_for('buy'))
        except ValueError:
            flash('Invalid quantity', 'error')
            return redirect(url_for('buy'))

        # Validate ticker
        valid_tickers = portfolio_manager.valid_tickers
        if ticker not in valid_tickers:
            flash(f'Invalid ticker: {ticker}', 'error')
            return redirect(url_for('buy'))

        asset_name = valid_tickers[ticker]["name"]
        market_price = portfolio_manager.get_price(ticker)

        if market_price is None:
            flash(f'Could not retrieve market price for {ticker}', 'error')
            return redirect(url_for('buy'))

        transaction_date = str(date.today())

        if order_type == 'limit':
            limit_price = request.form.get('limit_price', 0)
            try:
                limit_price = float(limit_price)
                if limit_price <= 0:
                    flash('Limit price must be positive', 'error')
                    return redirect(url_for('buy'))
                price = limit_price
            except ValueError:
                flash('Invalid limit price', 'error')
                return redirect(url_for('buy'))
        else:  # market order
            price = market_price
            limit_price = None

        # Execute the transaction
        portfolio_id = session.get('portfolio_id')
        db_manager.insert_transaction(portfolio_id, ticker, asset_name, transaction_date,
                                      order_type, price, quantity, limit_price)

        flash(
            f'Successfully purchased {quantity} shares of {ticker} at ${price:.2f}', 'success')
        return redirect(url_for('dashboard'))

    # GET request - serve the buy form
    return render_template('buy.html', name=session.get('name', 'User'))


@app.route('/sell', methods=['GET', 'POST'])
def sell():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        ticker = request.form.get('ticker', '').upper()
        quantity = request.form.get('quantity', 0)
        order_type = request.form.get('order_type', 'market')

        try:
            quantity = float(quantity)
            if quantity <= 0:
                flash('Quantity must be positive', 'error')
                return redirect(url_for('sell'))
        except ValueError:
            flash('Invalid quantity', 'error')
            return redirect(url_for('sell'))

        # Validate ticker
        valid_tickers = portfolio_manager.valid_tickers
        if ticker not in valid_tickers:
            flash(f'Invalid ticker: {ticker}', 'error')
            return redirect(url_for('sell'))

        asset_name = valid_tickers[ticker]["name"]
        market_price = portfolio_manager.get_price(ticker)

        if market_price is None:
            flash(f'Could not retrieve market price for {ticker}', 'error')
            return redirect(url_for('sell'))

        transaction_date = str(date.today())

        if order_type == 'limit':
            limit_price = request.form.get('limit_price', 0)
            try:
                limit_price = float(limit_price)
                if limit_price <= 0:
                    flash('Limit price must be positive', 'error')
                    return redirect(url_for('sell'))
                price = limit_price
            except ValueError:
                flash('Invalid limit price', 'error')
                return redirect(url_for('sell'))
        else:  # market order
            price = market_price
            limit_price = None

        # Execute the transaction (negative quantity for selling)
        portfolio_id = session.get('portfolio_id')
        db_manager.insert_transaction(portfolio_id, ticker, asset_name, transaction_date,
                                      order_type, price, -quantity, limit_price)

        flash(
            f'Successfully sold {quantity} shares of {ticker} at ${price:.2f}', 'success')
        return redirect(url_for('dashboard'))

    # GET request - serve the sell form
    return render_template('sell.html', name=session.get('name', 'User'))


@app.route('/historical', methods=['GET', 'POST'])
def historical():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        ticker = request.form.get('ticker', '').upper()
        quantity = request.form.get('quantity', 0)
        price = request.form.get('price', 0)
        transaction_date = request.form.get('transaction_date', '')

        try:
            quantity = float(quantity)
            if quantity <= 0:
                flash('Quantity must be positive', 'error')
                return redirect(url_for('historical'))
        except ValueError:
            flash('Invalid quantity', 'error')
            return redirect(url_for('historical'))

        try:
            price = float(price)
            if price <= 0:
                flash('Price must be positive', 'error')
                return redirect(url_for('historical'))
        except ValueError:
            flash('Invalid price', 'error')
            return redirect(url_for('historical'))

        # Validate date
        try:
            datetime.strptime(transaction_date, '%Y-%m-%d')
            if transaction_date > str(date.today()):
                flash('Transaction date cannot be in the future', 'error')
                return redirect(url_for('historical'))
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD', 'error')
            return redirect(url_for('historical'))

        # Validate ticker
        valid_tickers = portfolio_manager.valid_tickers
        if ticker not in valid_tickers:
            flash(f'Invalid ticker: {ticker}', 'error')
            return redirect(url_for('historical'))

        asset_name = valid_tickers[ticker]["name"]

        # Execute the transaction
        portfolio_id = session.get('portfolio_id')
        db_manager.insert_transaction(portfolio_id, ticker, asset_name, transaction_date,
                                      'historical', price, quantity, None)

        flash(
            f'Successfully recorded historical purchase of {quantity} shares of {ticker} at ${price:.2f} on {transaction_date}', 'success')
        return redirect(url_for('dashboard'))

    # GET request - serve the historical form
    return render_template('historical.html',
                           max_date=date.today().strftime('%Y-%m-%d'),
                           name=session.get('name', 'User'))


@app.route('/search_ticker', methods=['GET'])
def search_ticker():
    query = request.args.get('q', '').upper()

    if not query:
        return jsonify([])

    valid_tickers = portfolio_manager.valid_tickers

    # Direct matches (tickers that start with the query)
    direct_matches = [
        {'ticker': ticker, 'name': data['name']}
        for ticker, data in valid_tickers.items()
        if ticker.startswith(query)
    ]

    # Fuzzy matches (company names that contain the query)
    fuzzy_matches = [
        {'ticker': ticker, 'name': data['name']}
        for ticker, data in valid_tickers.items()
        if query.lower() in data['name'].lower() and not ticker.startswith(query)
    ]

    # Combine and limit results
    results = direct_matches + fuzzy_matches
    return jsonify(results[:10])  # Limit to 10 results


@app.route('/explore')
def explore():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    return render_template('explore.html', name=session.get('name', 'User'))


@app.route('/explore/news', methods=['GET', 'POST'])
def explore_news():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    news = []
    ticker = request.args.get('ticker', '').upper()

    if ticker:
        valid_tickers = portfolio_manager.valid_tickers
        if ticker in valid_tickers:
            asset_name = valid_tickers[ticker]["name"]

            # Get news using GoogleNews (adapted from NewsScraper class)
            from GoogleNews import GoogleNews
            googlenews = GoogleNews(lang='en', region='US')
            googlenews.clear()
            googlenews.search(asset_name)
            results = googlenews.results()

            if results:
                news = [{
                    'title': item['title'],
                    'link': item['link'],
                    'date': item.get('date', 'N/A'),
                    'source': item.get('media', 'Unknown')
                } for item in results[:10]]  # Limit to 10 news items

    return render_template('explore_news.html', news=news, ticker=ticker, name=session.get('name', 'User'))


@app.route('/explore/filter', methods=['GET', 'POST'])
def explore_filter():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    sector_df = pd.read_csv("SnP_tickers_sector.csv").drop(
        columns=["Headquarters Location"])

    # Get unique sectors and industries
    sectors = sorted(sector_df["GICS Sector"].dropna().unique())
    industries = sorted(sector_df["GICS Sub-Industry"].dropna().unique())

    filter_type = request.args.get('filter_type', '')
    filter_value = request.args.get('filter_value', '')

    results = []
    selected_ticker = request.args.get('ticker', '')
    ticker_metrics = {}

    if filter_type and filter_value:
        column = "GICS Sector" if filter_type == "sector" else "GICS Sub-Industry" if filter_type == "industry" else "Security"
        filtered = sector_df[sector_df[column].str.contains(
            filter_value, case=False, na=False)]

        if not filtered.empty:
            results = filtered.to_dict('records')

    # If a specific ticker is selected, fetch additional metrics
    if selected_ticker:
        try:
            ticker_obj = yf.Ticker(selected_ticker)
            info = ticker_obj.info
            ticker_metrics = {
                "name": info.get("shortName", "N/A"),
                "market_cap": info.get("marketCap", "N/A"),
                "pe_ratio": info.get("trailingPE", "N/A"),
                "price": info.get("regularMarketPrice", "N/A"),
                "dividend_yield": info.get("dividendYield", "N/A"),
                "52w_high": info.get("fiftyTwoWeekHigh", "N/A"),
                "52w_low": info.get("fiftyTwoWeekLow", "N/A")
            }
        except Exception as e:
            ticker_metrics = {"error": str(e)}

    return render_template('explore_filter.html',
                           sectors=sectors,
                           industries=industries,
                           filter_type=filter_type,
                           filter_value=filter_value,
                           results=results,
                           selected_ticker=selected_ticker,
                           ticker_metrics=ticker_metrics,
                           name=session.get('name', 'User'))

# Helper functions for charts and data analysis


def get_portfolio_performance_data(portfolio_id):
    """Get portfolio performance data over time for charts"""
    # Fetch all transactions
    cursor = db_manager.get_cursor()
    cursor.execute(
        "SELECT transaction_date, ticker, price, quantity FROM transactions WHERE portfolio_id = ? ORDER BY transaction_date, id",
        (portfolio_id,)
    )
    transactions = cursor.fetchall()
    if not transactions:
        return []

    # Parse transaction dates
    transactions_parsed = []
    for t in transactions:
        trans_date = datetime.strptime(t[0], "%Y-%m-%d").date()
        transactions_parsed.append((trans_date, t[1], t[2], t[3]))

    # Determine date range
    start_date = min(t[0] for t in transactions_parsed)
    end_date = date.today()

    # Generate dates for the chart (monthly intervals for better performance)
    current_date = start_date
    chart_dates = []
    while current_date <= end_date:
        chart_dates.append(current_date)
        # Move to next month
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)

    # Add the current date if it's not already included
    if chart_dates[-1] != end_date:
        chart_dates.append(end_date)

    # Fetch historical price data for all tickers involved
    tickers_involved = set(t[1] for t in transactions_parsed)
    ticker_data = {}
    for ticker in tickers_involved:
        try:
            # Use yfinance to get historical data
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
            stock_data = yf.download(ticker, start=start_str, end=end_str)
            if not stock_data.empty:
                ticker_data[ticker] = stock_data
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")

    # Calculate portfolio value for each date
    performance_data = []
    for current_date in chart_dates:
        # Calculate positions as of this date
        positions = {}
        net_deposits = 0.0

        for trans in transactions_parsed:
            if trans[0] <= current_date:
                ticker = trans[1]
                price = trans[2]
                quantity = trans[3]

                # Track deposits
                net_deposits += price * quantity

                # Update positions
                positions[ticker] = positions.get(ticker, 0) + quantity

        # Calculate portfolio value
        portfolio_value = 0.0
        for ticker, quantity in positions.items():
            if quantity == 0:
                continue

            if ticker in ticker_data:
                # Get price on or before the current date
                price_data = ticker_data[ticker]
                if not price_data.empty:
                    # Find the closest date before or on the current date
                    closest_date = price_data.index[price_data.index <= pd.Timestamp(
                        current_date)]
                    if len(closest_date) > 0:
                        closest_date = closest_date[-1]
                        price = price_data.loc[closest_date, 'Close']
                        portfolio_value += price * quantity

        # Calculate returns
        total_return = portfolio_value - net_deposits

        # Add data point
        performance_data.append({
            'date': current_date.strftime("%Y-%m-%d"),
            'value': round(portfolio_value, 2),
            'deposits': round(net_deposits, 2),
            'returns': round(total_return, 2)
        })

    return performance_data


def get_portfolio_performance_data(portfolio_id):
    """Get portfolio performance data over time for charts"""
    # Fetch all transactions
    cursor = db_manager.get_cursor()
    cursor.execute(
        "SELECT transaction_date, ticker, price, quantity FROM transactions WHERE portfolio_id = ? ORDER BY transaction_date, id",
        (portfolio_id,)
    )
    transactions = cursor.fetchall()
    if not transactions:
        return []

    # Parse transaction dates
    transactions_parsed = []
    for t in transactions:
        trans_date = datetime.strptime(t[0], "%Y-%m-%d").date()
        transactions_parsed.append((trans_date, t[1], t[2], t[3]))

    # Determine date range
    start_date = min(t[0] for t in transactions_parsed)
    end_date = date.today()

    # Generate dates for the chart (monthly intervals for better performance)
    current_date = start_date
    chart_dates = []
    while current_date <= end_date:
        chart_dates.append(current_date)
        # Move to next month
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)

    # Add the current date if it's not already included
    if chart_dates[-1] != end_date:
        chart_dates.append(end_date)

    # Fetch historical price data for all tickers involved
    tickers_involved = set(t[1] for t in transactions_parsed)
    ticker_data = {}
    for ticker in tickers_involved:
        try:
            # Use yfinance to get historical data
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
            stock_data = yf.download(ticker, start=start_str, end=end_str)
            if not stock_data.empty:
                ticker_data[ticker] = stock_data
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")

    # Calculate portfolio value for each date
    performance_data = []
    for current_date in chart_dates:
        # Calculate positions as of this date
        positions = {}
        net_deposits = 0.0

        for trans in transactions_parsed:
            if trans[0] <= current_date:
                ticker = trans[1]
                price = trans[2]
                quantity = trans[3]

                # Track deposits
                net_deposits += price * quantity

                # Update positions
                positions[ticker] = positions.get(ticker, 0) + quantity

        # Calculate portfolio value
        portfolio_value = 0.0
        for ticker, quantity in positions.items():
            if quantity == 0:
                continue

            if ticker in ticker_data:
                # Get price on or before the current date
                price_data = ticker_data[ticker]
                if not price_data.empty:
                    # Find the closest date before or on the current date
                    closest_dates = price_data.index[price_data.index <= pd.Timestamp(
                        current_date)]
                    if len(closest_dates) > 0:
                        closest_date = closest_dates[-1]
                        # Convert pandas Series to float
                        price = float(price_data.loc[closest_date, 'Close'])
                        portfolio_value += price * quantity

        # Calculate returns
        total_return = portfolio_value - net_deposits

        # Add data point - ensure all values are basic Python types
        performance_data.append({
            'date': current_date.strftime("%Y-%m-%d"),
            'value': float(round(portfolio_value, 2)),
            'deposits': float(round(net_deposits, 2)),
            'returns': float(round(total_return, 2))
        })

    return performance_data


def convert_to_serializable(obj):
    """Convert pandas and numpy types to JSON serializable Python types"""
    import pandas as pd
    import numpy as np

    # Handle pandas Series
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    # Handle pandas DataFrame
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    # Handle numpy arrays
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    # Handle numpy numeric types
    elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.float64, np.float32, np.float16)):
        return float(obj)
    # Handle other types that might need conversion
    elif hasattr(obj, 'isoformat'):  # datetime objects
        return obj.isoformat()
    else:
        return obj
    

if __name__ == '__main__':
    app.run(debug=True)
