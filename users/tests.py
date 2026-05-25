from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class ReferralSignupTests(TestCase):
	def test_signup_from_referral_link_assigns_referred_by(self):
		referrer = User.objects.create_user(
			email='referrer@example.com',
			password='strong-pass-123',
			first_name='Ref',
			role=User.END_USER,
		)

		response = self.client.get(reverse('signup'), {'ref': referrer.referral_code})
		self.assertEqual(response.status_code, 200)

		response = self.client.post(reverse('signup'), {
			'first_name': 'New',
			'last_name': 'User',
			'email': 'newuser@example.com',
			'phone': '+2348012345678',
			'role': User.END_USER,
			'password': 'new-user-pass-123',
			'password_confirm': 'new-user-pass-123',
			'referral_code_input': '',
		})

		self.assertRedirects(response, reverse('verify-otp'))
		new_user = User.objects.get(email='newuser@example.com')
		self.assertEqual(new_user.referred_by, referrer)

	def test_dashboard_contains_shareable_referral_link(self):
		user = User.objects.create_user(
			email='sharer@example.com',
			password='strong-pass-123',
			first_name='Sharer',
			role=User.END_USER,
			is_active=True,
			email_verified=True,
		)
		self.client.force_login(user)

		response = self.client.get(reverse('user-dashboard'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f'?ref={user.referral_code}')
