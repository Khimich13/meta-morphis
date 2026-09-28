import pytest


@pytest.fixture(autouse=True)
def _reset_http_pacing_state() -> None:
    # request_with_retries persists the last-request timestamp at module
    # scope so it can pace between separate calls, not just within one
    # call's own retries. Reset it before every test so one
    # test's real timing can't leak into the next one's and cause an
    # unexpected real time.sleep().
    import meta_morphis.utils.http as http
    http._last_request_time = 0.0
