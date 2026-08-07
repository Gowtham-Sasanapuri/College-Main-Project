from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Meeting', '0002_meeting_ai_enabled_transcriptentry'),
    ]

    operations = [
        migrations.AddField(
            model_name='meeting',
            name='Summary',
            field=models.TextField(blank=True, null=True),
        ),
    ]