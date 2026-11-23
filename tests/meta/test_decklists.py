import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from meta_morphis import config
from meta_morphis.meta import decklists
from meta_morphis.meta.decklists import count_meta_cards, rank_cards
from meta_morphis.models.meta import MetaEntry
from meta_morphis.utils.http import RequestUnavailable

TODAY = date(2026, 11, 22)
API = config.DECKLISTS_API_URL
RAW = f"{config.DECKLISTS_RAW_URL}{config.DECKLISTS_FOLDER}/"


def _deck(main: dict[str, int], side: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "Player": "someone",
        "Mainboard": [{"Count": n, "CardName": name} for name, n in main.items()],
        "Sideboard": [
            {"Count": n, "CardName": name} for name, n in (side or {}).items()
        ],
    }


def _event(*decks: dict[str, Any]) -> str:
    return json.dumps({"Tournament": {"Name": "Challenge"}, "Decks": list(decks)})


class FakeGitHub:
    """GitHub's API and raw files for an archive of `files`, keyed by
    their path under DECKLISTS_FOLDER ("2026/11/20/pauper-a.json")"""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.calls: list[str] = []
        self.down = False

    def __call__(self, method: str, url: str, **kwargs: Any) -> str | None:
        self.calls.append(url)
        if self.down:
            raise RequestUnavailable("unexpected status 403")
        if url.startswith(RAW):
            return self.files.get(url.removeprefix(RAW))
        path = url.removeprefix(API)
        folder = f"contents/{config.DECKLISTS_FOLDER}/"
        if path.startswith(folder):
            year = path.removeprefix(folder)
            months = sorted(
                {p.split("/")[1] for p in self.files if p.startswith(f"{year}/")}
            )
            if not months:
                return None
            return json.dumps(
                [{"name": m, "type": "dir", "sha": f"{year}-{m}"} for m in months]
            )
        if path.startswith("git/trees/"):
            year, month = path.removeprefix("git/trees/").split("?")[0].split("-")
            prefix = f"{year}/{month}/"
            tree: list[dict[str, Any]] = []
            for p in self.files:
                if p.startswith(prefix):
                    day, name = p.removeprefix(prefix).split("/")
                    tree.append({"path": day, "type": "tree"})
                    tree.append({"path": f"{day}/{name}", "type": "blob"})
            return json.dumps({"tree": tree, "truncated": False})
        raise AssertionError(f"unexpected url {url}")

    def downloads(self) -> list[str]:
        return [url.removeprefix(RAW) for url in self.calls if url.startswith(RAW)]


@pytest.fixture
def github(monkeypatch: MonkeyPatch) -> FakeGitHub:
    fake = FakeGitHub({})
    monkeypatch.setattr(decklists, "request_with_retries", fake)
    return fake


def test_rank_cards_counts_the_main_deck_and_sideboard_together() -> None:
    decks = [
        {"Hydroblast": 2, "Counterspell": 4},
        {"Hydroblast": 4},
        {"Counterspell": 2},
        {"Lightning Bolt": 4},
    ]
    ranked = rank_cards(decks)
    assert [(e.name, e.rank, e.percent, e.avg_copies) for e in ranked] == [
        # A tie in decks and copies goes by name
        ("Counterspell", 1, 50.0, 3.0),
        ("Hydroblast", 2, 50.0, 3.0),
        ("Lightning Bolt", 3, 25.0, 4.0),
    ]


def test_rank_cards_breaks_a_tie_by_copies() -> None:
    ranked = rank_cards([{"A": 1, "B": 4}, {"A": 1, "B": 2}])
    assert [e.name for e in ranked] == ["B", "A"]


def test_rank_cards_counts_spellings_of_one_name_as_one_card() -> None:
    ranked = rank_cards(
        [{"Lórien Revealed": 2, "Lorien Revealed": 1}, {"Lorien Revealed": 3}]
    )
    assert len(ranked) == 1
    [entry] = ranked
    assert entry.name == "Lórien Revealed"
    # Played in both decks, not counted as three
    assert entry.percent == 100.0
    assert entry.avg_copies == 3.0


def test_rank_cards_of_no_decks_is_empty() -> None:
    assert rank_cards([]) == []


def _ranked(format_name: str, today: date, folder: Path) -> list[MetaEntry] | None:
    """count_meta_cards's cards, or None"""
    count = count_meta_cards(format_name, today, folder)
    return None if count is None else count.cards


def test_the_count_is_to_the_day_of_its_newest_decks(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.files = {
        "2026/11/02/pauper-league.json": _event(_deck({"A": 4})),
        "2026/11/19/pauper-challenge.json": _event(_deck({"A": 4})),
        "2026/11/18/pauper-league.json": _event(_deck({"A": 4})),
        # Newer, but with no deck that can be read
        "2026/11/20/pauper-league.json": json.dumps({"Decks": []}),
        "2026/11/21/premodern-league.json": _event(_deck({"A": 4})),
    }
    count = count_meta_cards("pauper", TODAY, tmp_path)
    assert count is not None
    assert count.decks_to == date(2026, 11, 19)


def test_a_count_of_no_decks_is_to_no_day(github: FakeGitHub, tmp_path: Path) -> None:
    count = count_meta_cards("pauper", TODAY, tmp_path)
    assert count is not None
    assert count.cards == []
    assert count.decks_to is None


def test_counts_the_formats_files_of_the_last_30_days(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.files = {
        "2026/11/20/pauper-challenge.json": _event(
            _deck({"Counterspell": 4}, {"Hydroblast": 2}),
            _deck({"Counterspell": 2, "Hydroblast": 1}, {"Hydroblast": 2}),
        ),
        # The first day of the window, in the month before
        "2026/10/24/pauper-league.json": _event(_deck({"Lightning Bolt": 4})),
        # The day before the window
        "2026/10/23/pauper-league.json": _event(_deck({"Too Old": 4})),
        "2026/11/20/premodern-challenge.json": _event(_deck({"Other": 4})),
    }
    ranked = _ranked("pauper", TODAY, tmp_path)
    assert ranked is not None
    assert [(e.name, e.percent, e.avg_copies) for e in ranked] == [
        ("Counterspell", 66.7, 3.0),
        ("Hydroblast", 66.7, 2.5),
        ("Lightning Bolt", 33.3, 4.0),
    ]
    # Two months' trees, from one listing of the year
    assert sum(url.startswith(API) for url in github.calls) == 3
    assert sorted(github.downloads()) == [
        "2026/10/24/pauper-league.json",
        "2026/11/20/pauper-challenge.json",
    ]


def test_modern_is_not_premodern(github: FakeGitHub, tmp_path: Path) -> None:
    github.files = {
        "2026/11/20/premodern-challenge.json": _event(_deck({"Premodern Card": 4})),
        "2026/11/20/modern-challenge.json": _event(_deck({"Modern Card": 4})),
    }
    ranked = _ranked("modern", TODAY, tmp_path)
    assert ranked is not None
    assert [e.name for e in ranked] == ["Modern Card"]


def test_downloads_only_new_files(github: FakeGitHub, tmp_path: Path) -> None:
    github.files = {"2026/11/20/pauper-a.json": _event(_deck({"A": 4}))}
    count_meta_cards("pauper", TODAY, tmp_path)
    github.files["2026/11/21/pauper-b.json"] = _event(_deck({"B": 4}))
    github.calls.clear()

    ranked = _ranked("pauper", TODAY, tmp_path)
    assert github.downloads() == ["2026/11/21/pauper-b.json"]
    assert ranked is not None
    assert sorted(e.name for e in ranked) == ["A", "B"]


def test_deletes_the_days_before_the_window(github: FakeGitHub, tmp_path: Path) -> None:
    old = tmp_path / "2026" / "09" / "30" / "modern-a.json"
    old.parent.mkdir(parents=True)
    old.write_text(_event(_deck({"A": 4})))
    kept = tmp_path / "2026" / "10" / "24" / "modern-b.json"
    kept.parent.mkdir(parents=True)
    kept.write_text(_event(_deck({"B": 4})))

    count_meta_cards("pauper", TODAY, tmp_path)
    assert not (tmp_path / "2026" / "09").exists()
    assert kept.exists()


def test_none_when_the_archive_cant_be_listed(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.files = {"2026/11/20/pauper-a.json": _event(_deck({"A": 4}))}
    github.down = True
    assert count_meta_cards("pauper", TODAY, tmp_path) is None


def test_a_year_with_no_folder_yet_has_no_files(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.files = {"2026/12/31/pauper-a.json": _event(_deck({"A": 4}))}
    ranked = _ranked("pauper", date(2027, 1, 1), tmp_path)
    assert ranked is not None
    assert [e.name for e in ranked] == ["A"]


def test_a_failed_download_is_tried_again_next_run(
    github: FakeGitHub, tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    github.files = {
        "2026/11/20/pauper-a.json": _event(_deck({"A": 4})),
        "2026/11/20/pauper-b.json": "<html>not json</html>",
    }
    ranked = _ranked("pauper", TODAY, tmp_path)
    assert ranked is not None
    assert [e.name for e in ranked] == ["A"]
    assert not (tmp_path / "2026/11/20/pauper-b.json").exists()

    github.files["2026/11/20/pauper-b.json"] = _event(_deck({"B": 4}))
    github.calls.clear()
    ranked = _ranked("pauper", TODAY, tmp_path)
    assert github.downloads() == ["2026/11/20/pauper-b.json"]
    assert ranked is not None
    assert sorted(e.name for e in ranked) == ["A", "B"]


def test_leaves_out_decks_and_card_lines_of_the_wrong_shape(
    github: FakeGitHub, tmp_path: Path
) -> None:
    good = _deck({"A": 4})
    odd_lines = {
        "Mainboard": [
            {"Count": 2, "CardName": "B"},
            {"Count": "2", "CardName": "Text Count"},
            {"Count": True, "CardName": "Bool Count"},
            {"Count": 0, "CardName": "No Copies"},
            {"Count": 1, "CardName": "  "},
            "not a line",
        ],
        "Sideboard": None,
    }
    github.files = {
        "2026/11/20/pauper-a.json": json.dumps(
            {"Decks": [good, odd_lines, "not a deck", {"Mainboard": []}]}
        ),
        "2026/11/20/pauper-b.json": json.dumps({"Tournament": {}}),
    }
    ranked = _ranked("pauper", TODAY, tmp_path)
    assert ranked is not None
    assert [(e.name, e.percent) for e in ranked] == [("A", 50.0), ("B", 50.0)]


def test_sends_the_github_token_to_the_api_only(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    sent: list[tuple[str, dict[str, str]]] = []
    fake = FakeGitHub({"2026/11/20/pauper-a.json": _event(_deck({"A": 4}))})

    def spy(method: str, url: str, **kwargs: Any) -> str | None:
        sent.append((url, kwargs["headers"]))
        return fake(method, url, **kwargs)

    monkeypatch.setattr(decklists, "request_with_retries", spy)
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    count_meta_cards("pauper", TODAY, tmp_path)
    for url, headers in sent:
        expected = "Bearer secret" if url.startswith(API) else None
        assert headers.get("Authorization") == expected
