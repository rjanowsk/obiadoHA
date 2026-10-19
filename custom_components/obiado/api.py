"""Asynchronous read-only client for the API used by the Obiado portal.

Only login uses POST. All data operations are explicitly allowlisted GETs.
There are no ordering, cancelling, payment or account modification methods.
"""

import asyncio
import re
from datetime import date
from typing import Any

import aiohttp

from .models import (
    ChildNotFound,
    InvalidAuth,
    InvalidResponse,
    MealDay,
    ObiadoError,
    months_between,
    normalize_host,
    normalize_name,
    parse_orders,
)

API_URL = "https://api.obiado.pl"
MAX_PAGES = 1000


class ObiadoClient:
    def __init__(
        self, session: aiohttp.ClientSession, host: str, username: str, password: str
    ) -> None:
        self._session = session
        self.host = normalize_host(host)
        self._username = username
        self._password = password
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def _request(
        self, method: str, path: str, *, params: dict | None = None, body: dict | None = None
    ) -> Any:
        headers = {"X-Tenant-Slug": self.host.split(".")[0], "Accept": "application/json"}
        if self._token and path != "/api/auth/login":
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with self._session.request(
                method,
                API_URL + path,
                headers=headers,
                params=params,
                json=body,
                timeout=aiohttp.ClientTimeout(total=45),
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403):
                    raise InvalidAuth("Obiado authentication rejected")
                if response.status != 200:
                    raise ObiadoError(f"Obiado returned HTTP {response.status}")
                try:
                    return await response.json()
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise InvalidResponse("Obiado did not return JSON") from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ObiadoError("Cannot connect to Obiado") from err

    async def _login(self) -> None:
        payload = await self._request(
            "POST", "/api/auth/login", body={"username": self._username, "password": self._password}
        )
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("token"), str)
            or not payload["token"]
        ):
            raise InvalidResponse("Missing login token")
        self._token = payload["token"]

    async def _get(self, path: str, params: dict | None = None) -> Any:
        """Use only the observed read endpoints; retry expired credentials once."""
        allowed = path == "/api/frontend/auth/currentUser"
        allowed |= bool(re.fullmatch(r"/api/frontend/parents/\d+/children", path))
        allowed |= path == "/api/frontend/orders"
        allowed |= bool(re.fullmatch(r"/api/frontend/orders/subjects/child/\d+/orders", path))
        if not allowed:
            raise ValueError("Endpoint is not on the read-only allowlist")
        if not self._token:
            await self._login()
        try:
            return await self._request("GET", path, params=params)
        except InvalidAuth:
            self._token = None
            await self._login()
            return await self._request("GET", path, params=params)

    async def _pages(
        self, path: str, *, nested: str | None = None, params: dict | None = None
    ) -> list[dict]:
        """Follow all pages, failing rather than publishing a truncated snapshot."""
        result: list[dict] = []
        seen: set[str] = set()
        total: int | None = None
        for page in range(1, MAX_PAGES + 1):
            payload = await self._get(path, {**(params or {}), "page": page})
            container = payload.get(nested) if nested and isinstance(payload, dict) else payload
            if not isinstance(container, dict) or not isinstance(container.get("items"), list):
                raise InvalidResponse("Missing paginated items")
            # The portal's ListWrapper uses currentPage/perPage/totalResults.
            # Do not request a page beyond the advertised result count.
            if "currentPage" in container and (
                type(container["currentPage"]) is not int or container["currentPage"] != page
            ):
                raise InvalidResponse("Portal returned a different page")
            if "totalResults" in container:
                advertised_total = container["totalResults"]
                if type(advertised_total) is not int or advertised_total < 0:
                    raise InvalidResponse("Invalid pagination total")
                if total is not None and total != advertised_total:
                    raise InvalidResponse("Pagination total changed during fetch")
                total = advertised_total
            elif total is not None:
                raise InvalidResponse("Pagination total disappeared during fetch")
            items = container["items"]
            if not items:
                if total is not None and len(result) != total:
                    raise InvalidResponse("Portal ended before all results were fetched")
                return result
            if any(not isinstance(item, dict) for item in items):
                raise InvalidResponse("Invalid paginated item")
            fingerprint = repr(items)
            if fingerprint in seen:
                raise InvalidResponse("Portal repeated a page")
            seen.add(fingerprint)
            result.extend(items)
            if total is not None:
                if len(result) > total:
                    raise InvalidResponse("Portal returned more items than pagination total")
                if len(result) == total:
                    return result
            # Without metadata, require an empty page; never infer from page size.
        raise InvalidResponse("Pagination limit exceeded")

    async def resolve_child(self, name: str) -> int:
        async with self._lock:
            try:
                user = await self._get("/api/frontend/auth/currentUser")
            except InvalidResponse as err:
                raise InvalidResponse(f"Login/current user: {err}") from err
            if not isinstance(user, dict) or not isinstance(user.get("id"), int):
                raise InvalidResponse("Missing current user ID")
            try:
                children = await self._pages(f"/api/frontend/parents/{user['id']}/children")
            except InvalidResponse as err:
                raise InvalidResponse(f"Children list: {err}") from err
            matches = []
            for child in children:
                full_name = child.get("fullName")
                display = full_name.get("name") if isinstance(full_name, dict) else None
                if isinstance(display, str) and normalize_name(display) == normalize_name(name):
                    matches.append(child)
            if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
                raise ChildNotFound("Child name must match exactly one child")
            return matches[0]["id"]

    async def fetch_orders(self, child_id: int, cutoff: date) -> list[MealDay]:
        async with self._lock:
            # Discover every future month from the account's paginated order list.
            # The basket endpoint is monthly; never impose an arbitrary future horizon.
            try:
                orders = await self._pages(
                    "/api/frontend/orders", nested="orders", params={"dateFrom": cutoff.isoformat()}
                )
            except InvalidResponse as err:
                raise InvalidResponse(f"Orders list: {err}") from err
            months = {(cutoff.year, cutoff.month)}
            for order in orders:
                try:
                    if order.get("type") == "prepaid_order":
                        start = date.fromisoformat(order["dateFrom"][:10])
                        end = date.fromisoformat(order["dateTo"][:10])
                        if start > end:
                            raise ValueError("Invalid date range")
                        months.update(months_between(max(start, cutoff), end))
                    else:
                        day = date.fromisoformat(order["date"][:10])
                        if day >= cutoff:
                            months.add((day.year, day.month))
                except (KeyError, TypeError, ValueError) as err:
                    raise InvalidResponse("Invalid order list date") from err
            days: dict[date, MealDay] = {}
            for year, month in sorted(months):
                try:
                    payload = await self._get(
                        f"/api/frontend/orders/subjects/child/{child_id}/orders",
                        {"year": year, "month": month},
                    )
                    monthly_orders = parse_orders(payload, year, month)
                except InvalidResponse as err:
                    raise InvalidResponse(f"Monthly basket: {err}") from err
                for item in monthly_orders:
                    if item.day >= cutoff:
                        days[item.day] = item
            return sorted(days.values())
