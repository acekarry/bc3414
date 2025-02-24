import sqlite3
import yfinance as yf
import csv
import matplotlib.pyplot as plt  # For visualization
import os
import datetime
from GoogleNews import GoogleNews
import pandas as pd

class NewsScraper:
    def __init__(self, lang='en', region='US'):
        self.googlenews = GoogleNews(lang=lang, region=region)

    def show_news(self, ticker, num_results=5):
        """Fetch and display top news headlines for the given ticker with clickable hyperlinks."""
        self.googlenews.search(ticker)
        results = self.googlenews.results()
        if not results:
            print(f"No news found for {ticker}.")
            return

        print(f"\nTop {num_results} news articles for {ticker}: (ctrl/cmd+click to read in browser)")
        for news in results[:num_results]:
            title = news['title']
            link = news['link']
            # ANSI escape sequences for hyperlinks (supported in some terminals)
            hyperlink = f"    \033]8;;{link}\033\\{title}\033]8;;\033\\"
            print(hyperlink, "\n")


class DatabaseManager:
    def __init__(self, db_name="portfolio.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        """Creates the required tables if they do not exist."""
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                                id INTEGER PRIMARY KEY, 
                                name TEXT UNIQUE)''')

        self.cursor.execute('''CREATE TABLE IF NOT EXISTS portfolios (
                                id INTEGER PRIMARY KEY, 
                                owner_id INTEGER UNIQUE, 
                                name TEXT, 
                                FOREIGN KEY(owner_id) REFERENCES users(id))
                            ''')

        # Replacing assets with transactions table
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                                id INTEGER PRIMARY KEY,
                                portfolio_id INTEGER,
                                ticker TEXT,
                                name TEXT,
                                transaction_date TEXT,
                                order_type TEXT,
                                price REAL,
                                quantity INTEGER,
                                limit_price REAL,
                                FOREIGN KEY(portfolio_id) REFERENCES portfolios(id)
                            )''')
        self.conn.commit()

    def register_user(self, name):
        try:
            self.cursor.execute("INSERT INTO users (name) VALUES (?)", (name,))
            self.conn.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            print("User already exists. Please log in.")
            return None

    def login_user(self, name):
        self.cursor.execute("SELECT id FROM users WHERE name = ?", (name,))
        user = self.cursor.fetchone()
        return user[0] if user else None

    def insert_portfolio(self, owner_id, name):
        self.cursor.execute(
            "INSERT INTO portfolios (owner_id, name) VALUES (?, ?)", (owner_id, name))
        self.conn.commit()
        return self.cursor.lastrowid

    def get_market_price(self, ticker):
        """Fetch the latest market price from Yahoo Finance, or the nearest trading day if today's data is unavailable."""
        try:
            stock = yf.Ticker(ticker)
            stock_data = stock.history(period="1d")
            if stock_data.empty:
                # If today's data is missing, search backward for the nearest trading day's data.
                today = datetime.datetime.today()
                max_lookback = 10  # look back up to 10 days
                days_back = 0
                price = None
                while days_back < max_lookback:
                    current_date = today - datetime.timedelta(days=days_back)
                    next_day = current_date + datetime.timedelta(days=1)
                    data = stock.history(start=current_date.strftime("%Y-%m-%d"),
                                            end=next_day.strftime("%Y-%m-%d"))
                    if not data.empty:
                        price = data["Close"].iloc[0]
                        break
                    days_back += 1
                if price is None:
                    print(f"Error fetching market data for {ticker}.")
                return price
            else:
                return stock_data["Close"].iloc[-1]
        except Exception as e:
            print(f"Error fetching market data for {ticker}: {e}")
            return None

    def get_historical_price(self, ticker, transaction_date):
        """Fetch the historical market price for a given date, or the nearest previous trading day if not available."""
        try:
            stock = yf.Ticker(ticker)
            date_obj = datetime.datetime.strptime(transaction_date, "%Y-%m-%d")
            max_lookback = 10  # limit how many days back we search
            days_back = 0
            price = None
            used_date = None

            while days_back < max_lookback:
                current_date = date_obj - datetime.timedelta(days=days_back)
                next_day = current_date + datetime.timedelta(days=1)
                data = stock.history(start=current_date.strftime("%Y-%m-%d"),
                                     end=next_day.strftime("%Y-%m-%d"))
                if not data.empty:
                    price = data["Close"].iloc[0]
                    used_date = current_date.strftime("%Y-%m-%d")
                    break
                days_back += 1

            if price is None:
                print(
                    f"Error: No trading data found for {ticker} within {max_lookback} days of {transaction_date}.")
                return None
            if used_date != transaction_date:
                print(
                    f"{ticker}: No data on {transaction_date}. Using data from nearest trading day: {used_date}.")
            return price
        except Exception as e:
            print(f"Error fetching historical price for {ticker}: {e}")
            return None

    def insert_transaction(self, portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price=None):
        """Records a transaction (buy/sell) for the portfolio."""
        self.cursor.execute(
            """INSERT INTO transactions (portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price))
        self.conn.commit()
        return self.cursor.lastrowid

    def check_portfolio(self, portfolio_id):
        """
        Aggregates transactions to compute current positions.
        For each ticker, transactions are processed in order (by date) to compute
        net quantity and the weighted average cost basis.
        """
        self.cursor.execute(
            "SELECT ticker, name, transaction_date, order_type, price, quantity, limit_price FROM transactions WHERE portfolio_id = ? ORDER BY transaction_date, id",
            (portfolio_id,))
        transactions = self.cursor.fetchall()
        if not transactions:
            print("\nNo transactions found in this portfolio.")
            return {}

        positions = {}
        for t in transactions:
            ticker, name, t_date, order_type, price, quantity, limit_price = t
            if ticker not in positions:
                positions[ticker] = {"name": name,
                                     "quantity": 0, "total_cost": 0.0}
            # For a buy (quantity positive)
            if quantity > 0:
                positions[ticker]["quantity"] += quantity
                positions[ticker]["total_cost"] += price * quantity
            else:
                # For a sell (quantity negative), reduce the position cost basis proportionally.
                if positions[ticker]["quantity"] > 0:
                    avg_cost = positions[ticker]["total_cost"] / \
                        positions[ticker]["quantity"]
                else:
                    avg_cost = 0
                positions[ticker]["quantity"] += quantity
                positions[ticker]["total_cost"] += avg_cost * \
                    quantity  # quantity is negative, so cost decreases
        return positions

    def load_valid_tickers(self, filename="SnP_tickers_sector.csv"):
        """
        Loads valid stock tickers and their corresponding asset names and sectors from a CSV file.
        Expected CSV headers: Symbol, Security, GICS Sector, ...
        """
        tickers = {}
        if not os.path.isfile(filename):
            print(f"Error: File {filename} not found.")
            return tickers
        try:
            with open(filename, 'r') as file:
                reader = csv.reader(file)
                headers = next(reader, None)  # Skip header row if present
                for row in reader:
                    ticker = row[0].strip().upper()
                    name = row[1].strip()
                    sector = row[2].strip() if len(row) > 2 else "Unknown"
                    tickers[ticker] = {"name": name, "sector": sector}
        except FileNotFoundError:
            print(f"File {filename} not found.")
        return tickers


class PortfolioManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.valid_tickers = self.db.load_valid_tickers()
        self.news_scraper = NewsScraper()  # Instantiate the news scraper

    def register(self, name):
        return self.db.register_user(name)

    def login(self, name):
        return self.db.login_user(name)

    def get_market_price(self, ticker):
        """Fetch the latest market price from Yahoo Finance."""
        try:
            stock = yf.Ticker(ticker)
            stock_data = stock.history(period="1d")
            if not stock_data.empty:
                return stock_data["Close"].iloc[-1]
            else:
                return None
        except Exception as e:
            print(f"Error fetching market data for {ticker}: {e}")
            return None

    def get_historical_price(self, ticker, transaction_date):
        """Fetch the historical market price for a given date."""
        try:
            stock = yf.Ticker(ticker)
            date_obj = datetime.datetime.strptime(transaction_date, "%Y-%m-%d")
            max_lookback = 10  
            days_back = 0
            price = None
            used_date = None

            while days_back < max_lookback:
                current_date = date_obj - datetime.timedelta(days=days_back)
                next_day = current_date + datetime.timedelta(days=1)
                data = stock.history(start=current_date.strftime("%Y-%m-%d"),
                                     end=next_day.strftime("%Y-%m-%d"))
                if not data.empty:
                    price = data["Close"].iloc[0]
                    used_date = current_date.strftime("%Y-%m-%d")
                    break
                days_back += 1

            if price is None:
                print(
                    f"Error: No trading data found for {ticker} within {max_lookback} days of {transaction_date}.")
                return None
            if used_date != transaction_date:
                print(
                    f"{ticker}: No data on {transaction_date}. Using data from nearest trading day: {used_date}.")
            return price
        except Exception as e:
            print(f"Error fetching historical price for {ticker}: {e}")
            return None

    def create_portfolio(self, owner_id, name):
        self.db.cursor.execute(
            "SELECT id FROM portfolios WHERE owner_id = ?", (owner_id,))
        existing_portfolio = self.db.cursor.fetchone()

        if existing_portfolio:
            print(
                f"User already has a portfolio with ID {existing_portfolio[0]}.")
            return existing_portfolio[0]
        else:
            return self.db.insert_portfolio(owner_id, name)

    def buy_loop(self, portfolio_id):
        while True:
            ticker = input(
                "Enter stock ticker (or type 'exit' to quit): ").upper()
            if ticker == "EXIT":
                break

            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]
                market_price = self.get_market_price(ticker)
                if market_price is None:
                    print(
                        f"Could not retrieve market price for {ticker}. Please try again.")
                    continue

                print(f"\nStock found: {ticker} - {asset_name}")
                print(f"Current market price: ${market_price:.2f}")

                view_news = input(
                    "Would you like to view recent news for this stock? (y/n): ").lower()
                if view_news == 'y':
                    self.news_scraper.show_news(asset_name)

                confirm = input(
                    f"Do you want to buy {asset_name} ({ticker})? (y/n): ").lower()
                if confirm == 'y':
                    historical = input(
                        "Do you want to record a historical transaction? (y/n): ").lower()
                    if historical == 'y':
                        transaction_date = input(
                            "Enter transaction date (YYYY-MM-DD): ")
                        order_type = input(
                            "Enter order type (market/limit): ").lower()
                        if order_type == 'limit':
                            limit_price = float(input("Enter limit price: "))
                            price = limit_price
                        elif order_type == 'market':
                            price = self.get_historical_price(
                                ticker, transaction_date)
                            if price is None:
                                print(
                                    "Error fetching historical market price. Transaction canceled.")
                                continue
                            limit_price = None
                        else:
                            print("Invalid order type. Please try again.")
                            continue
                        quantity = int(input("Enter quantity: "))
                        self.db.insert_transaction(
                            portfolio_id, ticker, asset_name, transaction_date, order_type, price, quantity, limit_price)
                        print(
                            f"Recorded historical purchase of {quantity} shares of {ticker} on {transaction_date} at ${price:.2f}.")
                    else:
                        # Record a current transaction using today's date.
                        from datetime import date
                        transaction_date = str(date.today())
                        order_type = input(
                            "Enter order type (market/limit): ").lower()
                        if order_type == 'limit':
                            limit_price = float(input("Enter limit price: "))
                            price = limit_price
                        elif order_type == 'market':
                            price = market_price
                            limit_price = None
                        else:
                            print("Invalid order type. Please try again.")
                            continue
                        quantity = int(input("Enter quantity: "))
                        self.db.insert_transaction(
                            portfolio_id, ticker, asset_name, transaction_date, order_type, price, quantity, limit_price)
                        print(
                            f"Successfully recorded purchase of {quantity} shares of {ticker} at ${price:.2f} on {transaction_date}.")
                else:
                    print("Buy transaction canceled.")
            else:
                print("\nNo matching ticker found. Here are some suggested tickers:")
                self.validate_ticker(ticker)

    def check_portfolio(self, portfolio_id):
        positions = self.db.check_portfolio(portfolio_id)
        if positions:
            print("\nCurrent Portfolio Holdings:")
            for ticker, data in positions.items():
                quantity = data["quantity"]
                if quantity == 0:
                    continue
                avg_price = data["total_cost"] / \
                    quantity if quantity != 0 else 0
                market_price = self.get_market_price(ticker)
                if market_price is None:
                    print(f"Could not retrieve market price for {ticker}.")
                    continue
                if quantity > 0:
                    pnl = (market_price - avg_price) * quantity
                    print(
                        f"Owned: {data['name']} ({ticker}) - Avg Purchase: ${avg_price:.2f}, Market: ${market_price:.2f}, Quantity: {quantity}, P&L: ${pnl:.2f}")
                else:
                    pnl = (avg_price - market_price) * abs(quantity)
                    print(
                        f"Short: {data['name']} ({ticker}) - Avg Sale: ${avg_price:.2f}, Market: ${market_price:.2f}, Quantity: {quantity}, P&L: ${pnl:.2f}")
        else:
            print("No transactions to display.")

    def sell_asset_loop(self, portfolio_id):
        while True:
            ticker = input(
                "Enter stock ticker to sell/short (or type 'exit' to quit): ").upper()
            if ticker == "EXIT":
                break
            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]
                market_price = self.get_market_price(ticker)
                if market_price is None:
                    print(
                        f"Could not retrieve market price for {ticker}. Please try again.")
                    continue

                print(f"\nAsset found: {asset_name} ({ticker})")
                print(f"Current market price: ${market_price:.2f}")
                confirm = input(
                    f"Do you want to sell/short {asset_name} ({ticker})? (y/n): ").lower()
                if confirm == 'y':
                    historical = input(
                        "Do you want to record a historical transaction? (y/n): ").lower()
                    if historical == 'y':
                        transaction_date = input(
                            "Enter transaction date (YYYY-MM-DD): ")
                        order_type = input(
                            "Enter order type (market/limit): ").lower()
                        if order_type == 'limit':
                            limit_price = float(input("Enter limit price: "))
                            price = limit_price
                        elif order_type == 'market':
                            price = self.get_historical_price(
                                ticker, transaction_date)
                            if price is None:
                                print(
                                    "Error fetching historical market price. Transaction canceled.")
                                continue
                            limit_price = None
                        else:
                            print("Invalid order type. Please try again.")
                            continue
                        quantity = int(input("Enter quantity to sell/short: "))
                        # Record the sale/short as a negative quantity.
                        self.db.insert_transaction(
                            portfolio_id, ticker, asset_name, transaction_date, order_type, price, -quantity, limit_price)
                        print(
                            f"Recorded historical sale/short of {quantity} shares of {ticker} on {transaction_date} at ${price:.2f}.")
                    else:
                        from datetime import date
                        transaction_date = str(date.today())
                        order_type = input(
                            "Enter order type (market/limit): ").lower()
                        if order_type == 'limit':
                            limit_price = float(input("Enter limit price: "))
                            price = limit_price
                        elif order_type == 'market':
                            price = market_price
                            limit_price = None
                        else:
                            print("Invalid order type. Please try again.")
                            continue
                        quantity = int(input("Enter quantity to sell/short: "))
                        self.db.insert_transaction(
                            portfolio_id, ticker, asset_name, transaction_date, order_type, price, -quantity, limit_price)
                        print(
                            f"Successfully recorded sale/short of {quantity} shares of {ticker} at ${price:.2f} on {transaction_date}.")
                        break
                else:
                    print("Sell/Short transaction canceled.")
            else:
                print("\nNo matching ticker found. Here are some suggested tickers:")
                self.validate_ticker(ticker)

    def validate_ticker(self, ticker):
        """Suggests matching tickers for a given partial input."""
        matches = [valid_ticker for valid_ticker in self.valid_tickers if valid_ticker.startswith(
            ticker.upper())]
        if matches:
            print("Matching tickers:")
            for match in matches:
                print(f"{match} - {self.valid_tickers[match]['name']}")
        else:
            print("No matching tickers found.")
        return matches

    def export_portfolio(self, portfolio_id, filename="portfolio_export.csv"):
        """Exports the portfolio details to a CSV file."""
        positions = self.db.check_portfolio(portfolio_id)
        if positions:
            try:
                with open(filename, "w", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(
                        ["Ticker", "Name", "Quantity", "Avg Purchase Price"])
                    for ticker, data in positions.items():
                        if data["quantity"] != 0:
                            avg_price = data["total_cost"] / data["quantity"]
                            writer.writerow(
                                [ticker, data["name"], data["quantity"], avg_price])
                print(f"Portfolio exported to {filename}")
            except Exception as e:
                print(f"Error exporting portfolio: {e}")
        else:
            print("No transactions to export.")
    


    def visualise_portfolio(self, portfolio_id):
        """
        Creates a side-by-side visualization:
        - Left: A bar chart showing current portfolio performance (using check_portfolio).
        - Right: A time series chart displaying, over time, total portfolio value, net deposits, and total returns.
        """
        # ----- Left: Current Portfolio Bar Chart -----

        def _get_price_from_series(series, current_date):
            """
            Given a DataFrame of historical data (with a DateTimeIndex and 'Close' column)
            and a current_date (datetime.date), returns the as-of closing price.
            """
            ts = pd.Timestamp(current_date)
            price = series['Close'].asof(ts)
            # If asof returns a Series, get the first element
            if isinstance(price, pd.Series):
                price = price.iloc[0]
            return price
        def _fetch_time_series(ticker, start_date, end_date, interval="1d"):
            """
            Fetches the full time series for a ticker using yf.download.
            If no data is returned for the provided end_date, it adjusts the end_date backward until data is found.
            Returns a DataFrame.
            """
            data = yf.download(ticker, start=start_date,
                            end=end_date, interval=interval)
            original_end = end_date
            while data.empty:
                end_dt = datetime.datetime.strptime(
                    end_date, "%Y-%m-%d") - datetime.timedelta(days=1)
                end_date = end_dt.strftime("%Y-%m-%d")
                if end_date <= start_date:
                    break
                data = yf.download(ticker, start=start_date,
                                end=end_date, interval=interval)
            if data.empty:
                print(
                    f"Error: No data found for {ticker} from {start_date} to {original_end}.")
            return data
        positions = self.db.check_portfolio(portfolio_id)
        tickers = []
        current_values = []
        for ticker, data in positions.items():
            if data["quantity"] == 0:
                continue
            market_price = self.get_market_price(ticker)
            if market_price is None:
                continue
            tickers.append(ticker)
            current_values.append(market_price * data["quantity"])

        # ----- Right: Time Series Chart -----
        # Retrieve all transactions (ordered by date)
        self.db.cursor.execute(
            "SELECT transaction_date, ticker, price, quantity FROM transactions WHERE portfolio_id = ? ORDER BY transaction_date, id",
            (portfolio_id,))
        transactions = self.db.cursor.fetchall()
        if not transactions:
            print("No transactions found for time series visualization.")
            return

        # Parse transactions into a list of (date, ticker, price, quantity)
        transactions_parsed = []
        for t in transactions:
            trans_date = datetime.datetime.strptime(t[0], "%Y-%m-%d").date()
            transactions_parsed.append((trans_date, t[1], t[2], t[3]))

        # Determine overall date range: earliest transaction date to today
        start_date = min(t[0] for t in transactions_parsed)
        end_date = datetime.date.today()
        date_list = [start_date + datetime.timedelta(days=i)
                    for i in range((end_date - start_date).days + 1)]

        # Pre-fetch time series data for each ticker involved
        ticker_series = {}
        start_str = start_date.strftime("%Y-%m-%d")
        # yf.download uses an exclusive end date; add one day to include today
        end_str = (end_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        tickers_involved = set(t[1] for t in transactions_parsed)
        for ticker in tickers_involved:
            ts_data = _fetch_time_series(ticker, start_str, end_str, interval="1d")
            if not ts_data.empty:
                ts_data.index = pd.to_datetime(ts_data.index)
                ticker_series[ticker] = ts_data
            else:
                print(f"Warning: No historical data for {ticker}.")

        ts_dates = []
        total_values = []
        net_deposits_list = []
        total_returns_list = []
        for current_date in date_list:
            # Compute cumulative net deposits and positions up to current_date
            net_deposits = 0.0
            positions_ts = {}
            for trans in transactions_parsed:
                if trans[0] <= current_date:
                    net_deposits += trans[2] * trans[3]
                    positions_ts[trans[1]] = positions_ts.get(
                        trans[1], 0) + trans[3]
            portfolio_value = 0.0
            for ticker, quantity in positions_ts.items():
                if quantity == 0:
                    continue
                if ticker in ticker_series:
                    price = _get_price_from_series(
                        ticker_series[ticker], current_date)
                    if pd.isna(price):
                        price = ticker_series[ticker]['Close'].dropna().iloc[-1]
                    if price is not None:
                        portfolio_value += price * quantity
            total_return = portfolio_value - net_deposits
            ts_dates.append(current_date)
            total_values.append(portfolio_value)
            net_deposits_list.append(net_deposits)
            total_returns_list.append(total_return)

        # ----- Plotting Side by Side -----
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))

        # Left subplot: Current Portfolio Bar Chart
        axes[0].bar(tickers, current_values, color='skyblue')
        axes[0].set_xlabel("Ticker")
        axes[0].set_ylabel("Current Value ($)")
        axes[0].set_title("Portfolio Current Performance")

        # Right subplot: Time Series Chart
        axes[1].plot(ts_dates, total_values, label="Total Value")
        axes[1].plot(ts_dates, net_deposits_list, label="Net Deposits")
        axes[1].plot(ts_dates, total_returns_list, label="Total Returns")
        axes[1].set_xlabel("Date")
        axes[1].set_ylabel("Amount ($)")
        axes[1].set_title("Portfolio Performance Over Time")
        axes[1].legend()

        plt.tight_layout()
        plt.show()

        

    def diversification_analysis(self, portfolio_id):
        """
        Analyzes diversification by computing the current value per sector.
        Uses the 'GICS Sector' from the CSV file and displays a breakdown and pie chart.
        """
        positions = self.db.check_portfolio(portfolio_id)
        if not positions:
            print("No transactions to analyze for diversification.")
            return

        sector_values = {}
        total_value = 0
        for ticker, data in positions.items():
            if data["quantity"] == 0:
                continue
            market_price = self.get_market_price(ticker)
            if market_price is None:
                continue
            value = market_price * data["quantity"]
            total_value += value
            if ticker in self.valid_tickers:
                sector = self.valid_tickers[ticker].get("sector", "Unknown")
            else:
                sector = "Unknown"
            sector_values[sector] = sector_values.get(sector, 0) + value

        print("\nDiversification Analysis:")
        for sector, value in sector_values.items():
            percentage = (value / total_value * 100) if total_value != 0 else 0
            print(f"{sector}: ${value:.2f} ({percentage:.2f}%)")

        labels = list(sector_values.keys())
        sizes = [value for value in sector_values.values()]
        plt.figure(figsize=(8, 8))
        plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
        plt.title("Portfolio Diversification by Sector")
        plt.axis('equal')
        plt.show()

    


if __name__ == "__main__":
    manager = PortfolioManager()

    name = input("Enter your name: ")
    user_id = manager.login(name) or manager.register(name)

    portfolio_name = f"{name}'s Portfolio"
    portfolio_id = manager.create_portfolio(user_id, portfolio_name)

    while True:
        print("\nOptions: \n1) Buy Stock   \n2) Sell/Short Sell Stock \n3) Check Portfolio   \n4) Visualize Portfolio  \n5) Diversification Analysis  \n6) Export Portfolio \n7) Exit")
        choice = input("Enter choice: ")

        if choice == "1":
            manager.buy_loop(portfolio_id)
        elif choice == "2":
            manager.sell_asset_loop(portfolio_id)
        elif choice == "3":
            manager.check_portfolio(portfolio_id)
        elif choice == "4":
            manager.visualise_portfolio(portfolio_id)
        elif choice == "5":
            manager.diversification_analysis(portfolio_id)
        elif choice == "6":
            manager.export_portfolio(portfolio_id)
        elif choice == "7":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please enter a valid option.")
