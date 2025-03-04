from PortfolioManager import PortfolioManager

if __name__ == "__main__":
    manager = PortfolioManager()

    name = input("Enter your name: ").strip().lower()
    user_id = manager.login(name) or manager.register(name)

    portfolio_name = f"{name}'s Portfolio"
    portfolio_id = manager.create_portfolio(user_id, portfolio_name)

    while True:
        print("\nOptions: \n1) Buy Stock   \n2) Sell/Short Sell Stock \n3) Add historical transanction\n4) Check Portfolio   \n5) Visualize Portfolio  \n6) Diversification Analysis  \n7) Export Portfolio \n8) Import Portfolio\n9) Exit")
        choice = input("Enter choice: ")

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
            manager.export_portfolio(portfolio_id)
        elif choice == "8":
            manager.import_portfolio(portfolio_id)
        elif choice == "9":
            print("Exiting...")
            break
        else:
            print("Invalid choice. Please enter a valid option.")
