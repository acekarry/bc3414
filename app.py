from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, g, Response
import os
import sqlite3
import yfinance as yf
from datetime import date, datetime, timedelta
import pandas as pd
import json
from flask import Flask, request, redirect, url_for
import io
import csv
from collections import defaultdict
import urllib.parse
import requests

from DatabaseManager import DatabaseManager
from PortfolioManager import PortfolioManager
from StockExplorer import StockExplorer
from NewsScraper import NewsScraper
from plotly_charts import generate_performance_chart, generate_sector_chart
from market_overview import get_market_data


app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session management

# Initialize managers
db_manager = DatabaseManager()
portfolio_manager = PortfolioManager()
stock_explorer = StockExplorer()
news_scraper = NewsScraper()
# Teardown the per-request database connection


@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def setup_historical_routes(app, portfolio_manager):
    @app.route('/ticker_search', methods=['GET'])
    def ticker_search():
        if 'user_id' not in session:
            return redirect(url_for('index'))

        query = request.args.get('query', '').upper()
        valid_tickers = portfolio_manager.valid_tickers

        matching_tickers = []
        if query:
            matching_tickers = [
                (ticker, data['name'])
                for ticker, data in valid_tickers.items()
                if ticker.startswith(query) or query.lower() in data['name'].lower()
            ][:10]  # Limit to 10 results

        return render_template('ticker_results.html',
                               matching_tickers=matching_tickers,
                               query=query)

# -------------------------
# Routes
# -------------------------


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    # Basic validation
    if not username or not password:
        flash('Username and password cannot be empty', 'error')
        return redirect(url_for('index'))

    # Login user using the updated methods
    user = portfolio_manager.login(username, password)

    if user:
        session['user_id'] = user.user_id
        session['name'] = user.name

        # Create portfolio if needed
        portfolio_name = f"{user.name}'s Portfolio"
        portfolio_id = portfolio_manager.create_portfolio(
            user.user_id, portfolio_name)
        session['portfolio_id'] = portfolio_id

        return redirect(url_for('dashboard'))

    flash('Error logging in. Please check your username and password.', 'error')
    return redirect(url_for('index'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Basic validation
        if not first_name or not last_name or not username or not password:
            flash('All fields are required', 'error')
            return redirect(url_for('signup'))

        if any(char.isdigit() for char in first_name) or any(char.isdigit() for char in last_name):
            flash('First and Last names cannot contain numbers', 'error')
            return redirect(url_for('signup'))

        if not all(char.isalpha() or char.isspace() for char in first_name) or not all(char.isalpha() or char.isspace() for char in last_name):
            flash('First and Last names can only contain letters and spaces', 'error')
            return redirect(url_for('signup'))

        # Register user using the updated method
        user = portfolio_manager.register(
            first_name, last_name, username, password)

        if user:
            session['user_id'] = user.user_id
            session['name'] = user.name

            # Create portfolio if needed
            portfolio_name = f"{user.name}'s Portfolio"
            portfolio_id = portfolio_manager.create_portfolio(
                user.user_id, portfolio_name)
            session['portfolio_id'] = portfolio_id

            return redirect(url_for('dashboard'))

        flash('Error signing up. Username may already exist or other issue.', 'error')
        return redirect(url_for('signup'))

    return render_template('signup.html')


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

    # Get performance and sector data
    perf_data = get_portfolio_performance_data(portfolio_id)
    sector_data = get_portfolio_sector_data(portfolio_id)

    # Generate static chart images
    performance_chart = generate_performance_chart(perf_data)
    sector_chart = generate_sector_chart(sector_data)

    return render_template('dashboard.html',
                           portfolio_data=portfolio_data,
                           total_value=float(total_value),
                           total_pnl=float(total_pnl),
                           total_pnl_percent=float(total_pnl_percent),
                           performance_chart=performance_chart,
                           sector_chart=sector_chart,
                           name=session.get('name', 'User'))


@app.route("/export_holdings")
def export_holdings():
    portfolio_id = session.get('portfolio_id')
    transactions = db_manager.check_portfolio(portfolio_id, export=True)

    if not transactions:
        return "No holdings to export.", 204

    holdings = defaultdict(lambda: {"name": "", "quantity": 0, "avg_price": 0})

    for ticker, name, transaction_date, order_type, price, quantity, limit_price in transactions:
        price = float(price)
        quantity = int(quantity)

        if ticker not in holdings:
            holdings[ticker]["name"] = name

        holdings[ticker]["quantity"] += quantity

        if holdings[ticker]["quantity"]:
            total_cost = holdings[ticker]["avg_price"] * \
                (holdings[ticker]["quantity"] - quantity) + (price * quantity)
            holdings[ticker]["avg_price"] = total_cost / \
                holdings[ticker]["quantity"]
        else:
            holdings[ticker]["avg_price"] = 0

    holdings = {ticker: data for ticker,
                data in holdings.items()}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ticker", "name", "quantity",
                    "avg_price"])

    for ticker, data in holdings.items():
        writer.writerow(
            [ticker, data["name"], data["quantity"], round(data["avg_price"], 2)])

    output.seek(0)

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=portfolio_holdings.csv"}
    )


@app.route("/import_holdings", methods=["POST"])
def import_holdings():
    if "file" not in request.files:
        flash("No file part", "danger")
        return redirect(url_for("dashboard"))

    file = request.files["file"]

    if file.filename == "":
        flash("No selected file", "warning")
        return redirect(url_for("dashboard"))

    if file:
        try:
            portfolio_id = session.get('portfolio_id')
            stream = io.StringIO(file.stream.read().decode("utf-8"))
            reader = csv.reader(stream)

            headers = next(reader)  # Read the first row (header)
            expected_headers = ["ticker", "name", "transaction_date",
                                "order_type", "price", "quantity", "limit_price"]

            if headers != expected_headers:
                flash("Invalid CSV format", "danger")
                return redirect(url_for("dashboard"))

            for row in reader:
                ticker, name, transaction_date, order_type, price, quantity, limit_price = row
                price = float(price)
                quantity = int(quantity)

                db_manager.insert_transaction(
                    portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price)

            flash("Portfolio imported successfully!", "success")

        except Exception as e:
            flash(f"Error importing portfolio: {e}", "danger")

    return redirect(url_for("dashboard"))


@app.route('/buy', methods=['GET', 'POST'])
def buy():
    valid_tickers = portfolio_manager.valid_tickers
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
        else:
            price = market_price
            limit_price = None

        portfolio_id = session.get('portfolio_id')
        db_manager.insert_transaction(portfolio_id, ticker, asset_name, transaction_date,
                                      order_type, price, quantity, limit_price)

        flash(
            f'Successfully purchased {quantity} shares of {ticker} at ${price:.2f}', 'success')
        return redirect(url_for('dashboard'))

    return render_template('buy.html', name=session.get('name', 'User'), stock_list=valid_tickers)


@app.route('/sell', methods=['GET', 'POST'])
def sell():
    valid_tickers = portfolio_manager.valid_tickers
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
        else:
            price = market_price
            limit_price = None

        portfolio_id = session.get('portfolio_id')
        db_manager.insert_transaction(portfolio_id, ticker, asset_name, transaction_date,
                                      order_type, price, -quantity, limit_price)

        flash(
            f'Successfully sold {quantity} shares of {ticker} at ${price:.2f}', 'success')
        return redirect(url_for('dashboard'))

    return render_template('sell.html', name=session.get('name', 'User'), stock_list=valid_tickers)


@app.route('/historical', methods=['GET', 'POST'])
def historical():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    selected_ticker = request.args.get('ticker', '')
    selected_name = request.args.get('name', '')
    matching_tickers = []
    query = ''

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

        try:
            datetime.strptime(transaction_date, '%Y-%m-%d')
            if transaction_date > str(date.today()):
                flash('Transaction date cannot be in the future', 'error')
                return redirect(url_for('historical'))
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD', 'error')
            return redirect(url_for('historical'))

        valid_tickers = portfolio_manager.valid_tickers
        if ticker not in valid_tickers:
            flash(f'Invalid ticker: {ticker}', 'error')
            return redirect(url_for('historical'))

        asset_name = valid_tickers[ticker]["name"]
        portfolio_id = session.get('portfolio_id')
        db_manager.insert_transaction(portfolio_id, ticker, asset_name, transaction_date,
                                      'historical', price, quantity, None)

        flash(
            f'Successfully recorded historical purchase of {quantity} shares of {ticker} at ${price:.2f} on {transaction_date}', 'success')
        return redirect(url_for('dashboard'))

    return render_template('historical.html',
                           max_date=date.today().strftime('%Y-%m-%d'),
                           selected_ticker=selected_ticker,
                           selected_name=selected_name,
                           matching_tickers=matching_tickers,
                           query=query,
                           name=session.get('name', 'User'))


@app.route('/ticker_search', methods=['GET'])
def ticker_search():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    query = request.args.get('query', '').upper()
    valid_tickers = portfolio_manager.valid_tickers

    matching_tickers = []
    if query:
        # Direct matches (tickers that start with the query)
        direct_matches = [
            (ticker, data['name'])
            for ticker, data in valid_tickers.items()
            if ticker.startswith(query)
        ]

        # Fuzzy matches (company names containing the query)
        fuzzy_matches = [
            (ticker, data['name'])
            for ticker, data in valid_tickers.items()
            if query.lower() in data['name'].lower() and not ticker.startswith(query)
        ]

        matching_tickers = direct_matches + fuzzy_matches
        matching_tickers = matching_tickers[:10]  # Limit to 10 results

    return render_template('historical.html',
                           max_date=date.today().strftime('%Y-%m-%d'),
                           matching_tickers=matching_tickers,
                           query=query,
                           selected_ticker='',
                           selected_name='',
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

    # Fuzzy matches (company names containing the query)
    fuzzy_matches = [
        {'ticker': ticker, 'name': data['name']}
        for ticker, data in valid_tickers.items()
        if query.lower() in data['name'].lower() and not ticker.startswith(query)
    ]

    results = direct_matches + fuzzy_matches
    return jsonify(results[:10])  # Limit to 10 results


@app.route('/explore')
def explore():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    market_data = get_market_data()

    return render_template('explore.html',
                           market_data=market_data,
                           name=session.get('name', 'User'))


@app.route('/explore/news', methods=['GET', 'POST'])
def explore_news():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    news = []
    ticker = request.args.get('ticker', '').upper()
    query = request.args.get('query', '')

    # Handle search suggestions (without JavaScript)
    matching_tickers = []
    valid_tickers = portfolio_manager.valid_tickers
    if query and not ticker:
        # Direct matches (tickers that start with the query)
        direct_matches = [
            {'ticker': t, 'name': data['name']}
            for t, data in valid_tickers.items()
            if t.startswith(query.upper())
        ]
        # Fuzzy matches (company names containing the query)
        fuzzy_matches = [
            {'ticker': t, 'name': data['name']}
            for t, data in valid_tickers.items()
            if query.lower() in data['name'].lower() and not t.startswith(query.upper())
        ]
        matching_tickers = direct_matches + fuzzy_matches
        matching_tickers = matching_tickers[:10]  # Limit to 10 results

    if ticker:
        if ticker in valid_tickers:
            asset_name = valid_tickers[ticker]["name"]

            api_key = "bf93721d5d8c4ebaa70216a43ee0350f"

            # Make the request to NewsAPI
            response = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q": f"{asset_name} stock",
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": 10,
                    "apiKey": api_key
                }
            )

            data = response.json()

            # Handle error or empty result
            if data.get("status") != "ok" or not data.get("articles"):
                news = []
            else:
                news = [{
                    'title': article['title'],
                    'link': article['url'],
                    'date': article.get('publishedAt', 'N/A'),
                    'source': article.get('source', {}).get('name', 'Unknown')
                } for article in data['articles']]


        else:
            flash(
                f"Ticker '{ticker}' not found. Did you mean one of these?", 'error')

            # Suggest similar tickers
            direct_matches = [
                {'ticker': t, 'name': data['name']}
                for t, data in valid_tickers.items()
                if t.startswith(ticker)
            ]
            fuzzy_matches = [
                {'ticker': t, 'name': data['name']}
                for t, data in valid_tickers.items()
                if ticker.lower() in data['name'].lower() and not t.startswith(ticker)
            ]
            matching_tickers = (direct_matches + fuzzy_matches)[:10]

    return render_template(
        'explore_news.html',
        news=news,
        ticker=ticker,
        query=query,
        matching_tickers=matching_tickers,
        name=session.get('name', 'User')
    )


@app.route('/explore/filter', methods=['GET', 'POST'])
def explore_filter():
    """
    Filter and explore stocks by sector, industry, or company name.

    This route handles filtering of stock data based on user selection.
    It loads sector/industry data from CSV, processes filter parameters,
    and returns filtered results along with additional stock metrics
    when a specific stock is selected.
    """
    # Check if user is logged in
    if 'user_id' not in session:
        return redirect(url_for('index'))

    try:
        # Load and prepare data
        sector_df = pd.read_csv("SnP_tickers_sector.csv")

        # Detect and handle column names with or without asterisks
        columns = sector_df.columns.tolist()
        sector_col = next(
            (col for col in columns if col.endswith('GICS Sector')), 'GICS Sector')
        industry_col = next((col for col in columns if col.endswith(
            'GICS Sub-Industry')), 'GICS Sub-Industry')

        # Remove location column if present (with or without asterisk)
        location_cols = [
            col for col in columns if 'Headquarters Location' in col]
        if location_cols:
            sector_df = sector_df.drop(columns=location_cols)

        # Get unique values for dropdowns
        sectors = sorted(sector_df[sector_col].dropna().unique())
        industries = sorted(sector_df[industry_col].dropna().unique())

        # Process filter parameters
        filter_type = request.args.get('filter_type', 'sector')
        filter_value = request.args.get('filter_value', '')
        selected_ticker = request.args.get('ticker', '')

        # Log the request parameters for debugging
        app.logger.info(
            f"Filter request - Type: {filter_type}, Value: {filter_value}, Ticker: {selected_ticker}")

        results = []
        ticker_metrics = {}

        # Apply filtering based on filter type and value
        if filter_type and filter_value:
            if filter_type == "sector":
                # Filter by sector
                filtered = sector_df[sector_df[sector_col].str.contains(
                    filter_value, case=False, na=False)]
                if not filtered.empty:
                    results = filtered.to_dict('records')
                    app.logger.info(
                        f"Found {len(results)} results for sector: {filter_value}")

            elif filter_type == "industry":
                # Filter by industry
                filtered = sector_df[sector_df[industry_col].str.contains(
                    filter_value, case=False, na=False)]
                if not filtered.empty:
                    results = filtered.to_dict('records')
                    app.logger.info(
                        f"Found {len(results)} results for industry: {filter_value}")

            elif filter_type == "name":
                # Filter by company name or symbol - try both columns
                name_filtered = sector_df[sector_df["Security"].str.contains(
                    filter_value, case=False, na=False)]

                symbol_filtered = sector_df[sector_df["Symbol"].str.contains(
                    filter_value, case=False, na=False)]

                # Combine results and remove duplicates
                filtered = pd.concat(
                    [name_filtered, symbol_filtered]).drop_duplicates()

                if not filtered.empty:
                    results = filtered.to_dict('records')
                    app.logger.info(
                        f"Found {len(results)} results for name/symbol: {filter_value}")
                else:
                    app.logger.info(
                        f"No results found for name/symbol: {filter_value}")

        # If specific ticker is selected, fetch additional metrics
        if selected_ticker:
            # If we don't have the ticker in results, look it up directly
            if not results:
                ticker_filtered = sector_df[sector_df["Symbol"]
                                            == selected_ticker]
                if not ticker_filtered.empty:
                    results = ticker_filtered.to_dict('records')

            try:
                # Fetch additional metrics using yfinance
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
                app.logger.info(
                    f"Retrieved metrics for ticker: {selected_ticker}")
            except Exception as e:
                ticker_metrics = {"error": str(e)}
                app.logger.error(
                    f"Error fetching metrics for {selected_ticker}: {e}")

    except Exception as e:
        # Handle any unexpected errors
        app.logger.error(f"Error in explore_filter: {e}")
        flash(f"An error occurred: {e}", "error")
        sectors, industries = [], []
        results = []
        ticker_metrics = {}

    # Render template with all necessary data
    return render_template('explore_filter.html',
                           sectors=sectors,
                           industries=industries,
                           filter_type=filter_type,
                           filter_value=filter_value,
                           results=results,
                           selected_ticker=selected_ticker,
                           ticker_metrics=ticker_metrics,
                           name=session.get('name', 'User'))


# -------------------------
# Helper Functions
# -------------------------

def get_portfolio_performance_data(portfolio_id):
    """
    Get portfolio performance data over time for charts.
    This function aggregates transaction data, fetches historical prices via yfinance,
    and computes portfolio value, net deposits, and returns at monthly intervals.
    """
    cursor = db_manager.get_cursor()
    cursor.execute(
        "SELECT transaction_date, ticker, price, quantity FROM transactions WHERE portfolio_id = ? ORDER BY transaction_date, id",
        (portfolio_id,)
    )
    transactions = cursor.fetchall()
    if not transactions:
        return []

    # Parse transactions
    transactions_parsed = []
    for t in transactions:
        trans_date = datetime.strptime(t[0], "%Y-%m-%d").date()
        transactions_parsed.append((trans_date, t[1], t[2], t[3]))

    start_date = min(t[0] for t in transactions_parsed)
    end_date = date.today()

    # Generate monthly dates for the chart
    current_date = start_date
    chart_dates = []
    while current_date <= end_date:
        chart_dates.append(current_date)
        if current_date.month == 12:
            current_date = date(current_date.year + 1, 1, 1)
        else:
            current_date = date(current_date.year, current_date.month + 1, 1)
    if chart_dates[-1] != end_date:
        chart_dates.append(end_date)

    # Fetch historical price data for all involved tickers
    tickers_involved = set(t[1] for t in transactions_parsed)
    ticker_data = {}
    for ticker in tickers_involved:
        try:
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")
            stock_data = yf.download(ticker, start=start_str, end=end_str)
            if not stock_data.empty:
                ticker_data[ticker] = stock_data
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")

    performance_data = []
    for current_date in chart_dates:
        positions = {}
        net_deposits = 0.0

        # Aggregate transactions up to the current date
        for trans in transactions_parsed:
            if trans[0] <= current_date:
                ticker = trans[1]
                price = trans[2]
                quantity = trans[3]
                net_deposits += price * quantity
                positions[ticker] = positions.get(ticker, 0) + quantity

        portfolio_value = 0.0
        for ticker, quantity in positions.items():
            if quantity == 0 or ticker not in ticker_data:
                continue
            price_data = ticker_data[ticker]
            closest_dates = price_data.index[price_data.index <= pd.Timestamp(
                current_date)]
            if len(closest_dates) > 0:
                closest_date = closest_dates[-1]
                price = float(price_data.loc[closest_date, 'Close'])
                portfolio_value += price * quantity

        total_return = portfolio_value - net_deposits
        performance_data.append({
            'date': current_date.strftime("%Y-%m-%d"),
            'value': float(round(portfolio_value, 2)),
            'deposits': float(round(net_deposits, 2)),
            'returns': float(round(total_return, 2))
        })

    return performance_data


def get_portfolio_sector_data(portfolio_id):
    """
    Get portfolio sector allocation data for a pie chart.
    This function aggregates transactions to calculate the total value per sector.
    """
    positions = db_manager.check_portfolio(portfolio_id)
    sector_values = {}
    for ticker, data in positions.items():
        if data["quantity"] == 0:
            continue
        market_price = portfolio_manager.get_price(ticker)
        if market_price is None:
            continue
        value = market_price * data["quantity"]
        valid_tickers = portfolio_manager.valid_tickers
        if ticker in valid_tickers:
            sector = valid_tickers[ticker].get("sector", "Unknown")
        else:
            sector = "Unknown"
        sector_values[sector] = sector_values.get(sector, 0) + value
    sector_data = [{'sector': str(sector), 'value': float(
        round(value, 2))} for sector, value in sector_values.items()]
    return sector_data


def convert_to_serializable(obj):
    """
    Convert pandas, numpy, or datetime objects to JSON serializable types.
    """
    import pandas as pd
    import numpy as np

    if isinstance(obj, pd.Series):
        return obj.to_dict()
    elif isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient='records')
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.float64, np.float32, np.float16)):
        return float(obj)
    elif hasattr(obj, 'isoformat'):  # For datetime objects
        return obj.isoformat()
    else:
        return obj


# -------------------------
# Run the App
# -------------------------
if __name__ == '__main__':
    app.run(debug=True)
