from typing import Any

from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.meta.scraper import _parse_meta_table, scrape_meta_cards

# MTGGoldfish header markup: columns are located by <th> classes
_HEADER = """
<thead>
<tr>
<th class="col-rank"></th>
<th class="col-card">Card</th>
<th class="responsive-column">Cost</th>
<th class="col-decks">% of Decks</th>
<th class="col-played"># Played</th>
</tr>
</thead>
"""

def _table(rows_html: str, header: str = _HEADER) -> str:
    return f'<table class="table-staples">{header}{rows_html}</table>'

class FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.headers: dict[str, str] = {}


def test_parse_meta_table_valid() -> None:
    html = _table("""
        <tr>
            <td>1</td>
            <td>Lightning Bolt</td>
            <td></td>
            <td>25%</td>
            <td>3.5</td>
        </tr>
    """)
    result = _parse_meta_table(html)
    assert result is not None
    entries, skipped_count = result
    assert skipped_count == 0
    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "Lightning Bolt"
    assert entry.rank == 1
    assert entry.percent == 25.0
    assert entry.avg_copies == 3.5

def test_parse_meta_table_no_table() -> None:
    html = "<html><body>No table here</body></html>"
    assert _parse_meta_table(html) is None

def test_parse_meta_table_missing_thead_returns_none() -> None:
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
    assert _parse_meta_table(html) is None

def test_parse_meta_table_unrecognized_header_returns_none() -> None:
    html = _table(
        """
        <tr>
            <td>1</td>
            <td>Lightning Bolt</td>
            <td></td>
            <td>25%</td>
            <td>3.5</td>
        </tr>
        """,
        header="""
        <thead>
        <tr>
            <th>Rank</th>
            <th>Card</th>
            <th>Cost</th>
            <th>Decks</th>
            <th>Played</th>
        </tr>
        </thead>
        """,
    )
    assert _parse_meta_table(html) is None

def test_parse_meta_table_columns_reordered_still_parses() -> None:
    header = """
    <thead>
    <tr>
        <th class="col-played"></th>
        <th class="col-card">Card</th>
        <th class="col-rank"></th>
        <th class="col-decks">% of Decks</th>
    </tr>
    </thead>
    """
    html = _table(
        """
        <tr>
            <td>3.5</td>
            <td>Lightning Bolt</td>
            <td>1</td>
            <td>25%</td>
        </tr>
        """,
        header=header,
    )
    result = _parse_meta_table(html)
    assert result is not None
    entries, skipped_count = result
    assert skipped_count == 0
    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "Lightning Bolt"
    assert entry.rank == 1
    assert entry.percent == 25.0
    assert entry.avg_copies == 3.5

def test_parse_meta_table_double_name() -> None:
    html = _table("""
        <tr>
            <td>1</td>
            <td>Fire // Ice</td>
            <td></td>
            <td>10%</td>
            <td>2</td>
        </tr>
    """)
    result = _parse_meta_table(html)
    assert result is not None
    entries, skipped_count = result

    assert skipped_count == 0
    entry = entries[0]

    assert entry.name == "Fire // Ice"
    assert entry.lookup_name == "Fire"

def test_parse_meta_table_row_with_too_few_columns_is_skipped() -> None:
    html = _table("""
        <tr><td>1</td><td>Lightning Bolt</td></tr>
        <tr>
            <td>2</td>
            <td>Brainstorm</td>
            <td></td>
            <td>15%</td>
            <td>1</td>
        </tr>
    """)
    result = _parse_meta_table(html)
    assert result is not None
    entries, skipped_count = result

    assert skipped_count == 1
    assert len(entries) == 1

def test_parse_meta_table_empty_name_is_skipped() -> None:
    html = _table("""
        <tr>
            <td>1</td>
            <td></td>
            <td></td>
            <td>25%</td>
            <td>3.5</td>
        </tr>
    """)
    result = _parse_meta_table(html)
    assert result is not None
    entries, skipped_count = result

    assert skipped_count == 1
    assert entries == []

def test_parse_meta_table_single_bad_field_is_tolerated() -> None:
    html = _table("""
        <tr>
            <td>1</td>
            <td>Weird Percent Card</td>
            <td></td>
            <td>N/A</td>
            <td>3.5</td>
        </tr>
    """)
    result = _parse_meta_table(html)
    assert result is not None
    entries, skipped_count = result

    assert skipped_count == 0
    assert len(entries) == 1
    entry = entries[0]
    assert entry.name == "Weird Percent Card"
    assert entry.rank == 1
    assert entry.percent is None
    assert entry.avg_copies == 3.5

def test_parse_meta_table_structural_empty_row_not_counted_as_skipped() -> None:
    html = _table("""
        <tr></tr>
        <tr>
            <td>2</td>
            <td>Brainstorm</td>
            <td></td>
            <td>15%</td>
            <td>1</td>
        </tr>
    """)
    result = _parse_meta_table(html)
    assert result is not None
    entries, skipped_count = result

    assert skipped_count == 0
    assert len(entries) == 1

def test_scrape_meta_cards_success(monkeypatch: MonkeyPatch) -> None:
    html = _table("""
        <tr>
            <td>1</td>
            <td>Test Card</td>
            <td></td>
            <td>5%</td>
            <td>1</td>
        </tr>
    """)
    monkeypatch.setattr("requests.request", lambda *args, **kwargs: FakeResponse(200, html))

    result = scrape_meta_cards("http://fake-url")
    assert result is not None
    assert len(result) == 1
    assert result[0].name == "Test Card"

def test_scrape_meta_cards_retry(monkeypatch: MonkeyPatch) -> None:
    html = _table("""
        <tr>
            <td>1</td>
            <td>Test Card</td>
            <td></td>
            <td>5%</td>
            <td>1</td>
        </tr>
    """)
    responses = [FakeResponse(500), FakeResponse(500), FakeResponse(200, html)]

    def fake_request(*args: Any, **kwargs: Any) -> FakeResponse:
        return responses.pop(0)

    monkeypatch.setattr("requests.request", fake_request)
    monkeypatch.setattr("time.sleep", lambda x: None)

    result = scrape_meta_cards("http://fake-url")

    assert result is not None
    assert len(result) == 1

def test_scrape_meta_cards_all_fail(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("requests.request", lambda *args, **kwargs: FakeResponse(500))
    monkeypatch.setattr("time.sleep", lambda x: None)

    assert scrape_meta_cards("http://fake-url") is None

# Real MTGGoldfish name cells wrap the name in an <a> next to tooltip markup,
# so the cell's full text would be "Relic of ProgenitusView Card Details"
def test_parse_meta_table_takes_name_from_anchor() -> None:
    html = _table("""
        <tr>
            <td>1</td>
            <td><a href="/price/relic">Relic of Progenitus</a><span>View Card Details</span></td>
            <td></td>
            <td>35%</td>
            <td>2.8</td>
        </tr>
    """)
    result = _parse_meta_table(html)
    assert result is not None
    entries, _ = result

    assert entries[0].name == "Relic of Progenitus"

# Too many malformed rows means the page itself is broken, so the whole scrape
# is rejected (falling back to cached meta) rather than trusted. Checked at
# the boundary: exactly the limit is still accepted, one more is not.
def test_scrape_meta_cards_rejects_page_over_bad_rows_limit(monkeypatch: MonkeyPatch) -> None:
    good_row = "<tr><td>1</td><td>Lightning Bolt</td><td></td><td>25%</td><td>3.5</td></tr>"
    bad_row = "<tr><td>?</td><td>?</td></tr>"
    limit = config.GOLDFISH_BAD_ROWS_LIMIT

    for bad_rows, expected_ok in [(limit, True), (limit + 1, False)]:
        html = _table(good_row + bad_row * bad_rows)
        monkeypatch.setattr("requests.request", lambda *args, **kwargs: FakeResponse(200, html))

        result = scrape_meta_cards("http://fake-url")

        assert (result is not None) is expected_ok, f"{bad_rows} bad rows"
