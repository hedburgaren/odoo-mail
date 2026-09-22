# -*- coding: utf-8 -*-
"""Tester för återprenumeration på en avaktiverad endpoint (PS-334).

``unsubscribe`` avaktiverar raden i stället för att ta bort den. Modellen har
ett ``active``-fält, så en ofiltrerad sökning krävs för att hitta raden igen.
Utan den fälls ``subscribe`` av unikhetsvillkoret ``endpoint_unique``.
"""
from odoo.tests.common import TransactionCase


class TestPwaPushSubscribe(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Sub = self.env['pwa.push.subscription']
        self.partner = self.env.user.partner_id
        self.endpoint = 'https://fcm.example.com/fcm/send/abc123'

    def _subscribe(self):
        return self.Sub.subscribe(
            partner_id=self.partner.id,
            endpoint=self.endpoint,
            p256dh='p256dh-test',
            auth='auth-test',
            user_id=self.env.user.id,
        )

    def test_resubscribe_after_unsubscribe_reuses_row(self):
        first_id = self._subscribe()
        self.Sub.unsubscribe(self.endpoint)
        self.assertFalse(self.Sub.browse(first_id).active)

        second_id = self._subscribe()
        self.assertEqual(second_id, first_id)
        self.assertTrue(self.Sub.browse(first_id).active)
        self.assertEqual(
            self.Sub.with_context(active_test=False).search_count(
                [('endpoint', '=', self.endpoint)]), 1)

    def test_repeated_subscribe_keeps_one_row(self):
        first_id = self._subscribe()
        self.assertEqual(self._subscribe(), first_id)
        self.assertEqual(
            self.Sub.with_context(active_test=False).search_count(
                [('endpoint', '=', self.endpoint)]), 1)

    def test_unsubscribe_is_idempotent(self):
        self._subscribe()
        self.assertTrue(self.Sub.unsubscribe(self.endpoint))
        self.assertTrue(self.Sub.unsubscribe(self.endpoint))
