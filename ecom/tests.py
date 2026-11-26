from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ecom.models import (
    Order,
    RewardPointConfig,
    RewardPointLedger,
    HeroSectionConfig,
    SocialMediaLink,
    NewsletterSubscriber,
    ContactMessage,
)
from ecom.templatetags.ecom_tags import format_price
from django.urls import reverse


User = get_user_model()


class PartnerPointsAllocationTests(TestCase):
	def test_partner_earns_category_points_on_every_completed_purchase(self):
		config = RewardPointConfig.get_solo()
		config.wholesaler_points = 10
		config.retailer_points = 5
		config.points_per_purchase = 2
		config.save()

		wholesaler = User.objects.create_user(
			email='wholesaler@example.com',
			password='strong-pass-123',
			role=User.WHOLESALER,
		)

		Order.objects.create(
			user=wholesaler,
			total_amount=Decimal('50000.00'),
			payment_status='completed',
			status='pending',
			shipping_fee=Decimal('0.00'),
			shipping_address='12 Example Street',
			shipping_city='Lagos',
			shipping_state='Lagos',
			shipping_phone='+2348012345678',
		)
		Order.objects.create(
			user=wholesaler,
			total_amount=Decimal('25000.00'),
			payment_status='completed',
			status='pending',
			shipping_fee=Decimal('0.00'),
			shipping_address='12 Example Street',
			shipping_city='Lagos',
			shipping_state='Lagos',
			shipping_phone='+2348012345678',
		)

		wholesaler.refresh_from_db()
		self.assertEqual(wholesaler.reward_points, 20)
		self.assertEqual(
			RewardPointLedger.objects.filter(user=wholesaler, reason=RewardPointLedger.PURCHASE).count(),
			2,
		)


class StorefrontReviewFeaturesTests(TestCase):
	def test_format_price_whole_number_commas(self):
		self.assertEqual(format_price(Decimal('25000.00')), '25,000')
		self.assertEqual(format_price(1250000), '1,250,000')
		self.assertEqual(format_price(None), '0')

	def test_about_contact_newsletter_and_footer_links(self):
		SocialMediaLink.objects.create(name='Instagram', url='https://instagram.com/wholeshield', is_active=True)
		hero = HeroSectionConfig.get_solo()
		hero.headline_prefix = 'Discover the'
		hero.save()

		home_resp = self.client.get(reverse('home'))
		self.assertEqual(home_resp.status_code, 200)
		self.assertContains(home_resp, 'Discover the')
		self.assertContains(home_resp, 'https://instagram.com/wholeshield')
		self.assertContains(home_resp, 'By submitting your email, you consent to receive emails and updates from Wholeshield.')
		self.assertContains(home_resp, 'images/Shield.png')

		about_resp = self.client.get(reverse('about-us'))
		self.assertEqual(about_resp.status_code, 200)

		contact_resp = self.client.post(reverse('contact-us'), {
			'name': 'Jane Doe',
			'email': 'jane@example.com',
			'phone': '08012345678',
			'subject': 'Product inquiry',
			'message': 'Tell me more about Optishield.',
		})
		self.assertRedirects(contact_resp, reverse('contact-us'))
		self.assertEqual(ContactMessage.objects.count(), 1)

		sub_resp = self.client.post(
			reverse('newsletter-subscribe'),
			{'email': 'crew@example.com'},
			HTTP_HX_REQUEST='true',
		)
		self.assertEqual(sub_resp.status_code, 200)
		self.assertTrue(NewsletterSubscriber.objects.filter(email='crew@example.com').exists())


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


class AdminProductEditTests(TestCase):
	def test_edit_product_price_saves_successfully(self):
		admin_user = User.objects.create_superuser(
			email='admin_test@example.com',
			password='strong-pass-123',
		)
		from admin_dashboard.models import Product
		product = Product.objects.create(
			name="Product to Edit",
			customer_price=Decimal("100.00"),
			stock=50
		)
		self.client.login(email='admin_test@example.com', password='strong-pass-123')
		
		# Submit POST to edit product details
		response = self.client.post(
			f'/admin-dashboard/products/{product.id}/edit/',
			data={
				'name': 'Updated Product Name',
				'customer_price': '150.00',
				'stock': '40',
				'weight_kg': '1.50',
			}
		)
		self.assertEqual(response.status_code, 302)
		
		# Verify changes in DB
		product.refresh_from_db()
		self.assertEqual(product.name, 'Updated Product Name')
		self.assertEqual(product.customer_price, Decimal('150.00'))
		self.assertEqual(product.price, Decimal('150.00'))  # Verify legacy price synced
		self.assertEqual(product.stock, 40)


class ProductPaginationTests(TestCase):
	def test_htmx_pagination_returns_single_container_and_updates_page(self):
		from admin_dashboard.models import Product
		# Create 14 products to produce 2 pages (12 per page)
		for i in range(14):
			Product.objects.create(
				name=f"Product {i+1}",
				customer_price=Decimal("100.00"),
				stock=10
			)

		# Initial load (standard GET)
		response = self.client.get('/products/')
		self.assertEqual(response.status_code, 200)
		content = response.content.decode('utf-8')
		self.assertEqual(content.count('id="productsGrid"'), 1)
		self.assertEqual(content.count('id="paginationContainer"'), 1)
		self.assertIn('Page 1 of 2', content)

		# HTMX page 2 request
		htmx_response = self.client.get('/products/?page=2', HTTP_HX_REQUEST='true')
		self.assertEqual(htmx_response.status_code, 200)
		htmx_content = htmx_response.content.decode('utf-8')
		# The partial response itself must contain exactly 1 #productsGrid and 1 #paginationContainer
		self.assertEqual(htmx_content.count('id="productsGrid"'), 1)
		self.assertEqual(htmx_content.count('id="paginationContainer"'), 1)
		self.assertIn('Page 2 of 2', htmx_content)



