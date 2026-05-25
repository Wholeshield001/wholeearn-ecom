# Generated manually — aligns Order.status choices with Speedaf tracking action codes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ecom', '0009_payment_provider_config'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending',              'Pending'),
                    ('ordered',              'Ordered'),
                    ('inbound',              'Inbound'),
                    ('packaged',             'Packaged'),
                    ('outbound',             'Outbound'),
                    ('picked',               'Picked'),
                    ('departed',             'Departed'),
                    ('arrived',              'Arrived'),
                    ('customs_declaration',  'Customs Declaration'),
                    ('flight_departed',      'Flight Departed'),
                    ('flight_landed',        'Flight Landed'),
                    ('in_clearance',         'In Clearance'),
                    ('clearance_exception',  'Clearance Exception'),
                    ('clearance_completed',  'Clearance Completed'),
                    ('in_delivery',          'In Delivery'),
                    ('delivered',            'Delivered'),
                    ('returning',            'Returning'),
                    ('returned',             'Returned'),
                    ('cancelled',            'Cancelled'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]
