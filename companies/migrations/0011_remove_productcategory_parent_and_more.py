# Generated by Django 5.1.3 on 2024-11-12 15:30

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0010_alter_productcategory_parent_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='productcategory',
            name='parent',
        ),
        migrations.RemoveField(
            model_name='servicecategory',
            name='parent',
        ),
    ]