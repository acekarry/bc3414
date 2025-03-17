from DatabaseManager import DatabaseManager
from NewsScraper import NewsScraper
import datetime
import csv
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from thefuzz import process
from thefuzz import fuzz
import tkinter as tk
from tkinter.filedialog import askopenfilename
from datetime import date


class PortfolioManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.valid_tickers = self.db.load_valid_tickers()

    def register(self, name):
        return self.db.register_user(name)

    def login(self, name):
        return self.db.login_user(name)

    def get_price(self, ticker, transaction_date=None):
        """
        Fetch the market price for a given ticker.

        If transaction_date (in "YYYY-MM-DD" format) is provided, this method
        returns the closing price on that day or, if data is missing,
        on the nearest previous trading day (up to a maximum lookback).
        If transaction_date is not provided, it returns the latest available market price.
        """
        try:
            stock = yf.Ticker(ticker)
            # Determine the target date: use provided transaction_date or default to today.
            if transaction_date:
                target_date = datetime.datetime.strptime(
                    transaction_date, "%Y-%m-%d")
            else:
                target_date = datetime.datetime.today()

            # Maximum number of days to look back for available data.
            max_lookback = 10
            days_back = 1
            price = None
            used_date = None

            # Loop backwards until we find trading data.
            while days_back < max_lookback:
                current_date = target_date - datetime.timedelta(days=days_back)
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
                    f"Error: No trading data found for {ticker} within {max_lookback} days of {target_date.strftime('%Y-%m-%d')}.")
                return None

            # Notify if the fetched data is from a date different than requested.
            if transaction_date and used_date != transaction_date:
                print(
                    f"{ticker}: No data on {transaction_date}. Using data from nearest trading day: {used_date}.")

            return price
        except Exception as e:
            print(f"Error fetching market data for {ticker}: {e}")
            return None

    def create_portfolio(self, owner_id, name):
        cursor = self.db.get_cursor()
        cursor.execute(
            "SELECT id FROM portfolios WHERE owner_id = ?", (owner_id,))
        existing_portfolio = cursor.fetchone()

        if existing_portfolio:
            print(
                f"User already has a portfolio with ID {existing_portfolio[0]}.")
            return existing_portfolio[0]
        else:
            return self.db.insert_portfolio(owner_id, name)

    def add_historical(self, portfolio_id, ticker, transaction_date, price, quantity):
        if ticker in self.valid_tickers:
            asset_name = self.valid_tickers[ticker]["name"]
            order_type = "historical"
            limit_price = None
            self.db.insert_transaction(
                portfolio_id, ticker, asset_name, transaction_date, order_type, price, quantity, limit_price)
            return True
        return False

    def buy_stock(self, portfolio_id, ticker, quantity, order_type="market", limit_price=None):
        if ticker in self.valid_tickers:
            asset_name = self.valid_tickers[ticker]["name"]
            market_price = self.get_price(ticker)

            if market_price is None:
                return False, "Could not retrieve market price"

            transaction_date = str(date.today())

            if order_type == 'limit':
                price = limit_price
            else:  # market order
                price = market_price
                limit_price = None

            self.db.insert_transaction(
                portfolio_id, ticker, asset_name, transaction_date, order_type, price, quantity, limit_price)
            return True, f"Successfully purchased {quantity} shares of {ticker} at ${price:.2f}"
        return False, "Invalid ticker"

    def sell_stock(self, portfolio_id, ticker, quantity, order_type="market", limit_price=None):
        if ticker in self.valid_tickers:
            asset_name = self.valid_tickers[ticker]["name"]
            market_price = self.get_price(ticker)

            if market_price is None:
                return False, "Could not retrieve market price"

            transaction_date = str(date.today())

            if order_type == 'limit':
                price = limit_price
            else:  # market order
                price = market_price
                limit_price = None

            # Negative quantity for selling
            self.db.insert_transaction(portfolio_id, ticker, asset_name,
                                       transaction_date, order_type, price, -quantity, limit_price)
            return True, f"Successfully sold {quantity} shares of {ticker} at ${price:.2f}"
        return False, "Invalid ticker"

    def check_portfolio(self, portfolio_id):
        positions = self.db.check_portfolio(portfolio_id)
        if positions:
            processed_positions = {}
            total_long_val = 0
            total_short_val = 0
            total_long_pnl = 0
            total_short_pnl = 0

            for ticker, data in positions.items():
                quantity = data["quantity"]
                if quantity == 0:
                    continue

                # For shorts, show a positive average entry price.
                if quantity < 0:
                    avg_price = abs(data["total_cost"]) / abs(quantity)
                else:
                    avg_price = data["total_cost"] / abs(quantity)

                market_price = self.get_price(ticker)
                if market_price is None:
                    print(f"Could not retrieve market price for {ticker}.")
                    continue

                current_val = market_price * quantity

                if quantity > 0:
                    pnl = (market_price - avg_price) * quantity
                    pos_type = "Long"
                    total_long_val += current_val
                    total_long_pnl += pnl
                else:
                    pnl = (avg_price - market_price) * abs(quantity)
                    pos_type = "Short"
                    total_short_val += current_val
                    total_short_pnl += pnl

                processed_positions[ticker] = {
                    "name": data['name'],
                    "quantity": quantity,
                    "avg_price": avg_price,
                    "market_price": market_price,
                    "current_value": current_val,
                    "pnl": pnl,
                    "position_type": pos_type
                }

            summary = {
                "total_long_value": total_long_val,
                "total_short_value": total_short_val,
                "total_value": total_long_val + total_short_val,
                "total_long_pnl": total_long_pnl,
                "total_short_pnl": total_short_pnl,
                "total_pnl": total_long_pnl + total_short_pnl
            }

            return processed_positions, summary
        return {}, {"total_value": 0, "total_pnl": 0}

    def compute_annualized_return(self, initial_investment, final_value, years):
        if years <= 0 or initial_investment <= 0:
            return None
        return (final_value / initial_investment) ** (1 / years) - 1

    def portfolio_performance(self, portfolio_id):
        """ 
        Computes annualized return separately for long and short positions,
        then combines them for total portfolio performance.
        """
        try:
            # Retrieve the earliest transaction date for this portfolio.
            cursor = self.db.get_cursor()
            cursor.execute(
                "SELECT MIN(transaction_date) FROM transactions WHERE portfolio_id = ?",
                (portfolio_id,))
            earliest_date_str = cursor.fetchone()[0]

            if not earliest_date_str:
                return None

            earliest_date = datetime.datetime.strptime(
                earliest_date_str, "%Y-%m-%d")
            # Use local time for performance calculations.
            today_local = datetime.datetime.today()
            years = (today_local - earliest_date).days / 365.25

            positions, summary = self.check_portfolio(portfolio_id)
            total_long_val = summary["total_long_value"]
            total_short_val = summary["total_short_value"]
            total_long_pnl = summary["total_long_pnl"]
            total_short_pnl = summary["total_short_pnl"]
            total_val = summary["total_value"]
            total_pnl = summary["total_pnl"]

            performance_data = {}

            # Compute annualized return for long positions, if any.
            if total_long_val > 0:
                initial_long_investment = total_long_val - total_long_pnl
                annualized_long_return = self.compute_annualized_return(
                    initial_long_investment, total_long_val, years)
                if annualized_long_return is not None:
                    performance_data["long_annual_return"] = annualized_long_return * 100
            else:
                performance_data["long_annual_return"] = None

            # Compute annualized return for short positions, if any.
            if total_short_val < 0:
                # For shorts, initial proceeds are the absolute value of (total_short_val - total_short_pnl).
                initial_short_investment = abs(
                    total_short_val - total_short_pnl)
                annualized_short_return = self.compute_annualized_return(
                    initial_short_investment, abs(total_short_val), years)
                if annualized_short_return is not None:
                    performance_data["short_annual_return"] = annualized_short_return * 100
            else:
                performance_data["short_annual_return"] = None

            # Combined portfolio performance (using absolute values so that shorts are treated correctly).
            initial_total_investment = abs(total_val - total_pnl)
            annualized_total_return = self.compute_annualized_return(
                initial_total_investment, abs(total_val), years)

            if annualized_total_return is not None:
                performance_data["total_annual_return"] = annualized_total_return * 100
            else:
                performance_data["total_annual_return"] = None

            return performance_data

        except Exception as e:
            print(f"Error computing annualized returns: {e}")
            return None

    def validate_ticker(self, ticker):
        """Suggests matching tickers for a given partial input or stock name."""
        matches = [valid_ticker for valid_ticker in self.valid_tickers if valid_ticker.startswith(
            ticker.upper())]
        if matches:
            return matches, [(ticker, self.valid_tickers[ticker]['name']) for ticker in matches]
        else:
            top_matches = process.extract(
                ticker, [i['name'] for i in self.valid_tickers.values()], scorer=fuzz.ratio, limit=5)
            return [], [(k, self.valid_tickers[k]['name']) for match in top_matches
                        for k, v in self.valid_tickers.items() if v['name'] == match[0]]

    def export_portfolio(self, portfolio_id, filename="portfolio_export.csv"):
        """Exports the portfolio details to a CSV file."""
        transactions = self.db.check_portfolio(portfolio_id, export=True)
        if transactions:
            try:
                with open(filename, "w", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(
                        ["ticker", "name", "transaction_date", "order_type", "price", "quantity", "limit_price"])
                    for data in transactions:
                        writer.writerow(data)
                return True, f"Portfolio exported to {filename}"
            except Exception as e:
                return False, f"Error exporting portfolio: {e}"
        else:
            return False, "No transactions to export."

    def import_portfolio(self, portfolio_id, filename):
        """Imports the portfolio details from a CSV file."""
        try:
            with open(filename, "r") as csvfile:
                reader = csv.reader(csvfile)
                headers = next(reader)  # Skip the header row
                for row in reader:
                    ticker, name, transaction_date, order_type, price, quantity, limit_price = row
                    price = float(price)
                    quantity = int(quantity)
                    self.db.insert_transaction(
                        portfolio_id, ticker, name, transaction_date, order_type, price, quantity, limit_price)
                return True, f"Portfolio imported from {filename}"
        except FileNotFoundError:
            return False, f"File {filename} not found."
        except Exception as e:
            return False, f"Error importing portfolio: {e}"
