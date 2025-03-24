from pPortfolioManager import PortfolioManager
from StockExplorer import StockExplorer
from InputValidator import validate_input

if __name__ == "__main__":
    manager = PortfolioManager()
    explorer = StockExplorer()

    while True:
        name = input("Enter your name: ").strip().lower()

        if not name:
            print("Error: Name cannot be empty. Please enter a valid name.")
        elif any(char.isdigit() for char in name):
            print("Error: Name cannot contain numbers. Try again.")
        elif not all(char.isalpha() or char.isspace() for char in name):
            print("Error: Name can only contain letters and spaces. Try again.")
        else:
            break  

    user = manager.login(name) or manager.register(name)
    user_id = user.user_id

    portfolio_name = f"{name}'s Portfolio"
    portfolio_id = manager.create_portfolio(user_id, portfolio_name)

    while True:
        print("\nOptions: \n1) Buy Stock   \n2) Sell/Short Sell Stock \n3) Add historical transanction\n4) Check Portfolio   \n5) Visualize Portfolio  \n6) Diversification Analysis \n7) Explore Stocks\n8) Import Portfolio\n9) Export Portfolio\n10) Exit")
        choice = validate_input("Enter choice: ", str)

        if choice == "1":
            manager.buy_loop(portfolio_id)
        elif choice == "2":
            manager.sell_asset_loop(portfolio_id)
        elif choice == "3":
            manager.add_historical(portfolio_id)
        elif choice == "4":
            manager.check_portfolio(portfolio_id)
        elif choice == "5":
            manager.visualise_portfolio(portfolio_id)
        elif choice == "6":
            manager.diversification_analysis(portfolio_id)
        elif choice == "7":
            explorer.menu()
        elif choice == "8":
            manager.import_portfolio(portfolio_id) 
        elif choice == "9":
            manager.export_portfolio(portfolio_id)
        elif choice == "10":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please enter a valid option.")
