from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class PartnerAndReferralRemovalTests(TestCase):
    def test_signup_and_partner_signup_do_not_require_or_assign_referral(self):
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'referral_code_input')

        partner_resp = self.client.get(reverse('partner-signup'))
        self.assertEqual(partner_resp.status_code, 200)
        self.assertNotContains(partner_resp, 'referral_code_input')

    def test_dashboard_and_reward_hide_referral_sections(self):
        user = User.objects.create_user(
            email='partner@example.com',
            password='strong-pass-123',
            first_name='Partner',
            role=User.WHOLESALER,
            is_active=True,
            email_verified=True,
        )
        self.client.force_login(user)

        dash_resp = self.client.get(reverse('user-dashboard'))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertNotContains(dash_resp, 'Your Referral Link')

        reward_resp = self.client.get(reverse('reward-dashboard'))
        self.assertEqual(reward_resp.status_code, 200)
        self.assertNotContains(reward_resp, 'Your Referral Link')
        self.assertContains(reward_resp, 'Points Earned Per Purchase')


class PasswordRecoveryFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='recover@example.com',
            password='OldPassword123!',
            first_name='Recover',
            role=User.END_USER,
            is_active=True,
            email_verified=True,
        )

    def test_login_page_has_forgot_password_link(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('password-reset-request'))

    @patch('users.views.send_password_reset_email', return_value=True)
    def test_password_reset_case_insensitive_retry_and_validation(self, mock_send):
        # Case-insensitive request
        resp = self.client.post(reverse('password-reset-request'), {'email': 'RECOVER@EXAMPLE.COM'})
        self.assertRedirects(resp, reverse('password-reset-verify'))
        mock_send.assert_called_once()

        # Generate real OTP for verification check
        otp = self.user.generate_reset_otp()

        # Wrong OTP stays on verify page rather than redirecting back to request
        bad_verify = self.client.post(reverse('password-reset-verify'), {'otp': '000000'})
        self.assertEqual(bad_verify.status_code, 200)

        # Valid OTP redirects to new password page
        good_verify = self.client.post(reverse('password-reset-verify'), {'otp': otp})
        self.assertRedirects(good_verify, reverse('password-reset-new'))

        # Mismatched passwords show form error on page
        mismatch = self.client.post(reverse('password-reset-new'), {
            'new_password': 'NewStrongPassword123!',
            'new_password_confirm': 'DifferentPassword123!',
        })
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, 'Passwords do not match.')

        # Matching passwords update password and redirect to login
        ok = self.client.post(reverse('password-reset-new'), {
            'new_password': 'NewStrongPassword123!',
            'new_password_confirm': 'NewStrongPassword123!',
        })
        self.assertRedirects(ok, reverse('login'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPassword123!'))
