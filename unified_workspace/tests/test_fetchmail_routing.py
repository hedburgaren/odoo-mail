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


class TestCatchallThreadRouting(TransactionCase):
    """Replies to catchall reach their thread as well as the inbox copy."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.alias_domain = cls.env["mail.alias.domain"].create({
            "name": "catchall-test.example.com",
            "catchall_alias": "catchall",
            "bounce_alias": "bounce",
        })
        cls.catchall = "catchall@catchall-test.example.com"
        cls.fallback_user = cls.env["res.users"].create({
            "name": "Catchall Director",
            "login": "catchall_director",
            "email": "director@example.com",
        })
        cls.env["ir.config_parameter"].sudo().set_param(
            "unified_workspace.catchall_fallback_user_id", cls.fallback_user.id)
        cls.record = cls.env["res.partner"].create({"name": "Thread Owner"})
        cls.parent = cls.record.message_post(body="Our quotation")

    def _reply(self, message_id, in_reply_to=None, subject="Re: Quotation"):
        headers = (
            "From: customer@example.org\r\n"
            f"To: {self.catchall}\r\n"
            f"Subject: {subject}\r\n"
            f"Message-ID: <{message_id}>\r\n"
        )
        if in_reply_to:
            headers += f"In-Reply-To: {in_reply_to}\r\n"
        return (headers + "\r\nWe would like to add one item.").encode("utf-8")

    def test_catchall_reply_with_thread_match_reaches_chatter(self):
        raw = self._reply("reply-1@example.org", self.parent.message_id)
        result = self.env["mail.thread"].message_process(False, raw)
        mailbox = self.env["mail.personal.mailbox"].browse(result)
        self.assertEqual(mailbox.user_id, self.fallback_user)
        on_thread = self.env["mail.message"].search([
            ("message_id", "=", "<reply-1@example.org>"),
        ])
        self.assertEqual(on_thread.model, "res.partner")
        self.assertEqual(on_thread.res_id, self.record.id)

    def test_catchall_reply_is_idempotent_on_refetch(self):
        raw = self._reply("reply-2@example.org", self.parent.message_id)
        self.env["mail.thread"].message_process(False, raw)
        self.env["mail.thread"].message_process(False, raw)
        self.assertEqual(self.env["mail.message"].search_count([
            ("message_id", "=", "<reply-2@example.org>"),
        ]), 1)
        self.assertEqual(self.env["mail.personal.mailbox"].search_count([
            ("message_id", "=", "reply-2@example.org"),
        ]), 1)

    def test_catchall_without_thread_match_stays_in_inbox(self):
        raw = self._reply("reply-3@example.org", "<unknown@nowhere.example>",
                          subject="Something else")
        result = self.env["mail.thread"].message_process(False, raw)
        self.assertTrue(self.env["mail.personal.mailbox"].browse(result).exists())
        self.assertFalse(self.env["mail.message"].search([
            ("message_id", "=", "<reply-3@example.org>"),
        ]))
