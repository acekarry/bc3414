import os
import sqlite3
import datetime
import csv
import yfinance as yf

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
