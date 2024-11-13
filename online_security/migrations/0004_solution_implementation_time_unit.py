# Generated by Django 5.1.3 on 2024-11-12 22:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('online_security', '0003_alter_solution_implementation_difficulty_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='solution',
            name='implementation_time_unit',
            field=models.CharField(blank=True, choices=[('minutes', 'Minutes'), ('hours', 'Hours'), ('days', 'Days')], max_length=10, null=True),
        ),
    ]
