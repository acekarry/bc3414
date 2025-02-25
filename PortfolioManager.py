from DatabaseManager import DatabaseManager
from NewsScraper import NewsScraper
import datetime
import csv
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf
from datetime import date   

class PortfolioManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.valid_tickers = self.db.load_valid_tickers()
        self.news_scraper = NewsScraper()  # Instantiate the news scraper

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
                target_date = datetime.datetime.strptime(transaction_date, "%Y-%m-%d")
            else:
                target_date = datetime.datetime.today()
            
            max_lookback = 10  # Maximum number of days to look back for available data.
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
                print(f"Error: No trading data found for {ticker} within {max_lookback} days of {target_date.strftime('%Y-%m-%d')}.")
                return None

            # Notify if the fetched data is from a date different than requested.
            if transaction_date and used_date != transaction_date:
                print(f"{ticker}: No data on {transaction_date}. Using data from nearest trading day: {used_date}.")

            return price
        except Exception as e:
            print(f"Error fetching market data for {ticker}: {e}")
            return None

    def create_portfolio(self, owner_id, name):
        self.db.cursor.execute("SELECT id FROM portfolios WHERE owner_id = ?", (owner_id,))
        existing_portfolio = self.db.cursor.fetchone()

        if existing_portfolio:
            print(f"User already has a portfolio with ID {existing_portfolio[0]}.")
            return existing_portfolio[0]
        else:
            return self.db.insert_portfolio(owner_id, name)

    def add_historical(self, portfolio_id):
        while True:
            ticker = input("Enter stock ticker (or type 'exit' to quit): ").upper()
            if ticker == "EXIT":
                break

            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]

                confirm = input(f"Stock requested - {asset_name} ({ticker})? (y/n): ").lower()
                if confirm == 'y':
                    transaction_date = input("Enter transaction date (YYYY-MM-DD): ")
                    price = float(input("Enter price you bought at: "))
                    quantity = int(input("Enter quantity: "))
                    order_type = "historical"
                    limit_price = None
                    self.db.insert_transaction(portfolio_id, ticker, asset_name, transaction_date, order_type, price, quantity, limit_price)
                    print(f"Recorded historical purchase of {quantity} shares of {ticker} on {transaction_date} at ${price:.2f}.")
                    return
                else:
                    print("Transaction canceled.")
                    self.validate_ticker(ticker)
            else:
                print("\nNo matching ticker found. Here are some suggested tickers:")
                self.validate_ticker(ticker)

    def buy_loop(self, portfolio_id):
        while True:
            ticker = input("Enter stock ticker (or type 'exit' to quit): ").upper()
            if ticker == "EXIT":
                break

            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]
                # For current transactions, call get_price without a date.
                market_price = self.get_price(ticker)
                if market_price is None:
                    print(f"Could not retrieve market price for {ticker}. Please try again.")
                    continue

                print(f"\nStock found: {ticker} - {asset_name}")
                print(f"Current market price: ${market_price:.2f}")

                
                self.news_scraper.show_news(asset_name)
                confirm = input(f"Do you want to buy {asset_name} ({ticker})? (y/n): ").lower()
                if confirm == 'y':
                    # For current transactions, use today's date.
                    transaction_date = str(date.today())
                    order_type = input("Enter order type (market/limit): ").lower()
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
                    self.db.insert_transaction(portfolio_id, ticker, asset_name, transaction_date, order_type, price, quantity, limit_price)
                    print(f"Successfully recorded purchase of {quantity} shares of {ticker} at ${price:.2f} on {transaction_date}.")
                else:
                    print("Buy transaction canceled.")
                    self.validate_ticker(ticker)
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
                avg_price = data["total_cost"] / quantity if quantity != 0 else 0
                market_price = self.get_price(ticker)
                if market_price is None:
                    print(f"Could not retrieve market price for {ticker}.")
                    continue
                if quantity > 0:
                    pnl = (market_price - avg_price) * quantity
                    print(f"Owned: {data['name']} ({ticker}) - Avg Purchase: ${avg_price:.2f}, Market: ${market_price:.2f}, Quantity: {quantity}, P&L: ${pnl:.2f}")
                else:
                    pnl = (avg_price - market_price) * abs(quantity)
                    print(f"Short: {data['name']} ({ticker}) - Avg Sale: ${avg_price:.2f}, Market: ${market_price:.2f}, Quantity: {quantity}, P&L: ${pnl:.2f}")
        else:
            print("No transactions to display.")

    def sell_asset_loop(self, portfolio_id):
        while True:
            ticker = input("Enter stock ticker to sell/short (or type 'exit' to quit): ").upper()
            if ticker == "EXIT":
                break
            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]
                market_price = self.get_price(ticker)
                if market_price is None:
                    print(f"Could not retrieve market price for {ticker}. Please try again.")
                    continue

                print(f"\nAsset found: {asset_name} ({ticker})")
                print(f"Current market price: ${market_price:.2f}")
                confirm = input(f"Do you want to sell/short {asset_name} ({ticker})? (y/n): ").lower()
                if confirm == 'y':
                    historical = input("Do you want to record a historical transaction? (y/n): ").lower()
                    if historical == 'y':
                        transaction_date = input("Enter transaction date (YYYY-MM-DD): ")
                        order_type = input("Enter order type (market/limit): ").lower()
                        if order_type == 'limit':
                            limit_price = float(input("Enter limit price: "))
                            price = limit_price
                        elif order_type == 'market':
                            price = self.get_price(ticker, transaction_date)
                            if price is None:
                                print("Error fetching historical market price. Transaction canceled.")
                                continue
                            limit_price = None
                        else:
                            print("Invalid order type. Please try again.")
                            continue
                        quantity = int(input("Enter quantity to sell/short: "))
                        # Record the sale/short as a negative quantity.
                        self.db.insert_transaction(portfolio_id, ticker, asset_name, transaction_date, order_type, price, -quantity, limit_price)
                        print(f"Recorded historical sale/short of {quantity} shares of {ticker} on {transaction_date} at ${price:.2f}.")
                    else:
                        from datetime import date
                        transaction_date = str(date.today())
                        order_type = input("Enter order type (market/limit): ").lower()
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
                        self.db.insert_transaction(portfolio_id, ticker, asset_name, transaction_date, order_type, price, -quantity, limit_price)
                        print(f"Successfully recorded sale/short of {quantity} shares of {ticker} at ${price:.2f} on {transaction_date}.")
                        break
                else:
                    print("Sell/Short transaction canceled.")
                    self.validate_ticker(ticker)
            else:
                print("\nNo matching ticker found. Here are some suggested tickers:")
                self.validate_ticker(ticker)

    def validate_ticker(self, ticker):
        """Suggests matching tickers for a given partial input."""
        matches = [valid_ticker for valid_ticker in self.valid_tickers if valid_ticker.startswith(ticker.upper())]
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
                    writer.writerow(["Ticker", "Name", "Quantity", "Avg Purchase Price"])
                    for ticker, data in positions.items():
                        if data["quantity"] != 0:
                            avg_price = data["total_cost"] / data["quantity"]
                            writer.writerow([ticker, data["name"], data["quantity"], avg_price])
                print(f"Portfolio exported to {filename}")
            except Exception as e:
                print(f"Error exporting portfolio: {e}")
        else:
            print("No transactions to export.")

    def visualise_portfolio(self, portfolio_id):
        """
        Creates a side-by-side visualization:
        - Left: A bar chart showing current portfolio performance.
        - Right: A time series chart displaying, over time, total portfolio value, net deposits, and total returns.
        """
        # ----- Left: Current Portfolio Bar Chart -----
        def _get_price_from_series(series, current_date):
            ts = pd.Timestamp(current_date)
            price = series['Close'].asof(ts)
            if isinstance(price, pd.Series):
                price = price.iloc[0]
            return price

        def _fetch_time_series(ticker, start_date, end_date, interval="1d"):
            data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
            original_end = end_date
            while data.empty:
                end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d") - datetime.timedelta(days=1)
                end_date = end_dt.strftime("%Y-%m-%d")
                if end_date <= start_date:
                    break
                data = yf.download(ticker, start=start_date, end=end_date, interval=interval)
            if data.empty:
                print(f"Error: No data found for {ticker} from {start_date} to {original_end}.")
            return data

        positions = self.db.check_portfolio(portfolio_id)
        tickers = []
        current_values = []
        for ticker, data in positions.items():
            if data["quantity"] == 0:
                continue
            market_price = self.get_price(ticker)
            if market_price is None:
                continue
            tickers.append(ticker)
            current_values.append(market_price * data["quantity"])

        # ----- Right: Time Series Chart -----
        self.db.cursor.execute(
            "SELECT transaction_date, ticker, price, quantity FROM transactions WHERE portfolio_id = ? ORDER BY transaction_date, id",
            (portfolio_id,)
        )
        transactions = self.db.cursor.fetchall()
        if not transactions:
            print("No transactions found for time series visualization.")
            return

        transactions_parsed = []
        for t in transactions:
            trans_date = datetime.datetime.strptime(t[0], "%Y-%m-%d").date()
            transactions_parsed.append((trans_date, t[1], t[2], t[3]))

        start_date = min(t[0] for t in transactions_parsed)
        end_date = datetime.date.today()
        date_list = [start_date + datetime.timedelta(days=i) for i in range((end_date - start_date).days + 1)]

        ticker_series = {}
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (end_date + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        tickers_involved = set(t[1] for t in transactions_parsed)
        for ticker in tickers_involved:
            ts_data = _fetch_time_series(ticker, start_str, end_str, interval="1d")
            if not ts_data.empty:
                ts_data.index = pd.to_datetime(ts_data.index)
                ticker_series[ticker] = ts_data
            else:
                print(f"Warning: No historical data for {ticker}.")

        ts_dates, total_values, net_deposits_list, total_returns_list = [], [], [], []
        for current_date in date_list:
            net_deposits = 0.0
            positions_ts = {}
            for trans in transactions_parsed:
                if trans[0] <= current_date:
                    net_deposits += trans[2] * trans[3]
                    positions_ts[trans[1]] = positions_ts.get(trans[1], 0) + trans[3]
            portfolio_value = 0.0
            for ticker, quantity in positions_ts.items():
                if quantity == 0:
                    continue
                if ticker in ticker_series:
                    price = _get_price_from_series(ticker_series[ticker], current_date)
                    if pd.isna(price):
                        price = ticker_series[ticker]['Close'].dropna().iloc[-1]
                    if price is not None:
                        portfolio_value += price * quantity
            total_return = portfolio_value - net_deposits
            ts_dates.append(current_date)
            total_values.append(portfolio_value)
            net_deposits_list.append(net_deposits)
            total_returns_list.append(total_return)

        fig, axes = plt.subplots(1, 2, figsize=(16, 6))

        axes[0].bar(tickers, current_values, color='skyblue')
        axes[0].set_xlabel("Ticker")
        axes[0].set_ylabel("Current Value ($)")
        axes[0].set_title("Portfolio Current Performance")

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
            market_price = self.get_price(ticker)
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
