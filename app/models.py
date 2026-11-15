import uuid

from django.db import models


class Battle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prompt = models.TextField()
    duration_seconds = models.PositiveSmallIntegerField(default=60)
    host_token = models.UUIDField(null=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)


class BattleParticipant(models.Model):
    token = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    battle = models.ForeignKey(Battle, on_delete=models.CASCADE, related_name='participants')
    name = models.CharField(max_length=30)
    avatar = models.TextField(default='🐼')
    typed_text = models.TextField(blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
