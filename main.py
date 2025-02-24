from PortfolioManager import PortfolioManager

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
