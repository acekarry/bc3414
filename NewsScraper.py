from GoogleNews import GoogleNews

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

