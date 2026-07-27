# hesabe-python

Hand-written Python SDK for the Hesabe payment gateway (Kuwait), built and verified
against the live sandbox. Heavily inspired by stripe-python, scaled to a small team.
Sibling SDK: [hesabe-node](https://github.com/ruptyx/hesabe-node).

## Testing

- Unit suite: `python -m unittest discover -s tests`
- Single file: `python -m unittest tests.test_http`
- Live sandbox: `python tests/smoke.py`

The unit suite is hermetic (scripted `SendFunc`; no network). The smoke suite hits the
real sandbox with Hesabe's published test credentials — those credentials are public
documentation, safe to keep in the repo.

## Formatting & Linting

- `ruff format .` and `ruff check .` (config in `pyproject.toml`)

## Key Locations

- Transport (retries, Retry-After, envelope sniffing, HTTP backend selection): `hesabe/http.py`
- Crypto (AES-256-CBC, 32-byte padding, hex): `hesabe/crypto.py`, pure-Python fallback in `hesabe/_aes.py`
- Bearer-token session (leader/waiter, stale-while-refresh): `hesabe/session.py`
- Config resolution (env vars, opt-in dotenv, environment guard): `hesabe/config.py`
- Amount formatting and shared types: `hesabe/types.py`
- Endpoint wrappers: `hesabe/resources/`
- Cross-SDK parity fixtures: `fixtures/` (canonical copy; regenerate with `python fixtures/generate_cipher_vectors.py`, then copy the JSON into hesabe-node)

## Cardinal Rules

1. **Probed behavior beats the docs.** developer.hesabe.com lags the real API. Known
   intentional deviations: `isOrderReference` as a query param, `isScheduled` as
   `"true"`/`"false"` strings, optional `channel`/`fromDate`/`toDate`,
   `orderReferenceNumber` on VERIFY sessions. Never "fix" code to match the docs
   without proving it against the sandbox first — settle disputes with the smoke suite.
2. **This SDK stays behaviorally identical to hesabe-node.** Any change to crypto,
   amount formatting, retry policy, or payload construction lands in both repos, and
   any crypto/amount change must keep `fixtures/cipher-vectors.json` and
   `fixtures/amount-vectors.json` passing in both. Cipher fixtures must stay ASCII-only
   with string-typed decimals (the only regime where `json.dumps` and `JSON.stringify`
   produce identical bytes). This repo owns the generator; sync the JSON to hesabe-node
   after regenerating.
3. **Zero required dependencies.** The stdlib baseline must always work. Optional
   accelerators are detected at import (`cryptography`/`pycryptodome` for AES,
   `httpx`/`urllib3` for pooled HTTP) — never promote one to a hard dependency.
4. **All money goes through `format_amount`.** Three decimals, half-up, exact Decimal
   arithmetic. Never do float math on amounts; never bypass the formatter when building
   payloads. KWD is a 3-decimal currency — this is load-bearing.
5. **Never trust customer-transported payloads.** Redirect data and webhooks are
   decrypt-only (CBC has no MAC) or entirely unsigned. Fulfillment paths must go
   through `transactions.verify_redirect` / `webhooks.verify`, which re-read the
   transaction from the API. Keep that framing in any new docs or examples.
6. **Retry semantics are deliberate.** GETs are replayable; 429s are always replayable
   (rejected before processing); other non-idempotent calls fail fast — Hesabe has no
   idempotency keys, so retrying an ambiguous POST risks double-charging. Redirects
   are refused in every HTTP backend (`accessCode` must never follow one).
7. **The crypto is HesabeCrypt-compatible, not textbook.** AES-256-CBC with manual
   padding to 32-byte blocks (pad byte = pad length), cipher-level padding disabled,
   lowercase hex. Do not "correct" it to PKCS7/16 — it matches Hesabe's reference kit.
8. **Checkout version selection:** any of save_card / channel / embedded / subscription
   / customer_id (truthy) ⇒ `version: "3.0"`, else `"2.0"`; an explicit `version` wins.
   Use truthiness, not None-checks (regression tests pin this).

## Conventions

- Python 3.9+, stdlib-only baseline, `py.typed` shipped.
- Errors: raise the typed `Hesabe*Error` hierarchy; every error carries
  `message`, `code`, `status_code`, `raw`.
- Dotenv is opt-in (`env_path=`); constructing a client must never mutate
  `os.environ` on its own.
- Comments explain WHY or document a function — never what the code obviously does,
  never what used to be there.
- Work is not complete until the unit suite passes and — for transport/crypto/session
  changes — the smoke suite passes against the sandbox.

## Known Loose Ends

- The production merchant-API base URL (`merchantapi.hesabe.com`) is absent from the
  current docs; confirm with Hesabe support (support@hesabe.com) before the first
  production use of the merchant namespace (invoices/refunds/reports/POS).
- Hesabe documents no failure `resultCode` values and no webhook signature; if either
  ever appears in the docs, revisit `hesabe/webhooks.py`.
