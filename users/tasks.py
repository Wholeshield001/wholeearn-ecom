import logging

from celery import shared_task

from users.emails import (
    send_kyc_approved_email,
    send_kyc_rejected_email,
    send_kyc_submitted_admin_email,
    send_kyc_submitted_email,
)
from users.models import KYCSubmission, KYCSubmissionAuditLog

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_kyc_status_update_email_task(self, submission_id: str):
    """Send KYC status update email asynchronously with retries."""
    try:
        submission = KYCSubmission.objects.select_related('user').get(id=submission_id)
    except KYCSubmission.DoesNotExist:
        logger.warning("KYC submission %s not found for queued email", submission_id)
        return

    try:
        if submission.status == KYCSubmission.APPROVED:
            sent = send_kyc_approved_email(submission.user)
        elif submission.status == KYCSubmission.REJECTED:
            sent = send_kyc_rejected_email(submission.user, submission.rejection_reason or '')
        else:
            logger.info(
                "Skipping KYC status email for submission %s with status %s",
                submission_id,
                submission.status,
            )
            return

        if not sent:
            raise RuntimeError("KYC status email send returned False")

        KYCSubmissionAuditLog.objects.create(
            submission=submission,
            event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
            email_status=KYCSubmissionAuditLog.EMAIL_SENT,
            message='KYC status email sent successfully.',
            metadata={
                'task_id': self.request.id,
                'attempt': self.request.retries + 1,
                'status': submission.status,
            },
        )

        logger.info(
            "Queued KYC status email sent for submission %s (status=%s)",
            submission_id,
            submission.status,
        )
    except Exception as exc:
        KYCSubmissionAuditLog.objects.create(
            submission=submission,
            event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
            email_status=KYCSubmissionAuditLog.EMAIL_FAILED,
            message='KYC status email send attempt failed.',
            metadata={
                'task_id': self.request.id,
                'attempt': self.request.retries + 1,
                'error': str(exc),
                'status': submission.status,
            },
        )
        countdown = 60 * (2 ** self.request.retries)
        logger.warning(
            "KYC status email failed for submission %s (attempt %d): %s. Retrying in %ss",
            submission_id,
            self.request.retries + 1,
            exc,
            countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def send_kyc_submission_email_task(self, submission_id: str):
    """Send KYC submission emails (user + admins) asynchronously with retries."""
    try:
        submission = KYCSubmission.objects.select_related('user').get(id=submission_id)
    except KYCSubmission.DoesNotExist:
        logger.warning("KYC submission %s not found for queued submission email", submission_id)
        return

    try:
        user_sent = send_kyc_submitted_email(submission.user, submission)
        admin_sent = send_kyc_submitted_admin_email(submission.user, submission)

        if not (user_sent and admin_sent):
            raise RuntimeError("One or more KYC submission emails failed")

        KYCSubmissionAuditLog.objects.create(
            submission=submission,
            event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
            email_status=KYCSubmissionAuditLog.EMAIL_SENT,
            message='KYC submission emails sent successfully.',
            metadata={
                'task_id': self.request.id,
                'attempt': self.request.retries + 1,
                'user_email_sent': bool(user_sent),
                'admin_email_sent': bool(admin_sent),
            },
        )
        logger.info("Queued KYC submission emails sent for submission %s", submission_id)
    except Exception as exc:
        KYCSubmissionAuditLog.objects.create(
            submission=submission,
            event_type=KYCSubmissionAuditLog.EVENT_EMAIL,
            email_status=KYCSubmissionAuditLog.EMAIL_FAILED,
            message='KYC submission email send attempt failed.',
            metadata={
                'task_id': self.request.id,
                'attempt': self.request.retries + 1,
                'error': str(exc),
            },
        )
        countdown = 60 * (2 ** self.request.retries)
        logger.warning(
            "KYC submission emails failed for submission %s (attempt %d): %s. Retrying in %ss",
            submission_id,
            self.request.retries + 1,
            exc,
            countdown,
        )
        raise self.retry(exc=exc, countdown=countdown)
