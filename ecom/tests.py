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


class BuyerLimitConfigTests(TestCase):
	def test_get_min_quantity_for_role_uses_db_config(self):
		from ecom.models import BuyerLimitConfig
		from admin_dashboard.models import Product

		# Initially, should use default limits from solo instance
		config = BuyerLimitConfig.get_solo()
		self.assertEqual(config.wholesaler_limit, 10)
		self.assertEqual(config.retailer_limit, 5)
		self.assertEqual(config.end_user_limit, 1)

		product = Product.objects.create(
			name="Test Product",
			customer_price=Decimal("100.00"),
			stock=100
		)

		self.assertEqual(product.get_min_quantity_for_role(User.WHOLESALER), 10)
		self.assertEqual(product.get_min_quantity_for_role(User.RETAILER), 5)
		self.assertEqual(product.get_min_quantity_for_role(User.END_USER), 1)

		# Change config values
		config.wholesaler_limit = 25
		config.retailer_limit = 15
		config.end_user_limit = 3
		config.save()

		# Verify it updates dynamically
		self.assertEqual(product.get_min_quantity_for_role(User.WHOLESALER), 25)
		self.assertEqual(product.get_min_quantity_for_role(User.RETAILER), 15)
		self.assertEqual(product.get_min_quantity_for_role(User.END_USER), 3)


class CartMergingTests(TestCase):
	def test_merge_session_cart_to_user(self):
		from ecom.models import Cart, CartItem
		from admin_dashboard.models import Product
		from ecom.views import merge_session_cart_to_user

		user = User.objects.create_user(
			email='testbuyer@example.com',
			password='strong-pass-123',
			role=User.END_USER,
		)
		product1 = Product.objects.create(
			name="Product 1",
			customer_price=Decimal("100.00"),
			stock=50
		)
		product2 = Product.objects.create(
			name="Product 2",
			customer_price=Decimal("200.00"),
			stock=50
		)

		# Create a guest cart (session-based)
		guest_cart = Cart.objects.create(session_id="guest_session_123")
		CartItem.objects.create(cart=guest_cart, product=product1, quantity=2, price=product1.customer_price)

		# Create a user cart with product2
		user_cart = Cart.objects.create(user=user)
		CartItem.objects.create(cart=user_cart, product=product2, quantity=1, price=product2.customer_price)

		# Merge guest cart to user
		merge_session_cart_to_user("guest_session_123", user)

		# Refresh user cart and verify
		user_cart.refresh_from_db()
		self.assertEqual(user_cart.items.count(), 2)
		self.assertEqual(CartItem.objects.filter(cart=user_cart, product=product1).first().quantity, 2)
		self.assertEqual(CartItem.objects.filter(cart=user_cart, product=product2).first().quantity, 1)

		# Guest cart should be deleted
		self.assertFalse(Cart.objects.filter(session_id="guest_session_123").exists())


