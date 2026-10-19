"""Exercise authentication and wire requests against an isolated fake server session."""

from datetime import date
from unittest.mock import AsyncMock

import aiohttp
import pytest

from custom_components.obiado.api import API_URL, ObiadoClient
from custom_components.obiado.models import ChildNotFound, InvalidAuth, InvalidResponse, ObiadoError


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def json(self):
        return self.payload


class Session:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item


def client(session):
    return ObiadoClient(session, "rpk.obiado.pl", "test@example.invalid", "test-only")


async def test_login_and_paginated_child_selection():
    session = Session(
        Response({"token": "secret-token"}),
        Response({"id": 1}),
        Response({"items": [{"id": 10, "fullName": {"name": "Testowa Anna"}}]}),
        Response({"items": [{"id": 20, "fullName": {"name": "Testowy Jan"}}]}),
        Response({"items": []}),
    )
    assert await client(session).resolve_child(" TESTOWY   Jan ") == 20
    login = session.calls[0]
    assert login[0:2] == ("POST", API_URL + "/api/auth/login")
    assert login[2]["json"] == {"username": "test@example.invalid", "password": "test-only"}
    assert "Authorization" not in login[2]["headers"]
    for method, _url, kwargs in session.calls[1:]:
        assert method == "GET"
        assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
        assert kwargs["headers"]["X-Tenant-Slug"] == "rpk"
        assert kwargs["allow_redirects"] is False


async def test_missing_or_duplicate_child_fails():
    for children in [[], [{"id": 10, "fullName": {"name": "Testowy Jan"}}] * 2]:
        api = client(Session())
        api._get = AsyncMock(return_value={"id": 1})
        api._pages = AsyncMock(return_value=children)
        with pytest.raises(ChildNotFound):
            await api.resolve_child("Testowy Jan")


async def test_expired_token_reauthenticates_once():
    session = Session(
        Response({"token": "old"}),
        Response({}, 401),
        Response({"token": "new"}),
        Response({"id": 1}),
    )
    assert await client(session)._get("/api/frontend/auth/currentUser") == {"id": 1}
    assert [call[0] for call in session.calls] == ["POST", "GET", "POST", "GET"]


async def test_bad_password_and_rejected_retry():
    with pytest.raises(InvalidAuth):
        await client(Session(Response({}, 401))).resolve_child("Testowy Jan")
    session = Session(
        Response({"token": "old"}), Response({}, 401), Response({"token": "new"}), Response({}, 403)
    )
    with pytest.raises(InvalidAuth):
        await client(session)._get("/api/frontend/auth/currentUser")
    assert len(session.calls) == 4


async def test_network_and_invalid_response():
    with pytest.raises(ObiadoError, match="Cannot connect"):
        await client(Session(aiohttp.ClientConnectionError())).resolve_child("Testowy Jan")
    with pytest.raises(InvalidResponse):
        await client(Session(Response({}))).resolve_child("Testowy Jan")


async def test_repeated_page_does_not_publish_partial_snapshot():
    api = client(Session())
    api._get = AsyncMock(return_value={"items": [{"id": 1}]})
    with pytest.raises(InvalidResponse, match="repeated"):
        await api._pages("/api/frontend/parents/1/children")


async def test_all_future_months_and_prepaid_ranges():
    api = client(Session())
    api._pages = AsyncMock(
        return_value=[
            {"type": "order", "date": "2026-10-19"},
            {"type": "order", "date": "2028-03-01"},
            {"type": "prepaid_order", "dateFrom": "2026-12-01", "dateTo": "2027-01-31"},
        ]
    )

    async def get(path, params):
        assert path == "/api/frontend/orders/subjects/child/20/orders"
        if params == {"year": 2026, "month": 10}:
            return {"orders": {"2026-10-12": ["Old"], "2026-10-19": ["Zupa", "Napój"]}}
        return {"orders": {}}

    api._get = AsyncMock(side_effect=get)
    days = await api.fetch_orders(20, date(2026, 10, 13))
    assert len(days) == 1
    assert days[0].meals == ("Zupa", "Napój")
    assert [call.args[1] for call in api._get.call_args_list] == [
        {"year": 2026, "month": 10},
        {"year": 2026, "month": 12},
        {"year": 2027, "month": 1},
        {"year": 2028, "month": 3},
    ]


async def test_empty_snapshot_and_partial_failure():
    api = client(Session())
    api._pages = AsyncMock(return_value=[])
    api._get = AsyncMock(return_value={"orders": {}})
    assert await api.fetch_orders(20, date(2026, 10, 13)) == []
    api._pages = AsyncMock(return_value=[{"date": "2026-11-02"}])
    api._get = AsyncMock(side_effect=[{"orders": {"2026-10-19": ["Zupa"]}}, ObiadoError("offline")])
    with pytest.raises(ObiadoError):
        await api.fetch_orders(20, date(2026, 10, 13))


async def test_mutating_endpoint_is_never_requested():
    session = Session()
    with pytest.raises(ValueError, match="allowlist"):
        await client(session)._get("/api/frontend/orders/1/cancel")
    assert not session.calls


async def test_setup_uses_portal_totals_without_requesting_out_of_range_pages():
    """Walk login, child lookup, order discovery and basket as one setup request."""
    session = Session(
        Response({"token": "test-token"}),
        Response({"id": 1}),
        Response(
            {
                "items": [{"id": 20, "fullName": {"name": "Testowy Jan"}}],
                "currentPage": 1,
                "perPage": 20,
                "totalResults": 1,
            }
        ),
        Response(
            {
                "orders": {
                    "items": [{"type": "order", "date": "2026-10-19"}],
                    "currentPage": 1,
                    "perPage": 20,
                    "totalResults": 1,
                }
            }
        ),
        Response({"orders": {"2026-10-19": {"0": "Zupa", "2": "Danie główne"}}}),
    )
    api = client(session)
    child_id = await api.resolve_child("Testowy Jan")
    days = await api.fetch_orders(child_id, date(2026, 10, 14))
    assert days[0].day == date(2026, 10, 19)
    assert days[0].meals == ("Zupa", "Danie główne")
    assert len(session.calls) == 5


async def test_pagination_follows_total_even_when_server_returns_short_pages():
    api = client(Session())
    api._get = AsyncMock(
        side_effect=[
            {"items": [{"id": 1}], "currentPage": 1, "perPage": 20, "totalResults": 2},
            {"items": [{"id": 2}], "currentPage": 2, "perPage": 20, "totalResults": 2},
        ]
    )
    assert await api._pages("/api/frontend/orders") == [{"id": 1}, {"id": 2}]
    assert api._get.call_count == 2


@pytest.mark.parametrize(
    "pages, message",
    [
        ([{"items": [], "totalResults": -1}], "Invalid pagination total"),
        ([{"items": [], "totalResults": True}], "Invalid pagination total"),
        ([{"items": [], "totalResults": "0"}], "Invalid pagination total"),
        ([{"items": [{"id": 1}], "totalResults": 0}], "more items"),
        ([{"items": [], "totalResults": 1}], "ended before"),
        ([{"items": [{"id": 1}], "currentPage": 2}], "different page"),
        (
            [
                {"items": [{"id": 1}], "totalResults": 2},
                {"items": [{"id": 2}], "totalResults": 3},
            ],
            "total changed",
        ),
        (
            [{"items": [{"id": 1}], "totalResults": 2}, {"items": []}],
            "total disappeared",
        ),
    ],
)
async def test_invalid_pagination_does_not_return_partial_results(pages, message):
    api = client(Session())
    api._get = AsyncMock(side_effect=pages)
    with pytest.raises(InvalidResponse, match=message):
        await api._pages("/api/frontend/orders")


async def test_empty_total_is_a_valid_empty_snapshot():
    api = client(Session())
    api._get = AsyncMock(return_value={"items": [], "currentPage": 1, "totalResults": 0})
    assert await api._pages("/api/frontend/orders") == []


async def test_invalid_response_identifies_stage_without_account_data():
    api = client(Session())
    api._get = AsyncMock(return_value={"id": 1})
    api._pages = AsyncMock(side_effect=InvalidResponse("Missing paginated items"))
    with pytest.raises(InvalidResponse, match="Children list: Missing paginated items"):
        await api.resolve_child("Testowy Jan")
    with pytest.raises(InvalidResponse, match="Orders list: Missing paginated items"):
        await api.fetch_orders(20, date(2026, 10, 14))
    api._pages = AsyncMock(return_value=[])
    api._get = AsyncMock(return_value={})
    with pytest.raises(InvalidResponse, match="Monthly basket: Missing orders mapping"):
        await api.fetch_orders(20, date(2026, 10, 14))
