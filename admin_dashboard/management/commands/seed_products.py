"""
Management command to seed demo products and categories.
Usage: python manage.py seed_products
"""
from django.core.management.base import BaseCommand
from admin_dashboard.models import Category, Product


CATEGORIES = [
    "Vitamins & Supplements",
    "Personal Care",
    "Medical Devices",
    "Herbal & Natural",
    "Baby & Mother Care",
]

PRODUCTS = [
    {
        "name": "Vitamin C 1000mg (60 Tablets)",
        "category": "Vitamins & Supplements",
        "description": "<p>High-potency Vitamin C supplement that supports immune function, collagen synthesis, and antioxidant protection. Each tablet delivers 1000mg of ascorbic acid.</p>",
        "customer_price": 4500,
        "wholesaler_price": 3200,
        "retailer_price": 3800,
        "hospital_price": 3000,
        "pharmacy_price": 3500,
        "stock": 250,
        "weight_kg": 0.20,
        "sku": "VIT-C-1000-60",
        "is_best_seller": True,
        "is_general": True,
        "discount": 10,
    },
    {
        "name": "Omega-3 Fish Oil Softgels (90 Caps)",
        "category": "Vitamins & Supplements",
        "description": "<p>Premium Omega-3 fish oil rich in EPA and DHA. Supports heart health, brain function, and reduces inflammation. Each softgel contains 1200mg fish oil.</p>",
        "customer_price": 6500,
        "wholesaler_price": 4500,
        "retailer_price": 5200,
        "hospital_price": 4200,
        "pharmacy_price": 4800,
        "stock": 180,
        "weight_kg": 0.25,
        "sku": "OMG-3-90-SOFT",
        "is_best_seller": True,
        "is_general": True,
        "discount": 5,
    },
    {
        "name": "Multivitamin & Mineral Complex (30 Tablets)",
        "category": "Vitamins & Supplements",
        "description": "<p>Complete daily multivitamin providing 23 essential vitamins and minerals. Formulated for overall wellness, energy production, and immune support.</p>",
        "customer_price": 3800,
        "wholesaler_price": 2600,
        "retailer_price": 3100,
        "hospital_price": 2400,
        "pharmacy_price": 2900,
        "stock": 320,
        "weight_kg": 0.15,
        "sku": "MULTI-30-TAB",
        "is_best_seller": False,
        "is_general": True,
        "discount": 0,
    },
    {
        "name": "Digital Blood Pressure Monitor",
        "category": "Medical Devices",
        "description": "<p>Automatic upper-arm digital blood pressure monitor with large LCD display. Clinically validated, stores up to 120 readings, irregular heartbeat detection included.</p>",
        "customer_price": 28000,
        "wholesaler_price": 19000,
        "retailer_price": 23000,
        "hospital_price": 17500,
        "pharmacy_price": 21000,
        "stock": 75,
        "weight_kg": 0.55,
        "sku": "BP-MON-AUTO-ARM",
        "is_best_seller": True,
        "is_general": True,
        "discount": 8,
    },
    {
        "name": "Pulse Oximeter (Fingertip)",
        "category": "Medical Devices",
        "description": "<p>Compact fingertip pulse oximeter that accurately measures blood oxygen saturation (SpO2) and pulse rate. OLED display, fast readings in under 10 seconds.</p>",
        "customer_price": 8500,
        "wholesaler_price": 5800,
        "retailer_price": 7000,
        "hospital_price": 5200,
        "pharmacy_price": 6500,
        "stock": 140,
        "weight_kg": 0.08,
        "sku": "OXI-FIN-001",
        "is_best_seller": True,
        "is_general": True,
        "discount": 0,
    },
    {
        "name": "Digital Thermometer (Infrared)",
        "category": "Medical Devices",
        "description": "<p>Non-contact infrared thermometer for forehead readings. Fever alert, 32 memory readings, instant 1-second results. Suitable for all ages.</p>",
        "customer_price": 9500,
        "wholesaler_price": 6500,
        "retailer_price": 7800,
        "hospital_price": 6000,
        "pharmacy_price": 7200,
        "stock": 110,
        "weight_kg": 0.12,
        "sku": "THERM-IR-FHD",
        "is_best_seller": False,
        "is_general": True,
        "discount": 5,
    },
    {
        "name": "Turmeric & Black Pepper Extract (60 Caps)",
        "category": "Herbal & Natural",
        "description": "<p>Standardised turmeric extract (95% curcuminoids) combined with BioPerine black pepper for enhanced absorption. Supports joint comfort, anti-inflammation, and antioxidant activity.</p>",
        "customer_price": 5200,
        "wholesaler_price": 3500,
        "retailer_price": 4200,
        "hospital_price": 3200,
        "pharmacy_price": 3900,
        "stock": 200,
        "weight_kg": 0.18,
        "sku": "TURM-BP-60",
        "is_best_seller": False,
        "is_general": True,
        "discount": 0,
    },
    {
        "name": "Moringa Leaf Powder (200g)",
        "category": "Herbal & Natural",
        "description": "<p>100% pure, organic moringa oleifera leaf powder. Rich in vitamins, minerals, and amino acids. Add to smoothies, juice, or food for a natural nutritional boost.</p>",
        "customer_price": 3500,
        "wholesaler_price": 2200,
        "retailer_price": 2800,
        "hospital_price": 2000,
        "pharmacy_price": 2600,
        "stock": 300,
        "weight_kg": 0.22,
        "sku": "MORING-PWD-200",
        "is_best_seller": False,
        "is_general": True,
        "discount": 0,
    },
    {
        "name": "Sensitive Skin Moisturising Lotion (400ml)",
        "category": "Personal Care",
        "description": "<p>Dermatologist-tested gentle moisturising body lotion formulated for sensitive skin. Contains shea butter, aloe vera, and vitamin E. Fragrance-free and hypoallergenic.</p>",
        "customer_price": 4200,
        "wholesaler_price": 2900,
        "retailer_price": 3400,
        "hospital_price": 2700,
        "pharmacy_price": 3200,
        "stock": 400,
        "weight_kg": 0.45,
        "sku": "SKIN-LOT-SENS-400",
        "is_best_seller": False,
        "is_general": True,
        "discount": 12,
    },
    {
        "name": "Antibacterial Hand Sanitiser Gel (500ml)",
        "category": "Personal Care",
        "description": "<p>70% alcohol-based hand sanitiser gel that kills 99.99% of germs and bacteria. Quick-drying formula with moisturisers to prevent skin dryness. No water needed.</p>",
        "customer_price": 2800,
        "wholesaler_price": 1800,
        "retailer_price": 2200,
        "hospital_price": 1500,
        "pharmacy_price": 2000,
        "stock": 600,
        "weight_kg": 0.55,
        "sku": "SANIT-GEL-500",
        "is_best_seller": True,
        "is_general": True,
        "discount": 0,
    },
    {
        "name": "Baby Gripe Water (150ml)",
        "category": "Baby & Mother Care",
        "description": "<p>Natural gripe water formulated to relieve infant colic, wind, and stomach discomfort. Alcohol-free and sugar-free. Suitable from 1 month. Gentle on baby's delicate tummy.</p>",
        "customer_price": 2500,
        "wholesaler_price": 1600,
        "retailer_price": 2000,
        "hospital_price": 1400,
        "pharmacy_price": 1800,
        "stock": 250,
        "weight_kg": 0.18,
        "sku": "BABY-GRIPE-150",
        "is_best_seller": False,
        "is_female": True,
        "is_general": False,
        "discount": 0,
    },
    {
        "name": "Prenatal Multivitamin (60 Tablets)",
        "category": "Baby & Mother Care",
        "description": "<p>Comprehensive prenatal supplement with folate, iron, calcium, DHA, and 15 essential vitamins for mother and baby. Specially formulated for pregnancy and breastfeeding.</p>",
        "customer_price": 7800,
        "wholesaler_price": 5200,
        "retailer_price": 6400,
        "hospital_price": 4800,
        "pharmacy_price": 5900,
        "stock": 160,
        "weight_kg": 0.22,
        "sku": "PREN-MULTI-60",
        "is_best_seller": True,
        "is_female": True,
        "is_general": False,
        "discount": 0,
    },
]


class Command(BaseCommand):
    help = "Seed the database with 12 demo products and 5 categories"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete all existing products and categories before seeding",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            Product.objects.all().delete()
            Category.objects.all().delete()
            self.stdout.write(self.style.WARNING("Cleared existing products and categories."))

        # Create/get categories
        cat_objects = {}
        for cat_name in CATEGORIES:
            cat, created = Category.objects.get_or_create(name=cat_name)
            cat_objects[cat_name] = cat
            if created:
                self.stdout.write(f"  Created category: {cat_name}")

        created_count = 0
        skipped_count = 0

        for data in PRODUCTS:
            sku = data["sku"]
            if Product.objects.filter(sku=sku).exists():
                self.stdout.write(f"  Skipped (already exists): {data['name']}")
                skipped_count += 1
                continue

            cat_name = data.pop("category")
            price = data["customer_price"]  # set legacy price field too
            product = Product.objects.create(
                category=cat_objects.get(cat_name),
                price=price,
                **data,
            )
            self.stdout.write(f"  Created product: {product.name}")
            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {created_count} product(s) created, {skipped_count} skipped."
            )
        )
