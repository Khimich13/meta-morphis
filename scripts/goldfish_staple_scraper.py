import requests
from bs4 import BeautifulSoup

URL = "https://www.mtggoldfish.com/format-staples/pauper/full/spells"

def scrape_staples(url: str):
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text

    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.table-staples")
    if not table:
        raise RuntimeError("Could not find staples table on page.")

    rows = table.select("tr")
    cards = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        
        mana_cost = (
            cols[2].select_one("span.manacost")
            .get("aria-label", "")
            .removeprefix("mana cost: ")
        )

        cards.append({
            "rank": int(cols[0].text.strip()),
            "card": cols[1].text.strip(),
            "mana_cost": mana_cost,
            "percentage": cols[3].text.strip(),
            "deck_count": cols[4].text.strip(),
        })

    return cards


if __name__ == "__main__":
    staples = scrape_staples(URL)
    for c in staples:
        print(c)