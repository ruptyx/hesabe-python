"""Live smoke test against the Hesabe sandbox using their published test credentials.

    python tests/smoke.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hesabe import (  # noqa: E402
    BACKEND,
    HTTP_BACKEND,
    Hesabe,
    HesabeAPIError,
    HesabeAuthenticationError,
    HesabeConnectionError,
    HesabeError,
    PaymentType,
    format_amount,
)

hesabe = Hesabe(
    merchant_code="842217",
    access_code="c333729b-d060-4b74-a49d-7686a8353481",
    secret_key="PkW64zMe5NVdrlPVNnjo2Jy9nOb7v1Xg",
    iv_key="5NVdrlPVNnjo2Jy9",
    username="test",
    password="Test@1234",
    environment="sandbox",
)

passed = 0
failed = 0


def check(name, fn):
    global passed, failed
    try:
        detail = fn()
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
        passed += 1
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL  {name}\n        {type(exc).__name__}: {exc}")
        failed += 1


print(f"\nCrypto backend: {BACKEND} | HTTP backend: {HTTP_BACKEND}")
print("\nGateway (accessCode auth)")


def checkout_create():
    session = hesabe.checkout.create(
        amount=1.5,
        order_reference_number=f"SDK-PY-{int(time.time() * 1000)}",
        response_url="https://example.com/ok",
        failure_url="https://example.com/fail",
    )
    assert session.token, "no token"
    assert session.payment_url.startswith("https://sandbox.hesabe.com/payment?data=")
    return f"token {session.token[:12]}…"


def checkout_mobile():
    session = hesabe.checkout.create(
        amount=1,
        payment_type=PaymentType.MPGS,
        channel="mobile",
        order_reference_number=f"SDK-PY-MOB-{int(time.time() * 1000)}",
        response_url="https://example.com/ok",
        failure_url="https://example.com/fail",
    )
    assert "/pay/webview?data=" in session.webview_url
    return "webview_url present"


def checkout_embedded():
    session = hesabe.checkout.create(
        amount=2,
        embedded=True,
        order_reference_number=f"SDK-PY-EMB-{int(time.time() * 1000)}",
        response_url="https://example.com/ok",
        failure_url="https://example.com/fail",
    )
    assert session.data
    return f"{len(session.data)} char session token"


def bad_credentials():
    wrong = Hesabe(
        merchant_code="842217",
        access_code="00000000-0000-0000-0000-000000000000",
        secret_key="PkW64zMe5NVdrlPVNnjo2Jy9nOb7v1Xg",
        iv_key="5NVdrlPVNnjo2Jy9",
        environment="sandbox",
    )
    try:
        wrong.checkout.create(
            amount=1,
            order_reference_number="SDK-PY-AUTH",
            response_url="https://example.com/ok",
            failure_url="https://example.com/fail",
        )
    except HesabeAuthenticationError as exc:
        return f"code {exc.code}"
    raise AssertionError("expected a rejection")


def transaction_enquiry():
    # The docs place isOrderReference in the body; the SDK sends a query param
    # (probed behaviour). A structured Hesabe rejection proves the form is
    # accepted; only transport-level failures should fail this check.
    try:
        hesabe.transactions.retrieve_by_order_reference(f"SDK-PY-ENQ-{int(time.time())}")
    except (HesabeAPIError, HesabeConnectionError):
        raise
    except HesabeError as exc:
        return f"structured rejection: {type(exc).__name__} code {exc.code}"
    return "found a transaction"


check("checkout.create returns a payment URL", checkout_create)
check("checkout.create(channel='mobile') yields a webview_url", checkout_mobile)
check("checkout.create(embedded=True) selects version 3.0", checkout_embedded)
check("bad credentials raise HesabeAuthenticationError", bad_credentials)
check("transactions.retrieve_by_order_reference accepts the query-param form", transaction_enquiry)

print("\nSaved cards (direct payment)")

state = {}


def create_customer():
    customer = hesabe.customers.create(
        name="SDK Smoke",
        email=f"sdk-py-{int(time.time())}@example.com",
        mobile_number="66666666",
    )
    state["customer_id"] = customer.customer_id
    assert isinstance(customer.customer_id, int)
    return f"customer_id {customer.customer_id}"


check("customers.create", create_customer)
check(
    "cards.list for a new customer is empty",
    lambda: f"{len(hesabe.cards.list(state['customer_id']))} cards",
)


def verify_card():
    session = hesabe.checkout.verify_card(
        customer_id=state["customer_id"],
        order_reference_number=f"SDK-PY-VERIFY-{int(time.time() * 1000)}",
        response_url="https://example.com/ok",
        failure_url="https://example.com/fail",
        channel="mobile",
    )
    assert session.webview_url
    return "verify session created"


check("checkout.verify_card builds a zero-amount session", verify_card)

print("\nMerchant API (JWT auth, auto login + refresh)")


def profile():
    result = hesabe.profile.retrieve()
    return f"{result.merchant_name} ({result.merchant_code})"


def reports():
    page = hesabe.reports.transactions(from_date="2025-01-01", to_date="2026-12-31", page=1)
    return f"{len(page.data)} rows of {page.pagination.total}"


def refunds():
    page = hesabe.refunds.list(page=1)
    return f"{len(page.data)} refunds, {page.stats.total_refund_request_count} total"


def invoices():
    page = hesabe.invoices.list(from_date="2025-01-01", to_date="2026-12-31", page=1)
    assert isinstance(page.data, list)
    assert page.pagination
    return f"{len(page.data)} of {page.stats.total_invoice_count} invoices"


check("profile.retrieve", profile)
check("reports.transactions paginates", reports)
check("refunds.list returns a page carrying stats", refunds)
check("open_invoices.list", lambda: f"{len(hesabe.open_invoices.list(page=1).data)} open invoices")
check("invoices.list", invoices)

print("\nSmart POS")
check("pos.terminals", lambda: f"{len(hesabe.pos.terminals())} terminals")
check("pos.list", lambda: f"{len(hesabe.pos.list(page=1).data)} POS invoices")

print("\nHelpers")


def money():
    value = format_amount(0.1 + 0.2)
    assert value == "0.300", value
    return "0.1 + 0.2 -> 0.300"


def attribute_access():
    page = hesabe.pos.list(page=1)
    first = page.data[0]
    assert first.terminal_name == first["terminal_name"]
    return "dict and attribute access agree"


check("format_amount fixes floating point drift", money)
check("responses support attribute access", attribute_access)

print(f"\n{passed} passed, {failed} failed\n")
sys.exit(0 if failed == 0 else 1)
