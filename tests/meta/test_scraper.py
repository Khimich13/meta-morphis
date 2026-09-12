from typing import Any

from pytest import MonkeyPatch

from meta_morphis.meta.scraper import parse_meta_table, scrape_meta_cards


def test_parse_meta_table_valid() -> None:
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
    assert result != None
    assert len(result) == 1
    entry = result[0]
    assert entry.name == "Lightning Bolt"
    assert entry.rank == 1
    assert entry.percent == 25.0
    assert entry.avg_copies == 3.5

def test_parse_meta_table_no_table() -> None:
    html = "<html><body>No table here</body></html>"
    assert parse_meta_table(html) is None

def test_parse_meta_table_double_name() -> None:
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
    result = parse_meta_table(html)

    assert result != None

    entry = result[0]

    assert entry.name == "Fire // Ice"
    assert entry.lookup_name == "Fire"

def test_parse_meta_table_empty_rows() -> None:
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

    assert result != None
    assert len(result) == 1

def test_scrape_meta_cards_success(monkeypatch: MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers: dict[str, str] = {}
            self.text = """
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

        def json(self) -> None:
            raise ValueError("Not JSON")

    monkeypatch.setattr("requests.request", lambda *args, **kwargs: FakeResponse())

    result = scrape_meta_cards("http://fake-url")
    assert result != None
    assert len(result) == 1
    assert result[0].name == "Test Card"

def test_scrape_meta_cards_retry(monkeypatch: MonkeyPatch) -> None:
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

    def fake_get(*args: Any, **kwargs: Any) -> Any:
        return responses.pop(0)

    monkeypatch.setattr("requests.request", fake_get)
    monkeypatch.setattr("time.sleep", lambda x: None)

    result = scrape_meta_cards("http://fake-url")

    assert result is not None
    assert len(result) == 1

def test_scrape_meta_cards_all_fail(monkeypatch: MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 500

    monkeypatch.setattr("requests.request", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr("time.sleep", lambda x: None)

    assert scrape_meta_cards("http://fake-url") is None