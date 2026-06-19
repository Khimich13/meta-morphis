import requests
from bs4 import BeautifulSoup

URL = "https://www.mtggoldfish.com/format-staples/pauper/full/spells"

def scrape_staple_names():
    html = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")

    table = soup.select_one("table.table-staples")
    if not table:
        raise RuntimeError("Could not find staples table on page.")

    names = []
    for row in table.select("tr"):
        cols = row.find_all("td")
        if not cols:
            continue
        names.append(cols[1].text.strip())

    return names