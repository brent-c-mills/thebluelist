# Generated by Django 5.1.3 on 2024-11-11 00:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0006_alter_editrequest_options'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='business',
            name='categories',
        ),
        migrations.DeleteModel(
            name='BusinessCategory',
        ),
    ]