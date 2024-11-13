# Generated by Django 5.1.3 on 2024-11-13 16:24

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_purged',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='recovery_key_viewed',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='RecoveryKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('encrypted_key', models.CharField(max_length=344)),
                ('key_salt', models.CharField(max_length=32)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
