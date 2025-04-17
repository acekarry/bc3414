from GoogleNews import GoogleNews

class NewsScraper:
    def __init__(self, lang='en', region='US'):
        self.googlenews = GoogleNews(lang=lang, region=region)

    def show_news(self, asset_name, num_results=5):
        self.googlenews.clear() 
        self.googlenews.search(asset_name)
        results = self.googlenews.results() # get top headlines
        if not results:
            print(f"No news found for {asset_name}.")
            return

        print(f"\nTop {num_results} news articles for {asset_name}: (ctrl/cmd+click to read in browser)")
        for news in results[:num_results]:
            title = news['title']
            link = news['link']
            hyperlink = f"    \033]8;;{link}\033\\{title}\033]8;;\033\\" #regex fix
            print(hyperlink, "\n")

