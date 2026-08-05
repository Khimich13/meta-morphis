from meta_morphis.meta.scraper import (
    parse_meta_table,
    scrape_meta_cards
)

def test_parse_meta_table_valid():
    html = """
    <table class="table-staples">
        <tr>
            <td>1</td>
            <td>Lightning Bolt</td>
            <td></td>
            <td>25%</td>
            <td>3.5</td>
        </tr>
    </table>
    """
    result = parse_meta_table(html)
    assert len(result) == 1
    entry = result[0]
    assert entry.name == "Lightning Bolt"
    assert entry.rank == 1
    assert entry.percent == 25.0
    assert entry.deck_count == 3.5

def test_parse_meta_table_no_table():
    html = "<html><body>No table here</body></html>"
    assert parse_meta_table(html) is None

def test_parse_meta_table_double_name():
    html = """
    <table class="table-staples">
        <tr>
            <td>1</td>
            <td>Fire // Ice</td>
            <td></td>
            <td>10%</td>
            <td>2</td>
        </tr>
    </table>
    """
    entry = parse_meta_table(html)[0]
    assert entry.name == "Fire"

def test_parse_meta_table_empty_rows():
    html = """
    <table class="table-staples">
        <tr></tr>
        <tr>
            <td>2</td>
            <td>Brainstorm</td>
            <td></td>
            <td>15%</td>
            <td>1</td>
        </tr>
    </table>
    """
    result = parse_meta_table(html)
    assert len(result) == 1

def test_scrape_meta_cards_success(monkeypatch):
    class FakeResponse:
        status_code = 200
        text = """
        <table class="table-staples">
            <tr>
                <td>1</td>
                <td>Test Card</td>
                <td></td>
                <td>5%</td>
                <td>1</td>
            </tr>
        </table>
        """

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())

    result = scrape_meta_cards("http://fake-url")
    assert len(result) == 1
    assert result[0].name == "Test Card"

def test_scrape_meta_cards_retry(monkeypatch):
    responses = [
        type("R", (), {"status_code": 500}),
        type("R", (), {"status_code": 500}),
        type("R", (), {"status_code": 200, "text": """
            <table class="table-staples">
                <tr>
                    <td>1</td>
                    <td>Test Card</td>
                    <td></td>
                    <td>5%</td>
                    <td>1</td>
                </tr>
            </table>
            """})
    ]

    def fake_get(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("time.sleep", lambda x: None)

    result = scrape_meta_cards("http://fake-url")
    assert len(result) == 1

def test_scrape_meta_cards_all_fail(monkeypatch):
    class FakeResponse:
        status_code = 500

    monkeypatch.setattr("requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("time.sleep", lambda x: None)

    assert scrape_meta_cards("http://fake-url") is None