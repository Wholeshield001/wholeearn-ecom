# Monnify Environment Variables

## MONNIFY_SOURCE_ACCOUNT_NUMBER
This is the account number Monnify uses as the source for payouts (transfers to users). It is required for initiating transfers and for Monnify to validate the origin of funds. Without this, payout requests will fail.

## MONNIFY_WEBHOOK_SECRET
This is a secret key used to verify that incoming webhook notifications (such as payment status updates) are genuinely from Monnify and not spoofed.

If your Monnify dashboard does not expose a separate webhook secret value, set this to the same value as `MONNIFY_SECRET_KEY`. The app already falls back to `MONNIFY_SECRET_KEY` when this variable is empty, but setting it explicitly keeps configuration clear.

---

**Where they are used:**
- `MONNIFY_SOURCE_ACCOUNT_NUMBER` is used in the Monnify payout/transfer API call (see `ecom/services/payments.py`, `initiate_transfer`).
- `MONNIFY_WEBHOOK_SECRET` is used to verify the signature of incoming Monnify webhook requests (see `ecom/views.py`, `_verify_monnify_webhook_signature`).

**For payouts:** `MONNIFY_SOURCE_ACCOUNT_NUMBER` is required.

**For webhooks:** `MONNIFY_WEBHOOK_SECRET` should be set (or left blank to use `MONNIFY_SECRET_KEY` fallback in code).
