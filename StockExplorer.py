import pandas as pd
from InputValidator import validate_input
from NewsScraper import NewsScraper
from DatabaseManager import DatabaseManager
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter, FuzzyCompleter
import shutil
import math
import yfinance as yf


class StockExplorer:
    def __init__(self):
        # Assuming the CSV has at least these columns: "Security", "Ticker", "GICS Sector", "GICS Sub-Industry"
        self.sector_df = pd.read_csv("SnP_tickers_sector.csv").drop(
            columns=["Headquarters Location"])
        self.news_scraper = NewsScraper()
        self.db = DatabaseManager()
        self.valid_tickers = self.db.load_valid_tickers()

    def menu(self):
        """Display the main menu for stock exploration."""
        while True:
            print("\nStock Exploration Menu:")
            print("1) Explore Stock News")
            print("2) Explore Stocks by Filter")
            print("3) Exit")
            choice = validate_input(
                "Enter choice (1-3): ", int, "Invalid choice. Try again: ")
            if choice == 1:
                self.explore_news()
            elif choice == 2:
                self.explore_by_filter()
            elif choice == 3:
                print("Exiting stock exploration.")
                break

    def explore_news(self):
        """Fetch and display top news headlines for the given ticker with clickable hyperlinks."""
        while True:
            ticker = validate_input(
                "Enter ticker symbol: ", str, "Invalid ticker symbol. Try again: ").upper()
            if ticker in self.valid_tickers:
                asset_name = self.valid_tickers[ticker]["name"]
                print(f"Fetching news for {asset_name} ({ticker})...")
                self.news_scraper.show_news(asset_name)
            else:
                print(f"Error: Ticker {ticker} not found in database.")
            choice = input(
                "Type 'exit' to return to the main menu, or press Enter to explore more news: ").strip().lower()
            if choice == "exit":
                break

    def print_in_cols(self, items, sep='  '):
        """Prints a list of strings in neatly formatted columns."""
        if not items:
            return

        terminal_width = shutil.get_terminal_size().columns
        max_len = max(len(item) for item in items)
        num_cols = max(1, terminal_width // (max_len + len(sep)))
        num_rows = math.ceil(len(items) / num_cols)
        for row in range(num_rows):
            row_items = []
            for col in range(num_cols):
                index = col * num_rows + row
                if index < len(items):
                    row_items.append(items[index].ljust(max_len))
            print(sep.join(row_items))

    def explore_by_filter(self):
        """
        Explore stocks by filtering on attributes from the S&P tickers CSV file.
        Uses prompt_toolkit for an interactive fuzzy search experience.
        When filtering by Security (option 3), additional metrics are fetched from yfinance.
        """
        if self.sector_df.empty:
            print("Sector data not available.")
            return

        # Define mapping for filter options.
        # Option 3 uses the "Security" column. Note that the CSV is assumed to have a "Ticker" column.
        filter_options = {
            "1": ("GICS Sector", "sector name"),
            "2": ("GICS Sub-Industry", "sub-industry"),
            "3": ("Security", "security name"),
            "4": ("Exit", None)
        }

        while True:
            print("\nExplore Stocks by Filter (Start typing to filter):")
            print("Filter options:")
            for key, (col, _) in filter_options.items():
                if key == "4":
                    print(f"{key}) Exit")
                else:
                    print(f"{key}) {col}")

            choice = input("Enter filter choice (1-4): ").strip()
            if choice not in filter_options:
                print("Invalid choice. Try again.")
                continue

            # Exit option chosen
            if choice == "4":
                print("Exiting exploration.")
                break

            column, prompt_desc = filter_options[choice]
            # Get unique values for the chosen column
            unique_values = sorted(self.sector_df[column].dropna().unique())
            print(f"\nAvailable {column}s:")
            self.print_in_cols(unique_values)

            # Create a fuzzy completer with the unique values
            word_completer = WordCompleter(unique_values, ignore_case=True)
            fuzzy_completer = FuzzyCompleter(word_completer)

            # Use prompt_toolkit's prompt for interactive input with fuzzy completion
            selected = prompt(
                f"Enter {prompt_desc} (or partial): ", completer=fuzzy_completer).strip()

            # Filter the DataFrame based on fuzzy matching
            filtered = self.sector_df[self.sector_df[column].str.contains(
                selected, case=False, na=False)]
            if filtered.empty:
                print("No results found for your selection.")
            else:
                print("\nMatching Results:")
                print(filtered.to_string(index=False))
                if choice == "3":
                    # If multiple rows match, let the user choose which one to get metrics for.
                    if len(filtered) > 1:
                        print(
                            "\nMultiple results found. Please choose one for additional metrics:")
                        filtered = filtered.reset_index(drop=True)
                        for i, row in filtered.iterrows():
                            # Display both Security and Ticker
                            print(f"{i}) {row['Security']} ({row['Symbol']})")
                        selection = input(
                            "Enter the number corresponding to your choice: ").strip()
                        try:
                            selection = int(selection)
                            if selection < 0 or selection >= len(filtered):
                                print(
                                    "Invalid selection. Defaulting to the first result.")
                                selection = 0
                        except Exception:
                            print("Invalid input. Defaulting to the first result.")
                            selection = 0
                    else:
                        selection = 0
                    chosen = filtered.iloc[selection]
                    ticker_symbol = chosen["Symbol"]
                    print(
                        f"\nFetching additional metrics for {chosen['Security']} ({ticker_symbol})...")
                    try:
                        ticker_obj = yf.Ticker(ticker_symbol)
                        info = ticker_obj.info
                        metrics = {
                            "Market Cap": info.get("marketCap"),
                            "PE Ratio": info.get("trailingPE"),
                            "Price": info.get("regularMarketPrice"),
                            "Dividend Yield": info.get("dividendYield")
                        }
                        print("Additional metrics:")
                        for key, value in metrics.items():
                            print(f"   {key}: {value}")
                    except Exception as e:
                        print(
                            f"Could not fetch metrics for {ticker_symbol}: {e}")
            # Allow the user to filter again or exit
            cont = input(
                "\nPress Enter to perform another filter or type 'exit' to return to the main menu: ").strip().lower()
            if cont == "exit":
                break