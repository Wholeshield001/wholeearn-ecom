from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ecom.models import (
    RewardPointConfig,
    RewardPointLedger,
    RewardConversion,
    UserWallet,
    WalletBankAccount,
    WalletWithdrawalRequest,
)
from ecom.services.payments import PaymentGatewayError, get_payment_provider
from users.models import User


class WalletOperationError(Exception):
    """Raised when a wallet operation cannot be completed."""


def _to_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_DOWN)


def convert_points_to_wallet(*, user: User, points: int) -> RewardConversion:
    """Convert reward points to wallet money at the configured rate."""
    if points <= 0:
        raise WalletOperationError('Points to convert must be greater than zero.')

    config = RewardPointConfig.get_solo()
    rate = Decimal(str(config.points_to_naira_rate or 0))
    if rate <= 0:
        raise WalletOperationError('Point to naira rate is not configured yet.')

    with transaction.atomic():
        user_locked = User.objects.select_for_update().get(pk=user.pk)
        if user_locked.reward_points < points:
            raise WalletOperationError('Insufficient reward points for conversion.')

        wallet = UserWallet.get_for_user(user_locked)
        wallet = UserWallet.objects.select_for_update().get(pk=wallet.pk)

        naira_amount = _to_money(Decimal(points) * rate)
        if naira_amount <= 0:
            raise WalletOperationError('Calculated wallet value must be greater than zero.')

        user_locked.reward_points = F('reward_points') - points
        user_locked.save(update_fields=['reward_points'])

        wallet.available_balance = F('available_balance') + naira_amount
        wallet.total_converted = F('total_converted') + naira_amount
        wallet.save(update_fields=['available_balance', 'total_converted', 'updated_at'])

        reference = f"CNV-{timezone.now().strftime('%Y%m%d%H%M%S%f')}-{user_locked.id.hex[:6].upper()}"
        conversion = RewardConversion.objects.create(
            user=user_locked,
            wallet=wallet,
            points=points,
            naira_amount=naira_amount,
            rate_snapshot=rate,
            reference=reference,
            status=RewardConversion.SUCCESS,
        )
        RewardPointLedger.objects.create(
            user=user_locked,
            points=-points,
            reason=RewardPointLedger.CONVERSION_DEBIT,
        )

    return conversion


def add_or_update_bank_account(
    *,
    user: User,
    account_number: str,
    bank_code: str,
    set_default: bool = True,
    bank_name: str | None = None,
) -> WalletBankAccount:
    """Add and verify a payout bank account using Monnify account lookup."""
    account_number = (account_number or '').strip()
    bank_code = (bank_code or '').strip()
    if not account_number or not bank_code:
        raise WalletOperationError('Bank code and account number are required.')

    provider = get_payment_provider('monnify')
    if not hasattr(provider, 'verify_bank_account'):
        raise WalletOperationError('Monnify account verification is not available yet.')

    try:
        verification = provider.verify_bank_account(account_number=account_number, bank_code=bank_code)
    except PaymentGatewayError as exc:
        raise WalletOperationError(str(exc)) from exc

    account_name = verification.get('account_name')
    if not account_name:
        raise WalletOperationError('Unable to verify this bank account.')

    with transaction.atomic():
        account, _ = WalletBankAccount.objects.update_or_create(
            user=user,
            account_number=account_number,
            bank_code=bank_code,
            defaults={
                'account_name': account_name,
                'bank_name': bank_name or verification.get('bank_name'),
                'is_verified': True,
                'is_active': True,
                'monnify_account_reference': verification.get('account_reference'),
                'verified_at': timezone.now(),
            },
        )

        if set_default:
            WalletBankAccount.objects.filter(user=user).exclude(pk=account.pk).update(is_default=False)
            account.is_default = True
            account.save(update_fields=['is_default', 'updated_at'])

    return account


def create_withdrawal_request(*, user: User, amount: Decimal, bank_account: WalletBankAccount, idempotency_key: str | None = None) -> WalletWithdrawalRequest:
    """Reserve wallet funds and create a withdrawal request."""
    amount = _to_money(Decimal(str(amount or 0)))
    if amount <= 0:
        raise WalletOperationError('Withdrawal amount must be greater than zero.')

    config = RewardPointConfig.get_solo()
    minimum = Decimal(str(config.minimum_withdrawal_amount or 0))
    if amount < minimum:
        raise WalletOperationError(f'Minimum withdrawal amount is {minimum:.2f}.')

    if bank_account.user_id != user.id or not bank_account.is_verified or not bank_account.is_active:
        raise WalletOperationError('Please use an active verified bank account.')

    idempotency_key = (idempotency_key or '').strip() or None

    with transaction.atomic():
        wallet = UserWallet.get_for_user(user)
        wallet = UserWallet.objects.select_for_update().get(pk=wallet.pk)

        if idempotency_key:
            existing = WalletWithdrawalRequest.objects.select_for_update().filter(idempotency_key=idempotency_key, user=user).first()
            if existing:
                return existing

        # Guard against concurrent or duplicate withdrawal submissions
        if WalletWithdrawalRequest.objects.filter(
            user=user,
            status__in=[WalletWithdrawalRequest.PENDING, WalletWithdrawalRequest.PROCESSING],
        ).exists():
            raise WalletOperationError(
                'A withdrawal is already in progress. Please wait for it to complete before requesting another.'
            )

        if wallet.available_balance < amount:
            raise WalletOperationError('Insufficient wallet balance.')

        wallet.available_balance = F('available_balance') - amount
        wallet.pending_balance = F('pending_balance') + amount
        wallet.save(update_fields=['available_balance', 'pending_balance', 'updated_at'])

        reference = f"WDR-{idempotency_key}" if idempotency_key else f"WDR-{timezone.now().strftime('%Y%m%d%H%M%S%f')}-{user.id.hex[:6].upper()}"
        withdrawal = WalletWithdrawalRequest.objects.create(
            user=user,
            wallet=wallet,
            bank_account=bank_account,
            amount=amount,
            reference=reference,
            idempotency_key=idempotency_key,
            status=WalletWithdrawalRequest.PENDING,
        )

    return withdrawal


def process_withdrawal_request(withdrawal: WalletWithdrawalRequest) -> WalletWithdrawalRequest:
    """Send withdrawal payout request to Monnify and settle wallet balances."""
    if withdrawal.status not in {WalletWithdrawalRequest.PENDING, WalletWithdrawalRequest.FAILED}:
        return withdrawal

    provider = get_payment_provider('monnify')
    if not hasattr(provider, 'initiate_transfer'):
        raise WalletOperationError('Monnify transfer is not available yet.')

    with transaction.atomic():
        locked = WalletWithdrawalRequest.objects.select_for_update().get(pk=withdrawal.pk)
        wallet = UserWallet.objects.select_for_update().get(pk=locked.wallet_id)

        if locked.status == WalletWithdrawalRequest.FAILED:
            # Retrying a failed payout requires reserving funds again.
            if wallet.available_balance < locked.amount:
                raise WalletOperationError('Insufficient wallet balance to retry this withdrawal.')
            wallet.available_balance = F('available_balance') - locked.amount
            wallet.pending_balance = F('pending_balance') + locked.amount
            wallet.save(update_fields=['available_balance', 'pending_balance', 'updated_at'])

        WalletWithdrawalRequest.objects.filter(pk=locked.pk).update(
            status=WalletWithdrawalRequest.PROCESSING,
            failure_reason='',
        )

    withdrawal.refresh_from_db()

    try:
        response = provider.initiate_transfer(
            amount=withdrawal.amount,
            reference=withdrawal.reference,
            narration='WholeShield reward wallet withdrawal',
            account_number=withdrawal.bank_account.account_number,
            bank_code=withdrawal.bank_account.bank_code,
            account_name=withdrawal.bank_account.account_name,
        )
        provider_reference = response.get('provider_reference')

        with transaction.atomic():
            wallet = UserWallet.objects.select_for_update().get(pk=withdrawal.wallet_id)
            wallet.pending_balance = F('pending_balance') - withdrawal.amount
            wallet.total_withdrawn = F('total_withdrawn') + withdrawal.amount
            wallet.save(update_fields=['pending_balance', 'total_withdrawn', 'updated_at'])

            WalletWithdrawalRequest.objects.filter(pk=withdrawal.pk).update(
                status=WalletWithdrawalRequest.SUCCESS,
                monnify_reference=provider_reference,
                provider_response=response.get('raw') or response,
                processed_at=timezone.now(),
                failure_reason='',
            )
            _queue_withdrawal_completion_email(str(withdrawal.pk))
    except Exception as exc:
        with transaction.atomic():
            wallet = UserWallet.objects.select_for_update().get(pk=withdrawal.wallet_id)
            wallet.pending_balance = F('pending_balance') - withdrawal.amount
            wallet.available_balance = F('available_balance') + withdrawal.amount
            wallet.save(update_fields=['pending_balance', 'available_balance', 'updated_at'])

            WalletWithdrawalRequest.objects.filter(pk=withdrawal.pk).update(
                status=WalletWithdrawalRequest.FAILED,
                failure_reason=str(exc),
                processed_at=timezone.now(),
            )
        raise WalletOperationError(str(exc)) from exc

    withdrawal.refresh_from_db()
    return withdrawal


def queue_withdrawal_request(withdrawal: WalletWithdrawalRequest) -> WalletWithdrawalRequest:
    """Transition a withdrawal to processing and queue provider payout.

    This is the async entry point used by Celery tasks.
    """
    return process_withdrawal_request(withdrawal)


def _queue_withdrawal_completion_email(withdrawal_id: str):
    from ecom.tasks import send_withdrawal_completed_email_task

    transaction.on_commit(lambda: send_withdrawal_completed_email_task.delay(withdrawal_id))


def apply_withdrawal_status_update(
    *,
    reference: str,
    status: str,
    provider_reference: str | None = None,
    raw_payload: dict | None = None,
) -> WalletWithdrawalRequest | None:
    """Apply Monnify webhook status update to a withdrawal request safely and idempotently."""
    if not reference:
        return None

    normalized = (status or '').strip().upper()
    is_success = normalized in {'SUCCESS', 'SUCCESSFUL', 'COMPLETED', 'PAID'}
    is_failure = normalized in {'FAILED', 'FAIL', 'REVERSED', 'CANCELLED'}

    if not (is_success or is_failure):
        return WalletWithdrawalRequest.objects.filter(reference=reference).first()

    with transaction.atomic():
        withdrawal = WalletWithdrawalRequest.objects.select_for_update().filter(reference=reference).first()
        if not withdrawal:
            return None

        # Idempotent guard: do nothing if already settled.
        if withdrawal.status in {WalletWithdrawalRequest.SUCCESS, WalletWithdrawalRequest.FAILED}:
            return withdrawal

        wallet = UserWallet.objects.select_for_update().get(pk=withdrawal.wallet_id)
        update_fields = {
            'provider_response': raw_payload or withdrawal.provider_response,
            'monnify_reference': provider_reference or withdrawal.monnify_reference,
            'processed_at': timezone.now(),
        }

        if is_success:
            wallet.pending_balance = F('pending_balance') - withdrawal.amount
            wallet.total_withdrawn = F('total_withdrawn') + withdrawal.amount
            wallet.save(update_fields=['pending_balance', 'total_withdrawn', 'updated_at'])
            update_fields['status'] = WalletWithdrawalRequest.SUCCESS
            update_fields['failure_reason'] = ''
        else:
            wallet.pending_balance = F('pending_balance') - withdrawal.amount
            wallet.available_balance = F('available_balance') + withdrawal.amount
            wallet.save(update_fields=['pending_balance', 'available_balance', 'updated_at'])
            update_fields['status'] = WalletWithdrawalRequest.FAILED
            update_fields['failure_reason'] = f'Monnify reported status: {normalized}'

        WalletWithdrawalRequest.objects.filter(pk=withdrawal.pk).update(**update_fields)
        if is_success:
            _queue_withdrawal_completion_email(str(withdrawal.pk))

    return WalletWithdrawalRequest.objects.get(pk=withdrawal.pk)
