from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ecom.models import Order, RewardPointLedger


User = get_user_model()


class ReferralRewardTests(TestCase):
	def test_referrer_gets_point_on_referred_users_first_completed_purchase(self):
		referrer = User.objects.create_user(
			email='referrer@example.com',
			password='strong-pass-123',
			role=User.END_USER,
		)
		buyer = User.objects.create_user(
			email='buyer@example.com',
			password='strong-pass-123',
			role=User.END_USER,
			referred_by=referrer,
		)

		order = Order.objects.create(
			user=buyer,
			total_amount=Decimal('15000.00'),
			payment_status='completed',
			status='pending',
			shipping_fee=Decimal('0.00'),
			referral_code_used=referrer.referral_code,
			referrer=referrer,
			shipping_address='12 Example Street',
			shipping_city='Lagos',
			shipping_state='Lagos',
			shipping_phone='+2348012345678',
		)

		referrer.refresh_from_db()
		buyer.refresh_from_db()
		order.refresh_from_db()

		self.assertEqual(referrer.reward_points, 1)
		self.assertEqual(buyer.reward_points, 1)
		self.assertTrue(order.referral_points_awarded)
		self.assertEqual(
			RewardPointLedger.objects.filter(user=referrer, reason=RewardPointLedger.REFERRAL).count(),
			1,
		)
