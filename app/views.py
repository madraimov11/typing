import json
import re
import uuid
from datetime import timedelta
from math import ceil

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Battle, BattleParticipant


def home(request):
    return render(request, 'app/home.html')


BATTLE_PROMPT = (
    "Tez yozish uchun avvalo aniqlikka e'tibor bering. Muntazam mashq, sabr va "
    "diqqat bilan har bir inson klaviaturada tezroq yozishni o'rganishi mumkin. "
    "Do'stlar bilan bellashing va natijangizni yaxshilang!"
)


def battle_page(request, room_id=None):
    if room_id is not None:
        get_object_or_404(Battle, pk=room_id)

    return render(request, 'app/battle.html', {
        'room_id': str(room_id) if room_id else '',
        'room_url': reverse('battle_room', kwargs={'room_id': room_id}) if room_id else '',
    })


def _json_body(request):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('So‘rov ma’lumotlari noto‘g‘ri.')
    if not isinstance(data, dict):
        raise ValueError('So‘rov ma’lumotlari noto‘g‘ri.')
    return data


def _avatar_from(data):
    avatar = data.get('avatar', '🐼')
    if not isinstance(avatar, str) or not avatar or len(avatar) > 150_000:
        raise ValueError('Avatar noto‘g‘ri yoki juda katta.')
    if avatar.startswith('data:') and not re.fullmatch(
        r'data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/]*={0,2}',
        avatar,
    ):
        raise ValueError('Avatar rasm formati noto‘g‘ri.')
    return avatar


def _is_wordwise_progress(prompt, typed):
    offset = 0
    for word in prompt.split():
        word_end = offset + len(word)
        if (
            len(typed) > word_end
            and typed[offset:word_end] == word
            and typed[word_end] == ' '
        ):
            offset = word_end + 1
            continue
        current_word = typed[offset:]
        return ' ' not in current_word and len(current_word) <= len(word)
    return typed == prompt


def _participant_for_request(request, battle):
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        return None
    try:
        token = uuid.UUID(authorization[7:])
    except ValueError:
        return None
    return BattleParticipant.objects.filter(token=token, battle=battle).first()


def _score(participant, battle, now=None):
    typed = participant.typed_text
    correct = sum(
        typed[index] == battle.prompt[index]
        for index in range(min(len(typed), len(battle.prompt)))
    )
    if battle.started_at:
        current_time = participant.finished_at or now or timezone.now()
        elapsed = min(
            max((current_time - battle.started_at).total_seconds(), 1),
            battle.duration_seconds,
        )
    else:
        elapsed = 1
    accuracy = round(correct * 100 / len(typed)) if typed else 100
    wpm = round((correct / 5) / (elapsed / 60))
    position = min(len(typed), len(battle.prompt))
    for index in range(position):
        if typed[index] != battle.prompt[index]:
            position = index
            break
    return {
        'name': participant.name,
        'avatar': participant.avatar,
        'progress': min(round(len(typed) * 100 / len(battle.prompt)), 100),
        'position': position,
        'wpm': wpm,
        'accuracy': accuracy,
        'correct': correct,
        'errors': max(len(typed) - correct, 0),
        'duration_seconds': round(elapsed) if battle.started_at else 0,
        'completed': typed == battle.prompt,
    }


@require_POST
def battle_create(request):
    try:
        data = _json_body(request)
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=400)

    name = data.get('name')
    if not isinstance(name, str):
        return JsonResponse({'error': 'Ismingizni kiriting.'}, status=400)
    name = name.strip()
    if not name or len(name) > 30:
        return JsonResponse({'error': 'Ism 1 dan 30 tagacha belgidan iborat bo‘lsin.'}, status=400)
    try:
        avatar = _avatar_from(data)
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=400)

    with transaction.atomic():
        battle = Battle.objects.create(prompt=BATTLE_PROMPT)
        host = BattleParticipant.objects.create(battle=battle, name=name, avatar=avatar)
        battle.host_token = host.token
        battle.save(update_fields=['host_token'])
    return JsonResponse({
        'room_id': str(battle.pk),
        'room_url': reverse('battle_room', kwargs={'room_id': battle.pk}),
        'token': str(host.token),
    }, status=201)


@require_POST
def battle_join(request, room_id):
    battle = get_object_or_404(Battle, pk=room_id)
    try:
        data = _json_body(request)
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=400)

    name = data.get('name')
    if not isinstance(name, str):
        return JsonResponse({'error': 'Ismingizni kiriting.'}, status=400)
    name = name.strip()
    if not name or len(name) > 30:
        return JsonResponse({'error': 'Ism 1 dan 30 tagacha belgidan iborat bo‘lsin.'}, status=400)
    try:
        avatar = _avatar_from(data)
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=400)
    if battle.started_at:
        return JsonResponse({'error': 'Battle boshlangan. Endi qo‘shilib bo‘lmaydi.'}, status=409)

    participant = BattleParticipant.objects.create(battle=battle, name=name, avatar=avatar)
    return JsonResponse({'token': str(participant.token)}, status=201)


@require_POST
def battle_start(request, room_id):
    battle = get_object_or_404(Battle, pk=room_id)
    participant = _participant_for_request(request, battle)
    if participant is None:
        return JsonResponse({'error': 'Battle ishtirokchisi topilmadi.'}, status=403)
    if str(battle.host_token) != str(participant.token):
        return JsonResponse({'error': 'Battleni faqat xona egasi boshlashi mumkin.'}, status=403)
    if battle.started_at:
        return JsonResponse({'error': 'Battle allaqachon boshlangan.'}, status=409)
    if battle.participants.count() < 2:
        return JsonResponse({'error': 'Boshlash uchun kamida 2 ishtirokchi kerak.'}, status=400)

    battle.started_at = timezone.now() + timedelta(seconds=3)
    battle.save(update_fields=['started_at'])
    return JsonResponse({'started_at': battle.started_at.timestamp()})


@require_POST
def battle_progress(request, room_id):
    battle = get_object_or_404(Battle, pk=room_id)
    participant = _participant_for_request(request, battle)
    if participant is None:
        return JsonResponse({'error': 'Battle ishtirokchisi topilmadi.'}, status=403)
    if not battle.started_at:
        return JsonResponse({'error': 'Battle hali boshlanmagan.'}, status=409)
    now = timezone.now()
    if now < battle.started_at:
        return JsonResponse({'error': 'Teskari sanoq tugashini kuting.'}, status=409)
    if now >= battle.started_at + timedelta(seconds=battle.duration_seconds):
        return JsonResponse({'error': 'Battle vaqti tugadi.'}, status=409)
    if participant.finished_at:
        return JsonResponse({'error': 'Natija allaqachon topshirilgan.'}, status=409)

    try:
        data = _json_body(request)
    except ValueError as error:
        return JsonResponse({'error': str(error)}, status=400)
    typed = data.get('typed_text')
    if not isinstance(typed, str):
        return JsonResponse({'error': 'Yozilgan matn noto‘g‘ri.'}, status=400)

    participant.typed_text = typed[:len(battle.prompt)]
    if not _is_wordwise_progress(battle.prompt, participant.typed_text):
        return JsonResponse({'error': 'Keyingi so‘zga o‘tishdan oldin xatoni to‘g‘rilang.'}, status=400)
    update_fields = ['typed_text']
    if participant.typed_text == battle.prompt:
        participant.finished_at = timezone.now()
        update_fields.append('finished_at')
    participant.save(update_fields=update_fields)
    return JsonResponse(_score(participant, battle))


@require_GET
def battle_state(request, room_id):
    battle = get_object_or_404(Battle, pk=room_id)
    participant = _participant_for_request(request, battle)
    if participant is None:
        return JsonResponse({'error': 'Battle ishtirokchisi topilmadi.'}, status=403)

    now = timezone.now()
    countdown = 0
    started = False
    remaining = battle.duration_seconds
    if battle.started_at:
        countdown = max(0, ceil((battle.started_at - now).total_seconds()))
        started = countdown == 0
    if started:
        remaining = max(
            0,
            battle.duration_seconds - int((now - battle.started_at).total_seconds()),
        )
    participants = [
        {
            **_score(item, battle, now),
            'is_host': str(item.token) == str(battle.host_token),
            'is_self': item.token == participant.token,
        }
        for item in battle.participants.order_by('joined_at')
    ]
    return JsonResponse({
        'room_id': str(battle.pk),
        'prompt': battle.prompt,
        'duration': battle.duration_seconds,
        'countdown': countdown,
        'started': started,
        'ended': started and remaining == 0,
        'remaining': remaining,
        'is_host': str(participant.token) == str(battle.host_token),
        'my_typed_text': participant.typed_text,
        'participants': participants,
    })
