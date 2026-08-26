# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests.common import TransactionCase


class TestMailPersonalMailMerge(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create({
            "name": "Merge User",
            "login": "merge_user",
            "email": "merge_user@example.com",
        })
        cls.company = cls.env["res.partner"].create({
            "name": "Acme Inc",
            "is_company": True,
        })
        cls.partner_a = cls.env["res.partner"].create({
            "name": "Alice Anderson",
            "email": "alice@example.com",
            "parent_id": cls.company.id,
        })
        cls.partner_b = cls.env["res.partner"].create({
            "name": "Bob",
            "email": "bob@example.com",
        })
        cls.partner_no_email = cls.env["res.partner"].create({
            "name": "No Email",
        })
        cls.env = cls.env(user=cls.user)

    def _create_wizard(self, partners, subject="Hello {{name}}", body="<p>Hi {{first_name}}</p>"):
        return self.env["mail.personal.mail.merge"].create({
            "partner_ids": [(6, 0, partners.ids)],
            "subject": subject,
            "body": body,
        })

    def test_token_replacement_plain_text(self):
        wizard = self._create_wizard(self.partner_a)
        rendered = wizard._render_text(
            "{{name}} / {{email}} / {{company}} / {{first_name}} / {{last_name}}",
            self.partner_a,
        )
        self.assertEqual(
            rendered,
            "Alice Anderson / alice@example.com / Acme Inc / Alice / Anderson",
        )

    def test_token_replacement_html_escaping(self):
        partner = self.env["res.partner"].create({
            "name": "Eve <evil>",
            "email": "eve@example.com",
        })
        wizard = self._create_wizard(partner)
        rendered = wizard._render_html("<p>Hello {{name}}</p>", partner)
        self.assertIn("Hello Eve &lt;evil&gt;", rendered)

    def test_action_send_creates_sent_copies(self):
        inbox = self.env["mail.personal.folder"]._get_system_folder(
            self.env.user, "inbox"
        )
        before = self.env["mail.personal.mailbox"].search_count([
            ("folder_id", "=", inbox.id),
            ("user_id", "=", self.env.user.id),
            ("state", "=", "read"),
        ])
        wizard = self._create_wizard(
            self.partner_a + self.partner_b,
            subject="Hello {{name}}",
            body="<p>Hi {{first_name}} from {{company}}</p>",
        )
        action = wizard.action_send()
        after = self.env["mail.personal.mailbox"].search_count([
            ("folder_id", "=", inbox.id),
            ("user_id", "=", self.env.user.id),
            ("state", "=", "read"),
        ])
        self.assertEqual(after - before, 2)
        self.assertEqual(action["type"], "ir.actions.client")
        self.assertIn("2 email(s) sent", action["params"]["message"])

    def test_action_send_skips_partner_without_email(self):
        inbox = self.env["mail.personal.folder"]._get_system_folder(
            self.env.user, "inbox"
        )
        before = self.env["mail.personal.mailbox"].search_count([
            ("folder_id", "=", inbox.id),
            ("user_id", "=", self.env.user.id),
            ("state", "=", "read"),
        ])
        wizard = self._create_wizard(
            self.partner_a + self.partner_no_email,
            subject="Hello",
            body="<p>Hi</p>",
        )
        action = wizard.action_send()
        after = self.env["mail.personal.mailbox"].search_count([
            ("folder_id", "=", inbox.id),
            ("user_id", "=", self.env.user.id),
            ("state", "=", "read"),
        ])
        self.assertEqual(after - before, 1)
        self.assertIn("1 contact(s) skipped", action["params"]["message"])

    def test_default_get_from_active_ids(self):
        active_ids = (self.partner_a + self.partner_b).ids
        wizard = self.env["mail.personal.mail.merge"].with_context(
            active_model="res.partner",
            active_ids=active_ids,
        ).create({"subject": "Hello"})
        self.assertEqual(wizard.partner_ids, self.partner_a + self.partner_b)
