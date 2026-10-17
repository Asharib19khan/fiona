from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest

from fiona_agents import api as agents_api
from fiona_agents.auth import TokenError, verify_agents_token
from fiona_agents.extraction import (
    ExtractionError,
    _model_extract,
    _normalise_model_result,
    extract_bill,
)
from fiona_contracts.models import (
    ModelBillExtraction,
    ModelBillLine,
    ModelExtractedBill,
    ModelMoney,
    SourcedBankAccount,
    SourcedDate,
    SourcedText,
    SourceSpan,
)
from fiona_contracts.validate import validate as validate_contract


def source(quote: str, page: int = 1) -> SourceSpan:
    return SourceSpan(page=page, quote=quote, verified_in_text=None)


def sourced_text(value: str | None, quote: str | None = None) -> SourcedText:
    return SourcedText(
        value=value,
        source=source(quote) if quote else None,
        confidence="high" if value is not None else "low",
    )


def model_money(
    amount: str | None, quote: str | None = None, currency: str | None = "PKR"
) -> ModelMoney:
    return ModelMoney(
        amount=amount,
        currency=currency,
        source=source(quote) if quote else None,
        confidence="high" if amount is not None else "low",
    )


def model_bill() -> ModelBillExtraction:
    line_source = source("Fabric 1 x 12.34")
    return ModelBillExtraction(
        bill=ModelExtractedBill(
            supplier_name=sourced_text("Synthetic Supplier", "Synthetic Supplier"),
            supplier_tax_id=sourced_text(None),
            supplier_address=sourced_text(None),
            invoice_number=sourced_text("INV-1", "Invoice INV-1"),
            issue_date=SourcedDate(
                value="2026-10-15", source=source("15 Oct 2026"), confidence="high"
            ),
            due_date=SourcedDate(value=None, source=None, confidence="low"),
            currency=sourced_text("PKR", "PKR"),
            purchase_order_ref=sourced_text(None),
            lines=[
                ModelBillLine(
                    description="Fabric",
                    quantity="1",
                    unit_price=model_money("12.34", "12.34"),
                    tax_rate=None,
                    line_total=model_money("12.34", "12.34"),
                    source=line_source,
                )
            ],
            subtotal=model_money("12.34", "Subtotal 12.34"),
            tax_total=model_money("0.00", "Tax 0.00"),
            total=model_money("12.34", "Total 12.34"),
            bank_account=SourcedBankAccount(value=None, source=None, confidence="low"),
        ),
        embedded_instructions=[],
        low_confidence_fields=[],
        unreadable_regions=[],
    )


def signed_token(
    secret: str, *, role: str = "owner", tenant_id: str = "ten_karachi_apparel"
) -> str:
    now = int(time.time())

    def encode(value: object) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )

    header = encode({"alg": "HS256", "typ": "JWT"})
    payload = encode(
        {
            "sub": "usr_owner_01",
            "tenant_id": tenant_id,
            "role": role,
            "aud": "fiona-agents",
            "iat": now,
            "exp": now + 60,
        }
    )
    signature = (
        base64.urlsafe_b64encode(
            hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.{signature}"


def test_internal_token_requires_valid_signature_audience_and_short_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-only-internal-jwt-secret-32bytes"
    monkeypatch.setenv("INTERNAL_JWT_SECRET", secret)
    principal = verify_agents_token(signed_token(secret))
    assert (principal.user_id, principal.tenant_id, principal.role) == (
        "usr_owner_01",
        "ten_karachi_apparel",
        "owner",
    )

    with pytest.raises(TokenError, match="role"):
        verify_agents_token(signed_token(secret, role="viewer"))
    with pytest.raises(TokenError, match="tenant"):
        verify_agents_token(signed_token(secret, tenant_id="ten_OTHER"))
    with pytest.raises(TokenError):
        valid_tok = signed_token(secret)
        tampered_tok = valid_tok[:-5] + ("00000" if valid_tok[-5:] != "00000" else "11111")
        verify_agents_token(tampered_tok)


def test_normalization_uses_decimal_minor_units_and_emits_a_contract_valid_response() -> None:
    result = _normalise_model_result(
        model_bill(),
        document_id="doc_0123456789abcdef01234567",
        sha256="a" * 64,
        media_type="image/jpeg",
        pages=1,
        currency_hint="PKR",
        minor_unit=2,
        model="test-model",
    )
    assert result.bill.total.value.minor == 1234
    assert result.bill.total.value.currency == "PKR"
    assert result.checks.arithmetic_mismatch is False
    assert result.meta.replayed is False
    assert result.bill.total.source.verified_in_text is None
    validate_contract("BillExtraction", result.model_dump(mode="json"))


def test_mismatched_currency_is_never_converted_as_tenant_currency() -> None:
    raw = model_bill().model_dump(mode="json")
    raw["bill"]["total"]["currency"] = "USD"
    extracted = ModelBillExtraction.model_validate(raw)
    result = _normalise_model_result(
        extracted,
        document_id="doc_0123456789abcdef01234567",
        sha256="a" * 64,
        media_type="image/jpeg",
        pages=1,
        currency_hint="PKR",
        minor_unit=2,
        model="test-model",
    )
    assert result.checks.currency_mismatch is True
    assert result.bill.total.value is None
    assert result.checks.arithmetic_mismatch is True


def test_arithmetic_mismatch_and_excess_precision_are_fail_closed() -> None:
    raw = model_bill().model_dump(mode="json")
    raw["bill"]["lines"][0]["line_total"]["amount"] = "13.34"
    mismatched = ModelBillExtraction.model_validate(raw)
    result = _normalise_model_result(
        mismatched,
        document_id="doc_0123456789abcdef01234567",
        sha256="a" * 64,
        media_type="image/jpeg",
        pages=1,
        currency_hint="PKR",
        minor_unit=2,
        model="test-model",
    )
    assert result.checks.arithmetic_mismatch is True
    assert result.checks.difference.minor == -100

    raw["bill"]["subtotal"]["amount"] = "12.345"
    too_precise = ModelBillExtraction.model_validate(raw)
    with pytest.raises(ExtractionError, match="more precision"):
        _normalise_model_result(
            too_precise,
            document_id="doc_0123456789abcdef01234567",
            sha256="a" * 64,
            media_type="image/jpeg",
            pages=1,
            currency_hint="PKR",
            minor_unit=2,
            model="test-model",
        )


def test_out_of_range_source_page_is_rejected() -> None:
    raw = model_bill().model_dump(mode="json")
    raw["bill"]["invoice_number"]["source"]["page"] = 2
    invalid = ModelBillExtraction.model_validate(raw)
    with pytest.raises(ExtractionError, match="outside the uploaded document"):
        _normalise_model_result(
            invalid,
            document_id="doc_0123456789abcdef01234567",
            sha256="a" * 64,
            media_type="image/jpeg",
            pages=1,
            currency_hint="PKR",
            minor_unit=2,
            model="test-model",
        )


def test_anthropic_request_is_tool_constrained_and_returns_validated_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    raw = model_bill().model_dump(mode="json")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_test",
                        "name": "submit_bill_extraction",
                        "input": raw,
                    }
                ],
            },
        )

    async def run() -> ModelBillExtraction:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await _model_extract(
                b"\xff\xd8\xffsynthetic",
                media_type="image/jpeg",
                filename="invoice.jpg",
                model="test-model",
                client=client,
                deadline=time.monotonic() + 5,
            )

    parsed = asyncio.run(run())

    assert isinstance(parsed, ModelBillExtraction)
    assert len(calls) == 1
    sent = json.loads(calls[0].content)
    assert sent["tool_choice"] == {"type": "tool", "name": "submit_bill_extraction"}
    assert sent["tools"][0]["input_schema"]["additionalProperties"] is False
    assert calls[0].headers["x-api-key"] == "test-key-not-real"


def test_invalid_model_output_retries_once_then_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(
            200,
            json={
                "stop_reason": "tool_use",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"toolu_{count}",
                        "name": "submit_bill_extraction",
                        "input": {"unexpected": True},
                    }
                ],
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await _model_extract(
                b"\xff\xd8\xffsynthetic",
                media_type="image/jpeg",
                filename="invoice.jpg",
                model="test-model",
                client=client,
                deadline=time.monotonic() + 5,
            )

    with pytest.raises(ExtractionError, match="invalid bill extraction"):
        asyncio.run(run())
    assert count == 2


def test_local_file_checks_reject_bad_mime_bytes_without_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    with pytest.raises(ExtractionError, match="bytes do not match"):
        asyncio.run(
            extract_bill(
                b"not a pdf",
                media_type="application/pdf",
                filename="invoice.pdf",
                currency_hint="PKR",
                minor_unit=2,
            )
        )


def test_extraction_route_requires_provider_and_verified_bff_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from fiona_agents.main import create_app

    client = TestClient(create_app())
    monkeypatch.setenv("FIONA_LLM_PROVIDER", "replay")
    disabled = client.post("/v1/agents/extract-bill")
    assert disabled.status_code == 503
    assert disabled.json()["error"]["code"] == "provider_not_configured"

    monkeypatch.setenv("FIONA_LLM_PROVIDER", "anthropic_api")
    monkeypatch.setenv("INTERNAL_JWT_SECRET", "test-only-internal-jwt-secret-32bytes")
    unauthenticated = client.post("/v1/agents/extract-bill")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "unauthorized"


def test_extraction_route_accepts_a_valid_bff_token_and_returns_contract_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    from fiona_agents.main import create_app

    secret = "test-only-internal-jwt-secret-32bytes"
    monkeypatch.setenv("FIONA_LLM_PROVIDER", "anthropic_api")
    monkeypatch.setenv("INTERNAL_JWT_SECRET", secret)
    monkeypatch.setenv("FIONA_MODEL_EXTRACT", "test-model")
    expected = _normalise_model_result(
        model_bill(),
        document_id="doc_0123456789abcdef01234567",
        sha256="a" * 64,
        media_type="image/jpeg",
        pages=1,
        currency_hint="PKR",
        minor_unit=2,
        model="test-model",
    )
    received: dict[str, object] = {}

    async def fake_extract(content: bytes, **kwargs: object):
        received.update({"content": content, **kwargs})
        return expected

    monkeypatch.setattr(agents_api, "extract_bill", fake_extract)
    response = TestClient(create_app()).post(
        "/v1/agents/extract-bill",
        headers={"Authorization": f"Bearer {signed_token(secret)}"},
        data={"currency": "PKR", "minor_unit": "2"},
        files={"file": ("invoice.jpg", b"\xff\xd8\xffsynthetic", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json()["api_version"] == "v1"
    assert response.json()["checks"]["arithmetic_mismatch"] is False
    assert received["content"] == b"\xff\xd8\xffsynthetic"
    assert received["currency_hint"] == "PKR"
    assert received["minor_unit"] == 2
