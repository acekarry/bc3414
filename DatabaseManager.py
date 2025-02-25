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

    def insert_transaction(self, portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price=None):
        """Records a transaction (buy/sell) for the portfolio."""
        self.cursor.execute(
            """INSERT INTO transactions (portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price))
        self.conn.commit()
        return self.cursor.lastrowid

    def check_portfolio(self, portfolio_id, export=False):
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
        if export:
            return transactions
        
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
