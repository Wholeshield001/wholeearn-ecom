import base64
import logging
from typing import Any
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PaymentGatewayError(Exception):
    """Raised when the gateway cannot initialize or verify a payment."""


class BasePaymentProvider:
    key = "base"
    display_name = "Payment"

    def initialize_payment(self, *, amount, email: str, reference: str, callback_url: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def verify_payment(
        self,
        *,
        reference: str | None = None,
        transaction_reference: str | None = None,
        request=None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class PaystackProvider(BasePaymentProvider):
    key = "paystack"
    display_name = "Paystack"

    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.base_url = "https://api.paystack.co"

    def initialize_payment(self, *, amount, email: str, reference: str, callback_url: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.secret_key:
            raise PaymentGatewayError("Paystack is not configured.")

        amount_in_kobo = int(amount * 100)
        payload = {
            "email": email,
            "amount": amount_in_kobo,
            "reference": reference,
            "callback_url": callback_url,
            "metadata": metadata or {},
        }
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}/transaction/initialize",
                json=payload,
                headers=headers,
                timeout=15,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Paystack initialize request failed")
            raise PaymentGatewayError("Unable to connect to Paystack.") from exc
        except ValueError as exc:
            logger.exception("Paystack initialize returned non-JSON")
            raise PaymentGatewayError("Unexpected response from Paystack.") from exc

        if not data.get("status"):
            raise PaymentGatewayError(data.get("message") or "Payment initialization failed.")

        response_data = data.get("data") or {}
        return {
            "authorization_url": response_data.get("authorization_url"),
            "provider_reference": response_data.get("reference") or reference,
            "payment_reference": reference,
            "raw": data,
        }

    def verify_payment(
        self,
        *,
        reference: str | None = None,
        transaction_reference: str | None = None,
        request=None,
    ) -> dict[str, Any]:
        verify_reference = reference or transaction_reference
        if not verify_reference:
            raise PaymentGatewayError("No payment reference found.")
        if not self.secret_key:
            raise PaymentGatewayError("Paystack is not configured.")

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
        }

        try:
            response = requests.get(
                f"{self.base_url}/transaction/verify/{verify_reference}",
                headers=headers,
                timeout=15,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Paystack verify request failed")
            raise PaymentGatewayError("Unable to verify payment right now.") from exc
        except ValueError as exc:
            logger.exception("Paystack verify returned non-JSON")
            raise PaymentGatewayError("Unexpected verify response from Paystack.") from exc

        payload = data.get("data") or {}
        payment_reference = payload.get("reference") or verify_reference
        payment_status = payload.get("status") == "success"

        return {
            "success": bool(data.get("status") and payment_status),
            "payment_reference": payment_reference,
            "provider_reference": payload.get("reference") or verify_reference,
            "status": payload.get("status"),
            "raw": data,
        }


class MonnifyProvider(BasePaymentProvider):
    key = "monnify"
    display_name = "Monnify"

    def __init__(self):
        self.api_key = settings.MONNIFY_API_KEY
        self.secret_key = settings.MONNIFY_SECRET_KEY
        self.contract_code = settings.MONNIFY_CONTRACT_CODE
        self.base_url = settings.MONNIFY_BASE_URL.rstrip("/")

    def _get_access_token(self) -> str:
        if not self.api_key or not self.secret_key:
            raise PaymentGatewayError("Monnify API key/secret is not configured.")

        raw = f"{self.api_key}:{self.secret_key}".encode("utf-8")
        token = base64.b64encode(raw).decode("utf-8")

        headers = {
            "Authorization": f"Basic {token}",
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/v1/auth/login",
                headers=headers,
                timeout=15,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Monnify auth request failed")
            raise PaymentGatewayError("Unable to authenticate with Monnify.") from exc
        except ValueError as exc:
            logger.exception("Monnify auth returned non-JSON")
            raise PaymentGatewayError("Unexpected auth response from Monnify.") from exc

        if not data.get("requestSuccessful"):
            raise PaymentGatewayError(data.get("responseMessage") or "Monnify authentication failed.")

        access_token = (data.get("responseBody") or {}).get("accessToken")
        if not access_token:
            raise PaymentGatewayError("Monnify access token not returned.")
        return access_token

    def initialize_payment(self, *, amount, email: str, reference: str, callback_url: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.contract_code:
            raise PaymentGatewayError("Monnify contract code is not configured.")

        access_token = self._get_access_token()
        payload = {
            "amount": float(amount),
            "customerName": (metadata or {}).get("customer_name") or email,
            "customerEmail": email,
            "paymentReference": reference,
            "paymentDescription": "WholeShield order payment",
            "currencyCode": "NGN",
            "contractCode": self.contract_code,
            "redirectUrl": callback_url,
            "paymentMethods": ["CARD", "ACCOUNT_TRANSFER", "USSD"],
            "metadata": metadata or {},
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}/api/v1/merchant/transactions/init-transaction",
                json=payload,
                headers=headers,
                timeout=15,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Monnify initialize request failed")
            raise PaymentGatewayError("Unable to connect to Monnify.") from exc
        except ValueError as exc:
            logger.exception("Monnify initialize returned non-JSON")
            raise PaymentGatewayError("Unexpected response from Monnify.") from exc

        if not data.get("requestSuccessful"):
            raise PaymentGatewayError(data.get("responseMessage") or "Payment initialization failed.")

        response_data = data.get("responseBody") or {}
        return {
            "authorization_url": response_data.get("checkoutUrl"),
            "provider_reference": response_data.get("transactionReference"),
            "payment_reference": response_data.get("paymentReference") or reference,
            "raw": data,
        }

    def verify_payment(
        self,
        *,
        reference: str | None = None,
        transaction_reference: str | None = None,
        request=None,
    ) -> dict[str, Any]:
        access_token = self._get_access_token()
        query_reference = transaction_reference
        if not query_reference and request is not None:
            query_reference = request.GET.get("transactionReference") or request.GET.get("transaction_reference")

        payment_reference = reference
        if not payment_reference and request is not None:
            payment_reference = request.GET.get("paymentReference") or request.GET.get("payment_reference")

        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        # Prefer transaction reference lookup when available.
        # Monnify transaction references contain pipe characters (e.g. MNFY|date|id)
        # that must be percent-encoded when used in a URL path segment.
        if query_reference:
            verify_url = f"{self.base_url}/api/v2/transactions/{quote(query_reference, safe='')}"
            params = None
        else:
            if not payment_reference:
                raise PaymentGatewayError("No payment reference provided for Monnify verification.")
            verify_url = f"{self.base_url}/api/v2/transactions/query"
            params = {"paymentReference": payment_reference}

        try:
            response = requests.get(verify_url, headers=headers, params=params, timeout=15)
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Monnify verify request failed")
            raise PaymentGatewayError("Unable to verify Monnify payment right now.") from exc
        except ValueError as exc:
            logger.exception("Monnify verify returned non-JSON")
            raise PaymentGatewayError("Unexpected verify response from Monnify.") from exc

        if not data.get("requestSuccessful"):
            raise PaymentGatewayError(data.get("responseMessage") or "Monnify verification failed.")

        response_data = data.get("responseBody") or {}
        payment_status = (response_data.get("paymentStatus") or "").upper()

        return {
            "success": payment_status in {"PAID", "OVERPAID"},
            "payment_reference": response_data.get("paymentReference") or payment_reference,
            "provider_reference": response_data.get("transactionReference") or query_reference,
            "status": payment_status,
            "raw": data,
        }

    def verify_bank_account(self, *, account_number: str, bank_code: str) -> dict[str, Any]:
        """Resolve account details before saving payout destination."""
        access_token = self._get_access_token()
        endpoint = getattr(
            settings,
            "MONNIFY_ACCOUNT_LOOKUP_ENDPOINT",
            "/api/v1/disbursements/account/validate",
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        try:
            response = requests.get(
                f"{self.base_url}{endpoint}",
                params={
                    "accountNumber": account_number,
                    "bankCode": bank_code,
                },
                headers=headers,
                timeout=15,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Monnify account validation request failed")
            raise PaymentGatewayError("Unable to verify bank account right now.") from exc
        except ValueError as exc:
            logger.exception("Monnify account validation returned non-JSON")
            raise PaymentGatewayError("Unexpected account verification response from Monnify.") from exc

        if not data.get("requestSuccessful"):
            raise PaymentGatewayError(data.get("responseMessage") or "Bank account verification failed.")

        response_data = data.get("responseBody") or {}
        return {
            "account_name": response_data.get("accountName"),
            "account_number": response_data.get("accountNumber") or account_number,
            "bank_code": response_data.get("bankCode") or bank_code,
            "bank_name": response_data.get("bankName"),
            "account_reference": response_data.get("accountReference"),
            "raw": data,
        }

    def initiate_transfer(
        self,
        *,
        amount,
        reference: str,
        narration: str,
        account_number: str,
        bank_code: str,
        account_name: str,
    ) -> dict[str, Any]:
        """Initiate a single payout transfer via Monnify."""
        access_token = self._get_access_token()
        endpoint = getattr(
            settings,
            "MONNIFY_TRANSFER_ENDPOINT",
            "/api/v2/disbursements/single",
        )
        payload = {
            "amount": float(amount),
            "reference": reference,
            "narration": narration,
            "destinationBankCode": bank_code,
            "destinationAccountNumber": account_number,
            "destinationAccountName": account_name,
            "currency": "NGN",
            "sourceAccountNumber": getattr(settings, "MONNIFY_SOURCE_ACCOUNT_NUMBER", ""),
        }
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                f"{self.base_url}{endpoint}",
                json=payload,
                headers=headers,
                timeout=20,
            )
            data = response.json()
        except requests.RequestException as exc:
            logger.exception("Monnify transfer request failed")
            raise PaymentGatewayError("Unable to process withdrawal payout right now.") from exc
        except ValueError as exc:
            logger.exception("Monnify transfer returned non-JSON")
            raise PaymentGatewayError("Unexpected transfer response from Monnify.") from exc

        if not data.get("requestSuccessful"):
            raise PaymentGatewayError(data.get("responseMessage") or "Withdrawal payout failed.")

        response_data = data.get("responseBody") or {}
        return {
            "success": True,
            "provider_reference": response_data.get("reference") or response_data.get("transactionReference"),
            "status": response_data.get("status") or "SUCCESS",
            "raw": data,
        }

    def list_banks(self) -> list[dict[str, Any]]:
        """Fetch available destination banks for transfer/account verification."""
        access_token = self._get_access_token()
        configured_endpoint = getattr(settings, "MONNIFY_BANKS_ENDPOINT", "/api/v1/banks")
        candidate_endpoints = [configured_endpoint]
        if configured_endpoint != "/api/v1/banks":
            candidate_endpoints.append("/api/v1/banks")

        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        last_error = None
        data: dict[str, Any] | None = None
        for endpoint in candidate_endpoints:
            try:
                response = requests.get(f"{self.base_url}{endpoint}", headers=headers, timeout=15)
                data = response.json()
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Monnify banks request failed for endpoint %s", endpoint, exc_info=True)
                continue
            except ValueError as exc:
                last_error = exc
                logger.warning("Monnify banks response is non-JSON for endpoint %s", endpoint, exc_info=True)
                continue

            if data.get("requestSuccessful"):
                break

            # Try fallback endpoint on hard endpoint mismatch (e.g., stale /api/v2/banks)
            if response.status_code == 404:
                logger.warning("Monnify banks endpoint not found, trying fallback | endpoint=%s", endpoint)
                continue

            last_error = PaymentGatewayError(data.get("responseMessage") or "Unable to fetch banks.")

        if not data or not data.get("requestSuccessful"):
            if isinstance(last_error, PaymentGatewayError):
                raise last_error
            if last_error:
                raise PaymentGatewayError("Unable to fetch bank list right now.") from last_error
            raise PaymentGatewayError("Unable to fetch banks.")

        response_data = data.get("responseBody") or []
        banks = []
        for row in response_data:
            code = row.get("code") or row.get("bankCode") or row.get("cbnCode")
            name = row.get("name") or row.get("bankName")
            if code and name:
                banks.append({"code": str(code), "name": str(name)})
        return banks


def get_payment_provider(provider_key: str | None = None) -> BasePaymentProvider:
    key = (provider_key or settings.PAYMENT_PROVIDER or "paystack").strip().lower()
    providers = {
        PaystackProvider.key: PaystackProvider,
        MonnifyProvider.key: MonnifyProvider,
    }
    provider_cls = providers.get(key)
    if not provider_cls:
        raise PaymentGatewayError(f"Unsupported payment provider: {key}")
    return provider_cls()


def get_active_payment_provider() -> BasePaymentProvider:
    provider_key = settings.PAYMENT_PROVIDER
    try:
        from ecom.models import PaymentProviderConfig

        config = PaymentProviderConfig.get_solo()
        if config.active_provider:
            provider_key = config.active_provider
    except Exception:
        # Fall back to environment setting when DB config is unavailable.
        pass

    return get_payment_provider(provider_key)
