# Generated by Django 5.1.3 on 2024-11-15 18:24

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0020_editrequest_senior_employee_conservative_total_donations_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='datasource',
            name='edit_request',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='data_sources', to='companies.editrequest'),
        ),
        migrations.AddField(
            model_name='datasource',
            name='is_approved',
            field=models.BooleanField(default=False),
        ),
    ]
