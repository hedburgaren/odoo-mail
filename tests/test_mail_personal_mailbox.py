# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


ICS_INVITATION = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
METHOD:REQUEST
BEGIN:VEVENT
UID:test-event-1@example.com
DTSTART:20251231T090000Z
DTEND:20251231T100000Z
SUMMARY:Year End Review
DESCRIPTION:Please join the year-end review meeting.
LOCATION:Conference Room A
ORGANIZER:mailto:organizer@example.com
ATTENDEE:mailto:mailbox_user@example.com
ATTENDEE:mailto:attendee2@example.com
END:VEVENT
END:VCALENDAR
"""


class TestMailPersonalMailbox(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create({
            "name": "Mailbox User",
            "login": "mailbox_user",
            "email": "mailbox_user@example.com",
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Test Sender",
            "email": "sender@example.com",
        })
        cls.folder = cls.env["mail.personal.folder"]._get_system_folder(cls.user, "inbox")

    def test_default_folders_created(self):
        folder = self.env["mail.personal.folder"]._get_system_folder(self.user, "inbox")
        self.assertTrue(folder)
        self.assertEqual(folder.folder_type, "inbox")
        self.assertEqual(folder.user_id, self.user)

    def test_cannot_create_duplicate_system_folder(self):
        with self.assertRaises(ValidationError):
            self.env["mail.personal.folder"].create({
                "user_id": self.user.id,
                "folder_type": "inbox",
                "name": "Duplicate Inbox",
            })

    def test_message_partner_link(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Test",
            "email_from": self.partner.email,
        })
        self.assertEqual(message.partner_id, self.partner)

    def test_mark_read_unread(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Test",
        })
        self.assertEqual(message.state, "unread")
        message.action_mark_read()
        self.assertEqual(message.state, "read")
        message.action_mark_unread()
        self.assertEqual(message.state, "unread")

    def test_move_to_trash(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Test",
        })
        message_id = message.id
        message.action_move_to_trash()
        self.assertFalse(self.env["mail.personal.mailbox"].browse(message_id).exists())

    def test_create_lead(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Lead Subject",
            "email_from": "lead@example.com",
        })
        action = message.action_create_lead()
        self.assertTrue(message.crm_lead_id)
        self.assertEqual(action["res_model"], "crm.lead")
        self.assertEqual(action["res_id"], message.crm_lead_id.id)

    def test_parse_calendar_invitation(self):
        attachment = self.env["ir.attachment"].create({
            "name": "invite.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(ICS_INVITATION.encode("utf-8")),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Meeting invite",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        message.action_parse_calendar_invitation()
        self.assertTrue(message.calendar_event_id)
        event = message.calendar_event_id
        self.assertEqual(event.name, "Year End Review")
        self.assertEqual(event.location, "Conference Room A")
        self.assertTrue(event.start)
        self.assertTrue(event.stop)
        self.assertIn(self.user.partner_id, event.partner_ids)

    def test_rsvp_actions(self):
        attachment = self.env["ir.attachment"].create({
            "name": "invite.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(ICS_INVITATION.encode("utf-8")),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Meeting invite",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        message.action_parse_calendar_invitation()
        message.action_accept_event()
        self.assertEqual(message.calendar_rsvp_state, "accepted")
        attendee = message.calendar_event_id.attendee_ids.filtered(
            lambda a: a.partner_id == self.user.partner_id
        )
        self.assertEqual(attendee.state, "accepted")

        message.action_tentative_event()
        self.assertEqual(message.calendar_rsvp_state, "tentative")
        self.assertEqual(attendee.state, "tentative")

        message.action_decline_event()
        self.assertEqual(message.calendar_rsvp_state, "declined")
        self.assertEqual(attendee.state, "declined")

    def test_save_sent_copy_with_attachment(self):
        partner = self.env["res.partner"].create({
            "name": "Recipient",
            "email": "recipient@example.com",
        })
        cc_partner = self.env["res.partner"].create({
            "name": "CC Recipient",
            "email": "cc@example.com",
        })
        attachment = self.env["ir.attachment"].create({
            "name": "test.txt",
            "datas": base64.b64encode(b"hello"),
        })
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Sent subject",
            "body": "<p>Hello</p>",
            "partner_ids": [(6, 0, (partner + cc_partner).ids)],
            "email_cc": "cc@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        mailbox_message = composer._save_sent_copy()
        self.assertTrue(mailbox_message)
        self.assertEqual(mailbox_message.folder_id.folder_type, "inbox")
        self.assertEqual(mailbox_message.state, "read")
        self.assertIn("recipient@example.com", mailbox_message.email_to)
        self.assertIn("cc@example.com", mailbox_message.email_cc)
        self.assertEqual(len(mailbox_message.attachment_ids), 1)
        self.assertEqual(mailbox_message.attachment_ids.name, "test.txt")

    def test_personal_template(self):
        template = self.env["mail.personal.template"].create({
            "name": "Welcome",
            "subject": "Welcome aboard",
            "body": "<p>Hello and welcome!</p>",
            "user_id": self.user.id,
            "is_default": True,
        })
        data = template.action_use_template()
        self.assertEqual(data["subject"], "Welcome aboard")
        self.assertEqual(data["body"], "<p>Hello and welcome!</p>")
        other = self.env["mail.personal.template"].create({
            "name": "Follow-up",
            "subject": "Follow-up",
            "body": "<p>Follow-up</p>",
            "user_id": self.user.id,
            "is_default": True,
        })
        self.assertFalse(template.is_default)
        self.assertTrue(other.is_default)

    def test_thread_navigation(self):
        parent = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Parent",
            "email_from": "parent@example.com",
        })
        reply = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Reply",
            "email_from": "reply@example.com",
            "parent_id": parent.id,
        })
        thread = reply.action_get_thread()
        self.assertEqual(len(thread), 2)
        self.assertEqual(thread[0]["id"], parent.id)
        self.assertEqual(thread[1]["id"], reply.id)

    def test_log_activity_action(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Need follow-up",
            "email_from": "client@example.com",
        })
        action = message.action_log_activity()
        self.assertEqual(action["res_model"], "mail.activity.schedule")
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["context"]["active_id"], message.id)

    def test_save_attachments_to_record(self):
        attachment = self.env["ir.attachment"].create({
            "name": "contract.pdf",
            "datas": base64.b64encode(b"pdf data"),
        })
        lead = self.env["crm.lead"].create({
            "name": "New opportunity",
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Quote request",
            "email_from": "client@example.com",
            "crm_lead_id": lead.id,
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        action = message.action_save_attachments_to_record()
        self.assertEqual(action["tag"], "display_notification")
        saved = self.env["ir.attachment"].search([
            ("res_model", "=", "crm.lead"),
            ("res_id", "=", lead.id),
        ])
        self.assertTrue(saved)
        self.assertEqual(saved.name, "contract.pdf")

    def test_save_attachments_requires_record(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "No link",
            "email_from": "client@example.com",
        })
        with self.assertRaises(UserError):
            message.action_save_attachments_to_record()

    def test_save_attachments_to_dms(self):
        partner = self.env["res.partner"].create({
            "name": "DMS Client",
            "email": "dms.client@example.com",
        })
        attachment = self.env["ir.attachment"].create({
            "name": "contract.pdf",
            "datas": base64.b64encode(b"pdf data"),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Quote request",
            "email_from": partner.email,
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        action = message.action_save_attachments_to_dms()
        self.assertEqual(action["tag"], "display_notification")

        storage = self.env["dms.storage"].search([
            ("name", "=", "Personal Email Attachments"),
        ])
        self.assertTrue(storage)
        directory = self.env["dms.directory"].search([
            ("storage_id", "=", storage.id),
            ("res_model", "=", "res.partner"),
            ("res_id", "=", message.partner_id.id),
        ])
        self.assertTrue(directory)
        dms_file = self.env["dms.file"].search([
            ("directory_id", "=", directory.id),
            ("name", "=", "contract.pdf"),
        ])
        self.assertTrue(dms_file)

    def test_save_to_knowledge(self):
        partner = self.env["res.partner"].create({
            "name": "Knowledge Client",
            "email": "knowledge.client@example.com",
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Important note",
            "email_from": partner.email,
            "body": "<p>Key information</p>",
            "is_important": True,
        })
        action = message.action_save_to_knowledge()
        self.assertEqual(action["tag"], "display_notification")

        category = self.env["document.page"].search([
            ("name", "=", "Personal Email Articles"),
            ("type", "=", "category"),
        ])
        self.assertTrue(category)
        article = self.env["document.page"].search([
            ("parent_id", "=", category.id),
            ("name", "=", "Important note"),
            ("type", "=", "content"),
        ])
        self.assertTrue(article)
        self.assertIn("Key information", article.content)

    def test_save_to_knowledge_requires_important(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Normal note",
            "email_from": "normal@example.com",
            "body": "<p>Some info</p>",
            "is_important": False,
        })
        with self.assertRaises(UserError):
            message.action_save_to_knowledge()

    def test_save_draft(self):
        env = self.env.user.with_user(self.user).env
        inbox = env["mail.personal.folder"]._get_system_folder(self.user, "inbox")
        draft_id = env["mail.personal.mailbox"].save_draft({
            "subject": "Draft subject",
            "email_to": "to@example.com",
            "email_cc": "cc@example.com",
            "email_bcc": "bcc@example.com",
            "body": "<p>Draft body</p>",
        })
        draft = env["mail.personal.mailbox"].browse(draft_id)
        self.assertTrue(draft.exists())
        self.assertEqual(draft.folder_id, inbox)
        self.assertEqual(draft.state, "draft")
        self.assertEqual(draft.name, "Draft subject")
        self.assertEqual(draft.email_to, "to@example.com")
        self.assertEqual(draft.email_cc, "cc@example.com")
        self.assertEqual(draft.email_bcc, "bcc@example.com")
        self.assertEqual(draft.body, "<p>Draft body</p>")

    def test_save_draft_updates_existing(self):
        env = self.env.user.with_user(self.user).env
        inbox = env["mail.personal.folder"]._get_system_folder(self.user, "inbox")
        draft = env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": inbox.id,
            "name": "Old",
            "state": "draft",
        })
        draft_id = env["mail.personal.mailbox"].save_draft({
            "draft_id": draft.id,
            "subject": "Updated",
            "email_to": "to@example.com",
            "body": "<p>Updated</p>",
        })
        self.assertEqual(draft_id, draft.id)
        self.assertEqual(draft.name, "Updated")
        self.assertEqual(draft.state, "draft")

    def test_reply_body_includes_quote(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Original",
            "email_from": "sender@example.com",
            "body": "<p>Original body</p>",
        })
        body = message.action_get_reply_body()
        self.assertIn("sender@example.com wrote", body)
        self.assertIn("Original body", body)

    def test_sent_copy_links_parent_on_reply(self):
        partner = self.env["res.partner"].create({
            "name": "Recipient",
            "email": "recipient@example.com",
        })
        original = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Original",
            "email_from": "recipient@example.com",
        })
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Re: Original",
            "body": "<p>Reply</p>",
            "partner_ids": [(6, 0, partner.ids)],
            "personal_mailbox_id": original.id,
        })
        sent = composer._save_sent_copy()
        self.assertEqual(sent.parent_id, original)
        self.assertEqual(original.state, "replied")

    def test_timer_start_stop(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Timed task",
        })
        message.action_timer_start()
        self.assertTrue(message.timer_active)
        self.assertTrue(message.timer_start)
        # Simulate elapsed time by setting start in the past.
        message.timer_start = fields.Datetime.now() - timedelta(hours=1, minutes=30)
        elapsed = message.action_timer_stop()
        self.assertAlmostEqual(elapsed, 1.5, places=2)
        self.assertAlmostEqual(message.timer_duration, 1.5, places=2)
        self.assertFalse(message.timer_start)

    def test_log_time_to_task(self):
        env = self.env.user.with_user(self.user).env
        project = env["project.project"].create({"name": "Test Project"})
        task = env["project.task"].create({
            "name": "Test Task",
            "project_id": project.id,
        })
        employee = env["hr.employee"].create({
            "name": "Test Employee",
            "user_id": self.user.id,
        })
        message = env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": env["mail.personal.folder"]._get_system_folder(self.user, "inbox").id,
            "name": "Timed email",
            "project_task_id": task.id,
            "timer_duration": 2.5,
        })
        action = message.action_log_time_to_task()
        self.assertEqual(action["tag"], "display_notification")
        line = env["account.analytic.line"].search([
            ("task_id", "=", task.id),
            ("employee_id", "=", employee.id),
        ])
        self.assertTrue(line)
        self.assertEqual(line.unit_amount, 2.5)
        self.assertEqual(message.timer_duration, 0.0)

    def test_log_time_requires_task(self):
        env = self.env.user.with_user(self.user).env
        message = env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": env["mail.personal.folder"]._get_system_folder(self.user, "inbox").id,
            "name": "No task",
            "timer_duration": 1.0,
        })
        with self.assertRaises(UserError):
            message.action_log_time_to_task()

    def test_get_today_agenda(self):
        env = self.env.user.with_user(self.user).env
        partner = self.user.partner_id
        today = fields.Date.context_today(partner)
        start = fields.Datetime.to_datetime(today) + timedelta(hours=10)
        stop = start + timedelta(hours=1)
        event = env["calendar.event"].create({
            "name": "Team standup",
            "start": start,
            "stop": stop,
            "partner_ids": [(6, 0, partner.ids)],
        })
        agenda = env["mail.personal.mailbox"].get_today_agenda()
        self.assertTrue(agenda)
        self.assertEqual(agenda[0]["id"], event.id)
        self.assertEqual(agenda[0]["name"], "Team standup")

    def test_save_sent_copy_with_cc_bcc_and_company(self):
        env = self.env.user.with_user(self.user).env
        company = env["res.partner"].create({
            "name": "Acme Corp",
            "is_company": True,
        })
        contact = env["res.partner"].create({
            "name": "Jane Doe",
            "email": "jane.doe@example.com",
            "parent_id": company.id,
        })
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Hello",
            "body": "<p>Test</p>",
            "partner_ids": [(6, 0, contact.ids)],
            "email_cc": "cc@example.com",
            "email_bcc": "bcc@example.com",
        })
        mailbox_message = composer._save_sent_copy()
        self.assertEqual(mailbox_message.email_to, "jane.doe@example.com")
        self.assertEqual(mailbox_message.email_cc, "cc@example.com")
        self.assertEqual(mailbox_message.email_bcc, "bcc@example.com")
        self.assertEqual(mailbox_message.folder_id.folder_type, "inbox")
        self.assertEqual(mailbox_message.state, "read")

    def test_toggle_important(self):
        env = self.env.user.with_user(self.user).env
        message = env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": env["mail.personal.folder"]._get_system_folder(self.user, "inbox").id,
            "name": "Important soon",
        })
        self.assertFalse(message.is_important)
        message.action_toggle_important()
        self.assertTrue(message.is_important)
        message.action_toggle_important()
        self.assertFalse(message.is_important)

    def test_send_and_log_to_record(self):
        env = self.env.user.with_user(self.user).env
        lead = env["crm.lead"].create({"name": "Log target"})
        partner = env["res.partner"].create({
            "name": "Receiver",
            "email": "receiver@example.com",
        })
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Hello",
            "body": "<p>Test</p>",
            "partner_ids": [(6, 0, partner.ids)],
            "log_to_model": "crm.lead",
            "log_to_res_id": lead.id,
        })
        mailbox_message = composer._save_sent_copy()
        self.assertTrue(mailbox_message)
        chatter_message = env["mail.message"].search([
            ("model", "=", "crm.lead"),
            ("res_id", "=", lead.id),
        ], limit=1)
        self.assertTrue(chatter_message)
        self.assertIn("Test", chatter_message.body)

    def test_scheduled_message_cron(self):
        env = self.env.user.with_user(self.user).env
        partner = env["res.partner"].create({
            "name": "Scheduled Receiver",
            "email": "scheduled@example.com",
        })
        scheduled = env["mail.personal.scheduled.message"].create({
            "user_id": self.user.id,
            "subject": "Scheduled hello",
            "body": "<p>Scheduled</p>",
            "partner_ids": [(6, 0, partner.ids)],
            "scheduled_date": fields.Datetime.now(),
        })
        self.assertEqual(scheduled.state, "scheduled")
        env["mail.personal.scheduled.message"]._cron_send_due_messages()
        scheduled.invalidate_recordset()
        self.assertEqual(scheduled.state, "sent")
        sent_mail = env["mail.personal.mailbox"].search([
            ("user_id", "=", self.user.id),
            ("name", "=", "Scheduled hello"),
        ], limit=1)
        self.assertTrue(sent_mail)
        self.assertEqual(sent_mail.folder_id.folder_type, "inbox")
        self.assertEqual(sent_mail.state, "read")

    def test_auto_archive_old_emails(self):
        Icp = self.env["ir.config_parameter"].sudo()
        Icp.set_param("unified_workspace.auto_archive_enabled", "True")
        Icp.set_param("unified_workspace.auto_archive_days", "1")
        old_message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Old inbox message",
            "email_from": "old@example.com",
            "date": fields.Datetime.now() - timedelta(days=2),
        })
        self.assertEqual(old_message.state, "unread")
        self.env["mail.personal.mailbox"]._cron_auto_archive_and_delete()
        old_message.invalidate_recordset()
        self.assertEqual(old_message.state, "archived")

    def test_gdpr_deletion_old_emails(self):
        Icp = self.env["ir.config_parameter"].sudo()
        Icp.set_param("unified_workspace.gdpr_deletion_enabled", "True")
        Icp.set_param("unified_workspace.gdpr_deletion_days", "1")
        old_message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Very old message",
            "email_from": "old@example.com",
            "date": fields.Datetime.now() - timedelta(days=2),
        })
        message_id = old_message.id
        self.env["mail.personal.mailbox"]._cron_auto_archive_and_delete()
        self.assertFalse(self.env["mail.personal.mailbox"].browse(message_id).exists())

    def test_auto_archive_disabled_does_nothing(self):
        Icp = self.env["ir.config_parameter"].sudo()
        Icp.set_param("unified_workspace.auto_archive_enabled", "False")
        Icp.set_param("unified_workspace.gdpr_deletion_enabled", "False")
        old_message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Old but safe message",
            "email_from": "safe@example.com",
            "date": fields.Datetime.now() - timedelta(days=365),
        })
        self.env["mail.personal.mailbox"]._cron_auto_archive_and_delete()
        old_message.invalidate_recordset()
        self.assertTrue(old_message.exists())
        self.assertEqual(old_message.folder_id, self.folder)

    def test_sales_insights(self):
        partner = self.env["res.partner"].create({
            "name": "Sales Contact",
            "email": "sales@example.com",
        })
        lead = self.env["crm.lead"].create({
            "name": "Big Deal",
            "partner_id": partner.id,
            "type": "opportunity",
            "expected_revenue": 5000.0,
        })
        self.env["mail.activity"].create({
            "res_model_id": self.env["ir.model"]._get("crm.lead").id,
            "res_id": lead.id,
            "activity_type_id": self.env.ref("mail.mail_activity_data_call").id,
            "summary": "Follow-up call",
            "date_deadline": fields.Date.today(),
            "user_id": self.env.user.id,
        })
        insights = partner.get_sales_insights()
        self.assertEqual(insights["open_opportunities_count"], 1)
        self.assertEqual(insights["total_expected_revenue"], 5000.0)
        self.assertEqual(insights["next_activity"], "Follow-up call")
