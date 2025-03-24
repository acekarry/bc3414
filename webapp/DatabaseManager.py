import os
import sqlite3
import datetime
import csv
import yfinance as yf
from flask import g
import hashlib

class Person:
    def __init__(self, user_id, name):
        self.user_id = user_id
        self.name = name

class DatabaseManager:
    def __init__(self, db_name="portfolio.db"):
        self.db_name = db_name
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, db_name)

        conn = sqlite3.connect(db_path, check_same_thread=False)
        cursor = conn.cursor()
        self.create_tables(cursor)

    def get_connection(self):
        if 'db' not in g:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            db_path = os.path.join(base_dir, self.db_name)
            g.db = sqlite3.connect(db_path, check_same_thread=False)
        return g.db

    def get_cursor(self):
        return self.get_connection().cursor()

    def create_tables(self, cursor):
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                                id INTEGER PRIMARY KEY, 
                                first_name TEXT,
                                last_name TEXT,
                                username TEXT UNIQUE, 
                                password TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS portfolios (
                                id INTEGER PRIMARY KEY, 
                                owner_id INTEGER UNIQUE, 
                                name TEXT, 
                                FOREIGN KEY(owner_id) REFERENCES users(id))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
                                id INTEGER PRIMARY KEY,
                                portfolio_id INTEGER,
                                ticker TEXT,
                                name TEXT,
                                transaction_date TEXT,
                                order_type TEXT,
                                price REAL,
                                quantity INTEGER,
                                limit_price REAL,
                                FOREIGN KEY(portfolio_id) REFERENCES portfolios(id))''')

    def register_user(self, first_name, last_name, username, password):
        conn = self.get_connection()
        cursor = conn.cursor()

        # Hash the password for security
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        try:
            cursor.execute("INSERT INTO users (first_name, last_name, username, password) VALUES (?, ?, ?, ?)", 
                           (first_name, last_name, username, hashed_password))
            conn.commit()
            user_id = cursor.lastrowid
            return Person(user_id, first_name + ' ' + last_name)
        except sqlite3.IntegrityError:
            print("Username already exists. Please try a different one.")
            return None

    def login_user(self, username, password):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, first_name, last_name, password FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            # Check password
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            if hashed_password == row[3]:
                return Person(row[0], row[1] + ' ' + row[2])
            else:
                print("Login failed: Incorrect password.")
                return None
        else:
            print("Login failed: User not found.")
            return None

    def insert_portfolio(self, owner_id, name):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO portfolios (owner_id, name) VALUES (?, ?)", (owner_id, name))
        conn.commit()
        return cursor.lastrowid

    def retrieve_portfolio(self, owner_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM portfolios WHERE owner_id = ?", (owner_id,))
        existing_portfolio = cursor.fetchone()
        return existing_portfolio

    def insert_transaction(self, portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO transactions (portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price))
        conn.commit()
        return cursor.lastrowid

    def check_portfolio(self, portfolio_id, export=False):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT ticker, name, transaction_date, order_type, price, quantity, limit_price \
             FROM transactions \
             WHERE portfolio_id = ? \
             ORDER BY transaction_date, id",
            (portfolio_id,))
        transactions = cursor.fetchall()
        if not transactions:
            print("\nNo transactions found in this portfolio.")
            return {}
        if export:
            return transactions

        positions = {}
        for t in transactions:
            ticker, name, t_date, order_type, price, quantity, limit_price = t
            if ticker not in positions:
                positions[ticker] = {"name": name, "quantity": 0, "total_cost": 0.0}
            if quantity > 0:
                positions[ticker]["quantity"] += quantity
                positions[ticker]["total_cost"] += price * quantity
            else:
                existing_quantity = positions[ticker]["quantity"]
                if existing_quantity > 0:
                    avg_cost = positions[ticker]["total_cost"] / existing_quantity
                else:
                    avg_cost = 0
                positions[ticker]["quantity"] += quantity
                if positions[ticker]["quantity"] >= 0:
                    positions[ticker]["total_cost"] += avg_cost * quantity
                else:
                    positions[ticker]["total_cost"] = price * positions[ticker]["quantity"]

        return positions

    def load_valid_tickers(self, filename="SnP_tickers_sector.csv"):
        tickers = {}
        if not os.path.isfile(filename):
            print(f"Error: File {filename} not found.")
            return tickers
        try:
            with open(filename, 'r') as file:
                reader = csv.reader(file)
                headers = next(reader, None)
                for row in reader:
                    ticker = row[0].strip().upper()
                    name = row[1].strip()
                    sector = row[2].strip() if len(row) > 2 else "Unknown"
                    tickers[ticker] = {"name": name, "sector": sector}
        except FileNotFoundError:
            print(f"File {filename} not found.")
        return tickers
