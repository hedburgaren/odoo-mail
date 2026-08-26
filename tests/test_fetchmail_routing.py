# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests.common import TransactionCase


class TestFetchmailRouting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create({
            "name": "Route User",
            "login": "route_user",
            "email": "route_user@example.com",
        })

    def _build_message(self, to_email, subject="Hello"):
        return (
            "From: sender@example.com\r\n"
            f"To: {to_email}\r\n"
            f"Subject: {subject}\r\n"
            "Message-ID: <msg-1@example.com>\r\n"
            "\r\n"
            "This is a test message."
        ).encode("utf-8")

    def test_personal_email_routing(self):
        message_bytes = self._build_message(self.user.email)
        result = self.env["mail.thread"].message_process(
            False,
            message_bytes,
        )
        self.assertTrue(result)
        mailbox = self.env["mail.personal.mailbox"].browse(result)
        self.assertTrue(mailbox.exists())
        self.assertEqual(mailbox.user_id, self.user)
        self.assertEqual(mailbox.email_from, "sender@example.com")
        self.assertEqual(mailbox.name, "Hello")
        self.assertEqual(mailbox.folder_id.folder_type, "inbox")

    def test_unknown_email_falls_back(self):
        message_bytes = self._build_message("unknown@example.com")
        # Fallback should not create a personal mailbox record. The exact
        # result depends on alias configuration, so we only assert the absence
        # of a personal mailbox.
        try:
            self.env["mail.thread"].message_process(False, message_bytes)
        except Exception:
            pass
        self.assertFalse(
            self.env["mail.personal.mailbox"].search([
                ("name", "=", "Hello"),
                ("email_from", "=", "sender@example.com"),
            ])
        )
