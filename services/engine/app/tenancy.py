"""The tenant for the current request (R15).

The tenant is injected by the server. It is never read from a request body, a query string or
any URL the user can edit. Endpoints take it as a dependency:

    from engine.app.tenancy import TenantId

    @router.get("/v1/forecast/cash")
    def cash(tenant_id: TenantId, weeks: int = 13) -> ...: ...

Mock mode (`FIONA_MODE=mock`, the default) trusts the `X-Fiona-Tenant` header, so lanes can test
both personas, and falls back to `DEMO_TENANT_ID`. In live mode the tenant will come from the
verified internal token (the BFF's 60-second JWT in A3, or the agents' service token in A4).
Until that lands, live mode fails closed with 401 (R9).
"""

from __future__ import annotations

import os
import re
from typing import Annotated

from fastapi import Depends, Header, Request

from engine.app.errors import ApiError

TENANT_HEADER = "X-Fiona-Tenant"
DEFAULT_DEMO_TENANT = "ten_karachi_apparel"
_TENANT_ID = re.compile(r"^ten_[a-z0-9_]{1,60}$")


def current_tenant(
    request: Request,
    x_fiona_tenant: Annotated[str | None, Header(include_in_schema=False)] = None,
) -> str:
    if getattr(request.app.state, "mode", "mock") != "mock":
        raise ApiError(
            401,
            "unauthenticated",
            "Live mode needs a verified internal token; the tenant is never taken from the request.",
        )
    tenant = x_fiona_tenant or os.environ.get("DEMO_TENANT_ID") or DEFAULT_DEMO_TENANT
    if not _TENANT_ID.match(tenant):
        raise ApiError(400, "invalid_tenant", f"{TENANT_HEADER} must look like ten_<slug>.")
    return tenant


TenantId = Annotated[str, Depends(current_tenant)]
