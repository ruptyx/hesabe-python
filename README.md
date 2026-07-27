# hesabe

Hesabe Payment Gateway SDK for Python. No required dependencies.
Also available for Node.js: [hesabe-node](https://github.com/ruptyx/hesabe-node).

```bash
pip install hesabe
```

Requires Python 3.9+. Uses only the standard library. If `cryptography` or `pycryptodome`
is installed it is used for AES automatically; otherwise a bundled implementation
(NIST-vector tested) is used with a `UserWarning`, since it is not constant-time.
Likewise, if `httpx` or `urllib3` is installed, HTTP connections are pooled and
reused; otherwise each request opens a new connection via `urllib`.

```python
>>> import hesabe; hesabe.BACKEND, hesabe.HTTP_BACKEND
('cryptography', 'httpx')
```

## Setup

Credentials come from the environment. To read them from a dotenv file, opt in with
`Hesabe(env_path=".env")`; real environment variables always take precedence.

```bash
HESABE_ENVIRONMENT=sandbox          # or production
HESABE_MERCHANT_CODE=...
HESABE_ACCESS_CODE=...
HESABE_SECRET_KEY=...               # 32 characters
HESABE_IV_KEY=...                   # 16 characters
HESABE_MERCHANT_USERNAME=...        # invoices, refunds, reports, POS only
HESABE_MERCHANT_PASSWORD=...
```

```python
from hesabe import Hesabe

hesabe = Hesabe()
```

Everything is overridable in code:

```python
hesabe = Hesabe(
    merchant_code="842217",
    access_code="…",
    secret_key="…",
    iv_key="…",
    environment="production",
    timeout=20.0,
    max_retries=3,
)
```

Responses are dicts that also allow attribute access:

```python
session = hesabe.checkout.create(...)
session.payment_url == session["payment_url"]
```

## Accepting a payment

```python
session = hesabe.checkout.create(
    amount=12.5,
    order_reference_number="ORDER-1001",
    response_url="https://yourshop.com/paid",
    failure_url="https://yourshop.com/failed",
    email="customer@example.com",
    webhook_url="https://yourshop.com/hesabe/webhook",
)

return redirect(session.payment_url)
```

Choosing a specific rail instead of the hosted picker:

```python
from hesabe import PaymentType

hesabe.checkout.create(payment_type=PaymentType.KNET, ...)
```

Mobile apps get a WebView URL back:

```python
session = hesabe.checkout.create(channel="mobile", payment_type=PaymentType.MPGS, ...)
session.webview_url
```

Embedding the form in your own page:

```python
session = hesabe.checkout.create(embedded=True, ...)
# pass session.data to the browser SDK as its sessionID
```

## Handling the result

```python
confirmed = hesabe.transactions.verify_redirect(request.args["data"])
if confirmed.status == "SUCCESSFUL":
    fulfil(confirmed.reference_number)
```

`verify_redirect` decrypts what the browser carried back, then re-reads the transaction
from Hesabe and returns that authoritative copy — the redirect passes through the
customer, and decryption alone proves nothing. `parse_redirect` is available when you
only need the decrypted payload.

## Saved cards

One 3DS verification, then charge from your backend whenever you like.

```python
customer = hesabe.customers.create(
    name="Ahmed Al-Mansouri",
    email="ahmed@example.com",
    mobile_number="66666666",
)

session = hesabe.checkout.verify_card(
    customer_id=customer.customer_id,
    order_reference_number="SAVE-CARD-1",
    response_url="https://yourshop.com/card-saved",
    failure_url="https://yourshop.com/card-failed",
)
return redirect(session.payment_url)

# Later, on your callback: result.cardId is the saved card.
payment = hesabe.cards.charge(
    card_id=77,
    amount=9.9,
    customer_id=customer.customer_id,
    order_reference="INVOICE-2025-001",
)

hesabe.cards.list(customer.customer_id)
hesabe.cards.remove(77)
```

`cards.charge` sends your access code. Never expose it to a browser or mobile client.

## Authorize then capture

MPGS only. Reserves the funds now, takes them when you ship.

```python
hesabe.checkout.create(authorize=True, payment_type=PaymentType.MPGS, ...)

hesabe.authorizations.capture(payment_token=token, amount=25)
hesabe.authorizations.cancel(token)
```

## Subscriptions

```python
hesabe.checkout.create(
    amount=0,
    payment_type=PaymentType.CYBERSOURCE_SUBSCRIPTION,
    subscription={
        "recurring_frequency": 1,        # 1 monthly, 0 on demand
        "number_of_installments": 12,
        "recurring_start_date": "2026-09-01",
        "recurring_amount": 4.5,
    },
    ...
)

hesabe.subscriptions.capture(
    payment_token=token, amount=4.5, order_reference_number="SUB-9"
)
hesabe.subscriptions.cancel(subscription_token)
```

## Invoices, refunds, reports

These use the Merchant API. The bearer token is fetched and refreshed for you — you only
need `HESABE_MERCHANT_USERNAME` and `HESABE_MERCHANT_PASSWORD`.

```python
invoice = hesabe.invoices.create(
    amount=20,
    invoice_type="1",              # "1" SMS, "0" link
    mobile_number="66666666",
    country_code="965",
    customer_name="Ahmed",
    allocate_pay_type=[1, 2],      # KNET and MPGS only
)
invoice.url

page = hesabe.invoices.list(page=1, from_date="2026-01-01", to_date="2026-12-31")
page.data, page.pagination, page.stats

hesabe.invoices.cancel(invoice.token)
hesabe.invoices.resend(
    invoice_id=invoice.id, mobile_number="66666666", country_code="965"
)

refund = hesabe.refunds.create(token=payment_token, amount=5, method="partial")
refunds = hesabe.refunds.list(page=1)

report = hesabe.reports.transactions(
    from_date="2026-01-01", to_date="2026-12-31", payment_status=1, page=1
)
```

Shareable payment links:

```python
hesabe.open_invoices.create(title="Donation", min_amount=1, max_amount=100)
hesabe.open_invoices.create(title="Course fee", fix_amount=45)
```

## Smart POS

```python
terminals = hesabe.pos.terminals()

hesabe.pos.create(
    customer_name="Salman",
    amount=3.75,
    terminal_id=terminals[0].TerminalID,
)

hesabe.pos.list(page=1)
hesabe.pos.transactions(from_date="2026-01-01", to_date="2026-12-31")
```

## Webhooks

Hesabe webhooks carry no signature. `verify` re-reads the transaction from the API and
returns that copy instead of trusting the request body.

```python
@app.post("/hesabe/webhook")
def webhook():
    try:
        event = hesabe.webhooks.verify(request.get_data())
        if event.status == "SUCCESSFUL":
            fulfil(event.reference_number)
    except HesabeSignatureError as exc:
        logger.warning("rejected webhook: %s", exc)
    return "", 200
```

## Errors

```python
from hesabe import HesabeCardError, HesabeInvalidRequestError, HesabeRateLimitError

try:
    hesabe.cards.charge(card_id=77, amount=9.9)
except HesabeCardError as exc:
    decline_order(exc.message)
except HesabeInvalidRequestError as exc:
    bad_request(exc.field_errors)
except HesabeRateLimitError:
    retry_later()
```

Every error carries `message`, `code` (Hesabe's inner code), `status_code`, and `raw`.

## Amounts

Pass `int`, `float`, `str`, or `Decimal`; all are normalised to three decimals before
sending. `Decimal` is used internally, so no float drift reaches the API.

```python
from hesabe import format_amount

format_amount(0.1 + 0.2)  # "0.300"
```

## Testing

```bash
python -m unittest discover -s tests   # unit suite: crypto vectors, transport, session
python tests/smoke.py                  # live checks against the Hesabe sandbox
```
