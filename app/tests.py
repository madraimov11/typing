import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Battle


class HomePageTests(TestCase):
    def test_homepage_renders_typing_practice(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'TezYoz')
        self.assertContains(response, 'Oson')
        self.assertContains(response, 'O‘rta')
        self.assertContains(response, 'O‘z matnim')
        self.assertContains(response, 'Do‘stlar bilan battle')
        self.assertContains(response, 'Profilni saqlash')
        self.assertContains(response, 'Rasm yuklash')


class BattleTests(TestCase):
    def post_json(self, url, data, token=None):
        headers = {}
        if token:
            headers['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type='application/json',
            **headers,
        )

    def test_create_join_start_and_submit_progress(self):
        create_response = self.post_json(
            '/api/battles/create/',
            {'name': 'Ali', 'avatar': '🦊'},
        )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        room_id = created['room_id']

        page_response = self.client.get(created['room_url'])
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, 'Battle’ga qo‘shiling')

        join_response = self.post_json(
            '/api/battles/{}/join/'.format(room_id),
            {'name': 'Vali', 'avatar': 'data:image/jpeg;base64,ZmFrZQ=='},
        )
        self.assertEqual(join_response.status_code, 201)

        start_response = self.post_json(
            '/api/battles/{}/start/'.format(room_id),
            {},
            token=created['token'],
        )
        self.assertEqual(start_response.status_code, 200)

        countdown_response = self.client.get(
            '/api/battles/{}/state/'.format(room_id),
            HTTP_AUTHORIZATION='Bearer ' + created['token'],
        )
        self.assertFalse(countdown_response.json()['started'])
        self.assertGreaterEqual(countdown_response.json()['countdown'], 1)

        battle = Battle.objects.get(pk=room_id)
        battle.started_at = timezone.now() - timedelta(seconds=1)
        battle.save(update_fields=['started_at'])

        state_response = self.client.get(
            '/api/battles/{}/state/'.format(room_id),
            HTTP_AUTHORIZATION='Bearer ' + created['token'],
        )
        self.assertEqual(state_response.status_code, 200)
        self.assertTrue(state_response.json()['started'])
        self.assertEqual(len(state_response.json()['participants']), 2)
        self.assertEqual(state_response.json()['participants'][0]['avatar'], '🦊')
        self.assertEqual(
            state_response.json()['participants'][1]['avatar'],
            'data:image/jpeg;base64,ZmFrZQ==',
        )

        prompt = state_response.json()['prompt']
        words = prompt.split()
        invalid_progress = self.post_json(
            '/api/battles/{}/progress/'.format(room_id),
            {'typed_text': words[0] + ' ' + words[1] + 'x '},
            token=created['token'],
        )
        self.assertEqual(invalid_progress.status_code, 400)
        self.assertIn('Keyingi so‘zga', invalid_progress.json()['error'])

        progress_response = self.post_json(
            '/api/battles/{}/progress/'.format(room_id),
            {'typed_text': prompt[:10]},
            token=created['token'],
        )
        self.assertEqual(progress_response.status_code, 200)
        self.assertEqual(progress_response.json()['progress'], round(10 * 100 / len(prompt)))
        self.assertEqual(progress_response.json()['position'], 10)

        complete_response = self.post_json(
            '/api/battles/{}/progress/'.format(room_id),
            {'typed_text': prompt},
            token=join_response.json()['token'],
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertTrue(complete_response.json()['completed'])
        self.assertGreaterEqual(complete_response.json()['duration_seconds'], 1)

        updated_state = self.client.get(
            '/api/battles/{}/state/'.format(room_id),
            HTTP_AUTHORIZATION='Bearer ' + created['token'],
        )
        self.assertEqual(updated_state.json()['participants'][0]['position'], 10)
        self.assertEqual(
            updated_state.json()['participants'][1]['duration_seconds'],
            complete_response.json()['duration_seconds'],
        )

        late_join = self.post_json(
            '/api/battles/{}/join/'.format(room_id),
            {'name': 'Late'},
        )
        self.assertEqual(late_join.status_code, 409)

    def test_battle_requires_two_participants_to_start(self):
        created = self.post_json(
            '/api/battles/create/',
            {'name': 'Ali', 'avatar': '🐼'},
        ).json()
        response = self.post_json(
            '/api/battles/{}/start/'.format(created['room_id']),
            {},
            token=created['token'],
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('kamida 2', response.json()['error'])
