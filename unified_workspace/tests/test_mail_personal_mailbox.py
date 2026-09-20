# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.base.models.ir_mail_server import IrMailServer
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

ICS_INVITATION_RESCHEDULED = ICS_INVITATION.replace(
    "SUMMARY:Year End Review", "SUMMARY:Year End Review (rescheduled)"
)


def _no_send(self, *args, **kwargs):
    """Neutralisera mail.mail.send i test: auto_delete raderar annars posten
    innan assertions hinner läsa den."""
    return True


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

    def test_parse_invitation_without_dtstart_is_skipped(self):
        ics = ICS_INVITATION.replace("DTSTART:20251231T090000Z\n", "")
        attachment = self.env["ir.attachment"].create({
            "name": "broken.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(ics.encode("utf-8")),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Broken invite",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        # Får inte kasta: routningen av själva mailet får aldrig gå sönder.
        self.assertFalse(message.action_parse_calendar_invitation())
        self.assertFalse(message.calendar_event_id)

    def test_parse_invitation_late_without_dtend(self):
        ics = (
            ICS_INVITATION.replace("DTEND:20251231T100000Z\n", "")
            .replace("DTSTART:20251231T090000Z", "DTSTART:20251231T233000Z")
        )
        attachment = self.env["ir.attachment"].create({
            "name": "late.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(ics.encode("utf-8")),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Late invite",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        message.action_parse_calendar_invitation()
        self.assertTrue(message.calendar_event_id)
        self.assertEqual(
            message.calendar_event_id.start,
            fields.Datetime.to_datetime("2025-12-31 23:30:00"),
        )
        self.assertEqual(
            message.calendar_event_id.stop,
            fields.Datetime.to_datetime("2026-01-01 00:30:00"),
        )

    def _make_invitation_message(self, ics, user=None, subject="Meeting invite"):
        user = user or self.user
        attachment = self.env["ir.attachment"].create({
            "name": "invite.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(ics.encode("utf-8")),
        })
        folder = self.env["mail.personal.folder"]._get_system_folder(user, "inbox")
        return self.env["mail.personal.mailbox"].with_user(user).create({
            "user_id": user.id,
            "folder_id": folder.id,
            "name": subject,
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })

    def test_parse_future_invitation_sends_no_mail(self):
        """En mottagen inbjudan får aldrig mailas ut igen från oss.

        Odoo skickar "Invitation to ..." till alla deltagare när ett framtida
        event skapas. Arrangören skulle då få en inbjudan till sitt eget möte
        och övriga gäster en dubblett, avsänd från brevlådeägaren.
        """
        self.env["res.partner"].create([
            {"name": "External Organizer", "email": "organizer@example.com"},
            {"name": "External Guest", "email": "attendee2@example.com"},
        ])
        ics = (
            ICS_INVITATION.replace("DTSTART:20251231T090000Z", "DTSTART:20301231T090000Z")
            .replace("DTEND:20251231T100000Z", "DTEND:20301231T100000Z")
        )
        message = self._make_invitation_message(ics, subject="Future invite")

        sent = []
        with patch.object(IrMailServer, "connect", lambda *args, **kwargs: None), \
                patch.object(
                    IrMailServer, "send_email",
                    lambda self, message, *args, **kwargs: sent.append(message),
                ):
            message.action_parse_calendar_invitation()
            event = message.calendar_event_id
            self.assertTrue(event)
            self.assertGreater(event.start, fields.Datetime.now())
            # Även omplaneringen ska vara tyst.
            message.action_parse_calendar_invitation()
        self.assertFalse(sent, "Inbjudan mailades ut till deltagarna")

    def test_parse_invitation_as_regular_user_without_contact_rights(self):
        """En vanlig intern användare ska få sin kalenderhändelse.

        Tidigare skapades res.partner för varje okänd adress i filen, vilket
        gav AccessError för alla utan Contact Creation och lämnade mailet utan
        event.
        """
        regular_user = self.env["res.users"].create({
            "name": "Regular User",
            "login": "regular_mailbox_user",
            "email": "regular_mailbox_user@example.com",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        partners_before = self.env["res.partner"].search_count([])
        message = self._make_invitation_message(
            ICS_INVITATION, user=regular_user, subject="Invite for regular user",
        )
        message.action_parse_calendar_invitation()
        self.assertTrue(message.calendar_event_id)
        self.assertIn(regular_user.partner_id, message.calendar_event_id.partner_ids)
        self.assertEqual(
            self.env["res.partner"].search_count([]), partners_before,
            "Okända adresser i en .ics ska inte skapa kontakter",
        )
        self.assertIn(
            "attendee2@example.com", message.calendar_event_id.description or "",
        )

    def test_parse_invitation_runs_once_per_message(self):
        """Write-kroken parsar; ett extra anrop får inte ge ett andra event."""
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
        })
        message.attachment_ids = [(6, 0, attachment.ids)]
        event = message.calendar_event_id
        self.assertTrue(event, "Write-kroken ska ha parsat inbjudan")
        # Räkna hela eventmängden i stället för på namn: basdatabasen kan
        # innehålla ett gammalt event med samma SUMMARY, och då blir en
        # namnräkning fel oavsett modulens beteende.
        events_before = self.env["calendar.event"].search([])
        message.action_parse_calendar_invitation()
        self.assertEqual(message.calendar_event_id, event)
        self.assertEqual(self.env["calendar.event"].search([]), events_before)

    def test_write_attachments_on_multiple_messages(self):
        """write() på flera poster får inte fällas av kalenderparsningen."""
        attachment = self.env["ir.attachment"].create({
            "name": "notes.txt",
            "mimetype": "text/plain",
            "datas": base64.b64encode(b"just a note"),
        })
        messages = self.env["mail.personal.mailbox"].create([
            {
                "user_id": self.user.id,
                "folder_id": self.folder.id,
                "name": "First",
            },
            {
                "user_id": self.user.id,
                "folder_id": self.folder.id,
                "name": "Second",
            },
        ])
        messages.write({"attachment_ids": [(6, 0, attachment.ids)]})
        self.assertEqual(len(messages.mapped("attachment_ids")), 1)

    def test_parse_invitation_without_attachment_returns_false(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "No invite",
            "email_from": "organizer@example.com",
        })
        self.assertFalse(message.action_parse_calendar_invitation())
        self.assertFalse(message.calendar_event_id)

    def test_parse_invitation_ignores_non_calendar_attachment(self):
        attachment = self.env["ir.attachment"].create({
            "name": "notes.txt",
            "mimetype": "text/plain",
            "datas": base64.b64encode(b"just a note"),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Note, not invite",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        self.assertFalse(message.action_parse_calendar_invitation())
        self.assertFalse(message.calendar_event_id)

    def test_parse_malformed_ics_returns_false(self):
        attachment = self.env["ir.attachment"].create({
            "name": "broken.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(b"this is not a calendar at all"),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Malformed invite",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        # Får inte kasta: ett trasigt .ics får aldrig sluka mailet.
        self.assertFalse(message.action_parse_calendar_invitation())
        self.assertFalse(message.calendar_event_id)

    def test_parse_invitation_updates_existing_event_by_uid(self):
        first_attachment = self.env["ir.attachment"].create({
            "name": "invite.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(ICS_INVITATION.encode("utf-8")),
        })
        first = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Meeting invite",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, first_attachment.ids)],
        })
        first.action_parse_calendar_invitation()
        event = first.calendar_event_id
        self.assertTrue(event)

        updated_attachment = self.env["ir.attachment"].create({
            "name": "invite.ics",
            "mimetype": "text/calendar",
            "datas": base64.b64encode(ICS_INVITATION_RESCHEDULED.encode("utf-8")),
        })
        second = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Meeting invite updated",
            "email_from": "organizer@example.com",
            "attachment_ids": [(6, 0, updated_attachment.ids)],
        })
        second.action_parse_calendar_invitation()
        # Samma UID ska uppdatera samma event, inte skapa ett nytt.
        self.assertEqual(second.calendar_event_id, event)
        self.assertEqual(event.name, "Year End Review (rescheduled)")
        self.assertEqual(
            self.env["calendar.event"].search_count([
                ("name", "=", "Year End Review (rescheduled)"),
            ]),
            1,
        )

    def test_sent_mail_creates_no_inbox_copy(self):
        # Beslut 2026-09-07: ingen kopia i Odoo-inkorgen. Utgaende mail ligger
        # kvar i Gmails Sent; Odoo behaller bara state och loggning.
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
        result = composer._save_sent_copy()
        self.assertFalse(result)
        copy = self.env["mail.personal.mailbox"].search([
            ("user_id", "=", self.env.user.id),
            ("name", "=", "Sent subject"),
        ])
        self.assertFalse(copy)

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

    def test_personal_template_placeholders(self):
        recipient = self.env["res.partner"].create({
            "name": "Anna & Andersson",
            "company_name": "Andersson AB",
            "email": "anna@example.com",
            "phone": "+46 13 123 456",
            "city": "Linköping",
        })
        template = self.env["mail.personal.template"].create({
            "name": "Greeting",
            "subject": "Hej {{ partner.name }}",
            "body": (
                "<p>{{ partner.name }} på {{ partner.company_name }}</p>"
                "<p>{{ recipient.email }}</p>"
                "<p>{{ user.name }}</p>"
                "<p>{{ missing.field }}</p>"
            ),
            "user_id": self.user.id,
        })
        data = template.action_use_template(recipient.id)
        self.assertEqual(data["subject"], "Hej Anna & Andersson")
        self.assertIn("Anna &amp; Andersson", data["body"])
        self.assertIn("Andersson AB", data["body"])
        self.assertIn("anna@example.com", data["body"])
        self.assertIn(self.env.user.name, data["body"])
        # Unknown placeholders survive so a half-finished template stays visible.
        self.assertIn("{{ missing.field }}", data["body"])

    def test_personal_template_without_partner_keeps_partner_fields(self):
        """Utan mottagare ska partner-fälten stå kvar, inte raderas.

        Composern applicerar default-mallen när den öppnas, alltså innan
        någon mottagare finns. Renderades partner-fälten till tom sträng där
        fanns inget kvar att fylla i när mottagaren väl skrevs in.
        """
        template = self.env["mail.personal.template"].create({
            "name": "No partner",
            "subject": "Rapport {{ date }} till {{ partner.name }}",
            "body": "<p>{{ partner.name }} / {{ user.email }}</p>",
            "user_id": self.user.id,
        })
        data = template.action_use_template()
        self.assertNotIn("{{ date }}", data["subject"])
        self.assertIn("{{ partner.name }}", data["subject"])
        self.assertIn("{{ partner.name }}", data["body"])
        self.assertNotIn("{{ user.email }}", data["body"])

    def test_personal_template_render_for_partner_fills_the_rest(self):
        """Mottagaren skrivs in efteråt: bara platshållarna fylls i."""
        recipient = self.env["res.partner"].create({
            "name": "Berit Karlsson",
            "email": "berit@example.com",
        })
        data = self.env["mail.personal.template"].render_for_partner(
            subject="Hej {{ partner.name }}",
            body="<p>Hej {{ partner.name }}, egen text kvar.</p>",
            partner_id=recipient.id,
        )
        self.assertEqual(data["subject"], "Hej Berit Karlsson")
        self.assertIn("Berit Karlsson", data["body"])
        self.assertIn("egen text kvar", data["body"])

    def test_personal_template_render_for_partner_stale_id(self):
        """Ett inaktuellt partner-id får inte krascha renderingen."""
        data = self.env["mail.personal.template"].render_for_partner(
            subject="Hej {{ partner.name }}",
            body="<p>{{ user.name }}</p>",
            partner_id=99999999,
        )
        self.assertIn("{{ partner.name }}", data["subject"])
        self.assertIn(self.env.user.name, data["body"])

    def test_personal_template_placeholder_with_nbsp(self):
        """HTML-editorn kan lägga &nbsp; innanför klamrarna."""
        recipient = self.env["res.partner"].create({
            "name": "Cecilia Nord",
            "email": "cecilia@example.com",
        })
        template = self.env["mail.personal.template"].create({
            "name": "Nbsp",
            "subject": "Hej",
            "body": "<p>{{&nbsp;partner.name&nbsp;}} och {{\u00a0user.name\u00a0}}</p>",
            "user_id": self.user.id,
        })
        data = template.action_use_template(recipient.id)
        self.assertIn("Cecilia Nord", data["body"])
        self.assertIn(self.env.user.name, data["body"])
        self.assertNotIn("partner.name", data["body"])

    def test_personal_template_placeholder_fields_exposed(self):
        fields = self.env["mail.personal.template"].get_placeholder_fields()
        self.assertIn("partner.name", fields)
        self.assertIn("user.name", fields)

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

    def test_save_attachments_to_project_task(self):
        project = self.env["project.project"].search([], limit=1)
        if not project:
            project = self.env["project.project"].create({"name": "Attachments Project"})
        task = self.env["project.task"].create({
            "name": "Attachment task",
            "project_id": project.id,
        })
        attachment = self.env["ir.attachment"].create({
            "name": "spec.pdf",
            "datas": base64.b64encode(b"pdf data"),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Task mail",
            "email_from": "client@example.com",
            "project_task_id": task.id,
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        action = message.action_save_attachments_to_record()
        self.assertEqual(action["tag"], "display_notification")
        saved = self.env["ir.attachment"].search([
            ("res_model", "=", "project.task"),
            ("res_id", "=", task.id),
        ])
        self.assertTrue(saved)
        self.assertEqual(saved.name, "spec.pdf")

    def test_save_attachments_to_partner_when_no_lead(self):
        partner = self.env["res.partner"].create({
            "name": "Direct Sender",
            "email": "direct.sender@example.com",
        })
        attachment = self.env["ir.attachment"].create({
            "name": "letter.pdf",
            "datas": base64.b64encode(b"pdf data"),
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Sender mail",
            "email_from": partner.email,
            "attachment_ids": [(6, 0, attachment.ids)],
        })
        self.assertEqual(message.partner_id, partner)
        message.action_save_attachments_to_record()
        saved = self.env["ir.attachment"].search([
            ("res_model", "=", "res.partner"),
            ("res_id", "=", partner.id),
        ])
        self.assertTrue(saved)
        self.assertEqual(saved.name, "letter.pdf")

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

    def test_composer_requires_recipient(self):
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "No recipient",
            "body": "<p>Hello</p>",
        })
        with self.assertRaises(UserError):
            composer._action_send_personal_email()

    def test_send_renders_placeholders_against_recipient(self):
        """Sändningen är sista chansen: inget {{ ... }} får gå ut till kund."""
        recipient = self.env["res.partner"].create({
            "name": "David Ek",
            "email": "david@example.com",
        })
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Hej {{ partner.name }}",
            "body": "<p>Hej {{ partner.name }} i {{ partner.city }}</p>",
            "partner_ids": [(6, 0, recipient.ids)],
        })
        subject, body = composer._render_personal_placeholders(recipient)
        self.assertEqual(subject, "Hej David Ek")
        self.assertIn("David Ek", body)
        self.assertNotIn("{{", body)

    def test_send_clears_partner_placeholders_without_recipient(self):
        """Utan mottagare blir partner-fälten tomma vid sändning, inte råa."""
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Hej {{ partner.name }}",
            "body": "<p>{{ partner.name }} / {{ user.name }}</p>",
        })
        subject, body = composer._render_personal_placeholders(
            self.env["res.partner"]
        )
        self.assertEqual(subject, "Hej ")
        self.assertNotIn("{{ partner.name }}", body)
        self.assertIn(self.env.user.name, body)

    def test_ensure_signature_inserted_once_above_quote(self):
        self.user.email_signature = "<p>Kind regards, Mailbox User</p>"
        composer = self.env["mail.compose.message"].with_user(self.user).create({
            "composition_mode": "personal_email",
            "subject": "Reply",
            "body": '<p>My reply</p><div class="uw_quote"><p>quoted</p></div>',
        })
        body = composer._ensure_signature(composer.body)
        self.assertEqual(body.count("Kind regards, Mailbox User"), 1)
        self.assertLess(
            body.index("Kind regards, Mailbox User"), body.index("uw_quote")
        )
        # Andra anropet ska inte dublera signaturen.
        self.assertEqual(
            composer._ensure_signature(body).count("Kind regards, Mailbox User"), 1
        )

    def test_ensure_signature_appends_without_quote_marker(self):
        self.user.email_signature = "<p>Signature line</p>"
        composer = self.env["mail.compose.message"].with_user(self.user).create({
            "composition_mode": "personal_email",
            "subject": "New mail",
            "body": "<p>Plain body</p>",
        })
        body = composer._ensure_signature(composer.body)
        self.assertIn("Signature line", body)
        self.assertLess(body.index("Plain body"), body.index("Signature line"))

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

    def test_reply_marks_original_replied_without_copy(self):
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
        self.assertFalse(composer._save_sent_copy())
        self.assertEqual(original.state, "replied")
        copy = self.env["mail.personal.mailbox"].search([
            ("user_id", "=", self.user.id),
            ("name", "=", "Re: Original"),
        ])
        self.assertFalse(copy)

    def test_forward_marks_original_forwarded_without_copy(self):
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
            "subject": "Fwd: Original",
            "body": "<p>Forward</p>",
            "partner_ids": [(6, 0, partner.ids)],
            "personal_mailbox_id": original.id,
        })
        self.assertFalse(composer._save_sent_copy())
        self.assertEqual(original.state, "forwarded")

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

    def test_sent_mail_cc_bcc_creates_no_inbox_copy(self):
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
        before = env["mail.personal.mailbox"].search_count([
            ("user_id", "=", self.user.id),
        ])
        composer = env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Hello",
            "body": "<p>Test</p>",
            "partner_ids": [(6, 0, contact.ids)],
            "email_cc": "cc@example.com",
            "email_bcc": "bcc@example.com",
        })
        self.assertFalse(composer._save_sent_copy())
        after = env["mail.personal.mailbox"].search_count([
            ("user_id", "=", self.user.id),
        ])
        self.assertEqual(after, before)

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
        # Ingen inkorgskopia, men loggning till valt record ska ga igenom.
        self.assertFalse(composer._save_sent_copy())
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
        # Ingen inkorgskopia av det skickade schemamailet (2026-09-07).
        sent_mail = env["mail.personal.mailbox"].search([
            ("user_id", "=", self.user.id),
            ("name", "=", "Scheduled hello"),
        ])
        self.assertFalse(sent_mail)

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

    def test_send_creates_no_inbox_copy(self):
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
        before = self.env["mail.personal.mailbox"].search_count([("user_id", "=", self.env.user.id)])
        with patch.object(type(self.env["mail.mail"]), "send", _no_send):
            composer._action_send_personal_email()
        composer._save_sent_copy()
        after = self.env["mail.personal.mailbox"].search_count([("user_id", "=", self.env.user.id)])
        # Chrille 2026-09-07 (c8714d8): utgående mail ska inte hamna i inkorgen.
        self.assertEqual(before, after)
        mail = self.env["mail.mail"].sudo().search(
            [("subject", "=", "Sent subject")], order="id desc", limit=1
        )
        self.assertTrue(mail)
        self.assertIn(partner, mail.recipient_ids)
        self.assertNotIn(cc_partner, mail.recipient_ids)
        self.assertIn("cc@example.com", mail.email_cc)
        self.assertEqual(mail.attachment_ids.name, "test.txt")

    def test_forward_body_includes_header_and_quote(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Original",
            "email_from": "sender@example.com",
            "email_to": "me@example.com",
            "body": "<p>Original body</p>",
        })
        body = message.action_get_forward_body()
        self.assertIn("Forwarded message", body)
        self.assertIn("sender@example.com", body)
        self.assertIn("Original body", body)

    def test_move_email_to_crm_stage(self):
        stage = self.env["crm.stage"].create({"name": "Test Stage"})
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Deal",
            "email_from": "deal@example.com",
        })
        result = message.action_move_to_stage(stage.id)
        self.assertTrue(message.crm_lead_id)
        self.assertEqual(message.crm_lead_id.stage_id, stage)
        self.assertEqual(result["lead_id"], message.crm_lead_id.id)
        self.assertEqual(result["stage_id"], stage.id)

    def test_move_existing_lead_to_stage(self):
        stage = self.env["crm.stage"].create({"name": "Second Stage"})
        lead = self.env["crm.lead"].create({
            "name": "Existing deal",
            "type": "opportunity",
        })
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "Existing deal",
            "crm_lead_id": lead.id,
        })
        message.action_move_to_stage(stage.id)
        self.assertEqual(lead.stage_id, stage)
        self.assertEqual(message.crm_lead_id, lead)

    def test_move_to_unknown_stage_raises(self):
        message = self.env["mail.personal.mailbox"].create({
            "user_id": self.user.id,
            "folder_id": self.folder.id,
            "name": "No stage",
        })
        with self.assertRaises(UserError):
            message.action_move_to_stage(99999999)

    def test_reply_marks_original_replied(self):
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
        self.assertIsNone(composer._save_sent_copy())
        self.assertEqual(original.state, "replied")

        forward = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Fwd: Original",
            "body": "<p>Forward</p>",
            "partner_ids": [(6, 0, partner.ids)],
            "personal_mailbox_id": original.id,
        })
        forward._save_sent_copy()
        self.assertEqual(original.state, "forwarded")

    def test_outgoing_mail_splits_to_and_cc(self):
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
        with patch.object(type(self.env["mail.mail"]), "send", _no_send):
            composer._action_send_personal_email()
        mails = self.env["mail.mail"].sudo().search([("subject", "=", "Hello")])
        main = mails.filtered(lambda m: m.recipient_ids == contact)
        self.assertTrue(main)
        self.assertEqual(main.email_cc, "cc@example.com")
        self.assertFalse(
            self.env["mail.personal.mailbox"].search_count([("name", "=", "Hello")])
        )

    def test_outgoing_mail_delivers_bcc_blind(self):
        """BCC ska faktiskt levereras, och utan att röja de dolda mottagarna."""
        env = self.env.user.with_user(self.user).env
        contact = env["res.partner"].create({
            "name": "Jane Doe",
            "email": "jane.doe@example.com",
        })
        hidden = env["res.partner"].create({
            "name": "Hidden One",
            "email": "hidden@example.com",
        })
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Blind copy",
            "body": "<p>Test</p>",
            "partner_ids": [(6, 0, (contact | hidden).ids)],
            "email_cc": "cc@example.com",
            "email_bcc": "hidden@example.com, loose@example.com",
        })
        with patch.object(type(self.env["mail.mail"]), "send", _no_send):
            composer._action_send_personal_email()
        mails = self.env["mail.mail"].sudo().search([("subject", "=", "Blind copy")])
        self.assertEqual(len(mails), 3)
        main = mails.filtered(lambda m: m.recipient_ids == contact)
        self.assertEqual(len(main), 1)
        self.assertEqual(main.email_cc, "cc@example.com")
        partner_bcc = mails.filtered(lambda m: m.recipient_ids == hidden)
        self.assertEqual(len(partner_bcc), 1)
        self.assertFalse(partner_bcc.email_cc)
        loose_bcc = mails.filtered(lambda m: m.email_to == "loose@example.com")
        self.assertEqual(len(loose_bcc), 1)
        self.assertFalse(loose_bcc.recipient_ids)
        self.assertFalse(loose_bcc.email_cc)

    def test_outgoing_mail_bcc_only_is_sent(self):
        """Enbart BCC ifyllt ska skicka, inte kasta No recipient found."""
        env = self.env.user.with_user(self.user).env
        hidden = env["res.partner"].create({
            "name": "Hidden Only",
            "email": "hidden.only@example.com",
        })
        composer = self.env["mail.compose.message"].create({
            "composition_mode": "personal_email",
            "subject": "Only blind",
            "body": "<p>Test</p>",
            "partner_ids": [(6, 0, hidden.ids)],
            "email_bcc": "hidden.only@example.com",
        })
        with patch.object(type(self.env["mail.mail"]), "send", _no_send):
            composer._action_send_personal_email()
        mails = self.env["mail.mail"].sudo().search([("subject", "=", "Only blind")])
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails.recipient_ids, hidden)

    def test_signature_type_is_respected(self):
        """Väljaren i composern ska styra signaturen, inte bara mottagarna."""
        self.user.write({
            "email_signature": "<p>Internal sig</p>",
            "email_signature_external": "<p>External sig</p>",
        })
        external_contact = self.env["res.partner"].create({
            "name": "Outsider",
            "email": "outsider@example.com",
        })
        base = {
            "composition_mode": "personal_email",
            "subject": "Sig",
            "body": "<p>Test</p>",
            "partner_ids": [(6, 0, external_contact.ids)],
        }
        composer = self.env["mail.compose.message"].with_user(self.user).create(base)
        self.assertEqual(composer.signature_type, "auto")
        self.assertIn("External sig", composer._ensure_signature("<p>Test</p>"))

        forced_internal = self.env["mail.compose.message"].with_user(self.user).create(
            dict(base, signature_type="internal")
        )
        body = forced_internal._ensure_signature("<p>Test</p>")
        self.assertIn("Internal sig", body)
        self.assertNotIn("External sig", body)

        internal_partner = self.env["res.partner"].create({
            "name": "Colleague",
            "email": "colleague@example.com",
        })
        self.env["res.users"].create({
            "name": "Colleague",
            "login": "colleague_sig_user",
            "partner_id": internal_partner.id,
        })
        forced_external = self.env["mail.compose.message"].with_user(self.user).create(
            dict(base, partner_ids=[(6, 0, internal_partner.ids)], signature_type="external")
        )
        body = forced_external._ensure_signature("<p>Test</p>")
        self.assertIn("External sig", body)
        self.assertNotIn("Internal sig", body)

