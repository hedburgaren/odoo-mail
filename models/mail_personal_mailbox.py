# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import logging
import re
from datetime import datetime, time, timedelta, timezone

import vobject

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import email_split, html_sanitize

_logger = logging.getLogger(__name__)


class MailPersonalMailbox(models.Model):
    _name = "mail.personal.mailbox"
    _description = "Personal Email Mailbox"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date DESC, id DESC"

    name = fields.Char(string="Subject", required=True, default="")
    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete="cascade",
    )
    folder_id = fields.Many2one(
        "mail.personal.folder",
        string="Folder",
        required=True,
        ondelete="restrict",
        domain="[('user_id', '=', user_id)]",
        default=lambda self: self.env["mail.personal.folder"]._get_system_folder(
            self.env.user, "inbox"
        ),
    )
    message_id = fields.Char(string="Message-ID", index=True)
    parent_id = fields.Many2one(
        "mail.personal.mailbox",
        string="Parent Message",
        index=True,
        ondelete="set null",
        help="Parent message in a conversation thread.",
    )
    child_ids = fields.One2many(
        "mail.personal.mailbox",
        "parent_id",
        string="Replies",
    )
    body = fields.Html(string="Body", sanitize=True)
    body_text = fields.Text(
        string="Plain Text Body",
        compute="_compute_body_text",
        store=True,
    )
    email_from = fields.Char(string="From")
    email_to = fields.Char(string="To")
    email_cc = fields.Char(string="CC")
    email_bcc = fields.Char(string="BCC")
    date = fields.Datetime(string="Date", default=fields.Datetime.now, required=True)
    state = fields.Selection(
        selection=[
            ("unread", "Unread"),
            ("read", "Read"),
            ("replied", "Replied"),
            ("forwarded", "Forwarded"),
            ("draft", "Draft"),
            ("archived", "Archived"),
        ],
        string="Status",
        default="unread",
        required=True,
    )
    is_starred = fields.Boolean(string="Starred", default=False, index=True)
    is_important = fields.Boolean(string="Important", default=False, index=True)
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "mail_personal_mailbox_attachment_rel",
        "mailbox_id",
        "attachment_id",
        string="Attachments",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Sender Partner",
        compute="_compute_partner_id",
        store=True,
        index=True,
    )
    crm_lead_id = fields.Many2one(
        "crm.lead",
        string="Linked Lead",
        index=True,
        ondelete="set null",
    )
    project_task_id = fields.Many2one(
        "project.task",
        string="Linked Task",
        index=True,
        ondelete="set null",
    )
    calendar_event_id = fields.Many2one(
        "calendar.event",
        string="Linked Event",
        index=True,
        ondelete="set null",
    )
    calendar_event_uid = fields.Char(
        string="Calendar Event UID",
        index=True,
        help="UID of the calendar invitation used to detect duplicates.",
    )
    calendar_rsvp_state = fields.Selection(
        selection=[
            ("needsAction", "Needs Action"),
            ("tentative", "Tentative"),
            ("accepted", "Accepted"),
            ("declined", "Declined"),
        ],
        string="Calendar RSVP",
        default="needsAction",
    )
    timer_start = fields.Datetime(string="Timer Started")
    timer_duration = fields.Float(string="Logged Time", default=0.0, help="Elapsed time in hours.")
    timer_active = fields.Boolean(
        string="Timer Active",
        compute="_compute_timer_active",
        store=True,
    )
    reply_to = fields.Char(string="Reply-To")
    mail_id = fields.Many2one(
        "mail.mail",
        string="Outgoing Mail",
        index=True,
        ondelete="set null",
        help="Outgoing mail record when this message was sent from Odoo.",
    )

    @api.depends("body")
    def _compute_body_text(self):
        for message in self:
            text = re.sub(r"<[^>]+>", " ", message.body or "")
            message.body_text = " ".join(text.split())

    @api.depends("email_from")
    def _compute_partner_id(self):
        for message in self:
            partner = self.env["res.partner"]
            if message.email_from:
                address = email_split(message.email_from)
                address = address[0] if address else message.email_from
                partner = self.env["res.partner"].search([
                    ("email", "=ilike", address),
                ], limit=1, order="is_company DESC, id")
            message.partner_id = partner

    @api.depends("timer_start")
    def _compute_timer_active(self):
        for message in self:
            message.timer_active = bool(message.timer_start)

    @api.constrains("user_id", "folder_id")
    def _check_folder_user(self):
        for message in self:
            if message.folder_id.user_id != message.user_id:
                raise ValidationError(_(
                    "The folder must belong to the same user as the message."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("body"):
                vals["body"] = html_sanitize(vals["body"])
            if not vals.get("folder_id") and vals.get("user_id"):
                vals["folder_id"] = self.env["mail.personal.folder"]._get_system_folder(
                    self.env["res.users"].browse(vals["user_id"]), "inbox"
                ).id
        return super().create(vals_list)

    @api.model
    def get_today_agenda(self):
        """Return today's calendar events for the current user."""
        partner = self.env.user.partner_id
        if not partner:
            return []
        today = fields.Date.context_today(self)
        start_dt = fields.Datetime.to_datetime(today)
        end_dt = start_dt + timedelta(days=1, seconds=-1)
        events = self.env["calendar.event"].search([
            ("start", "<=", end_dt),
            ("stop", ">=", start_dt),
            ("partner_ids", "in", partner.id),
        ], order="start, id")
        return events.read(["id", "name", "start", "stop", "location", "allday"])

    @api.model
    def get_discuss_inbox_count(self):
        """Return the number of unread Discuss inbox notifications for the current user."""
        partner = self.env.user.partner_id
        if not partner:
            return 0
        return self.env["mail.notification"].search_count([
            ("res_partner_id", "=", partner.id),
            ("is_read", "=", False),
        ])

    @api.model
    def get_discuss_inbox_messages(self, limit=50):
        """Return unread Discuss inbox notifications as lightweight message dicts."""
        partner = self.env.user.partner_id
        if not partner:
            return []
        notifications = self.env["mail.notification"].search([
            ("res_partner_id", "=", partner.id),
            ("is_read", "=", False),
        ], order="id DESC", limit=limit)
        message_ids = notifications.mapped("mail_message_id").ids
        if not message_ids:
            return []
        messages = self.env["mail.message"].search_read(
            [("id", "in", message_ids)],
            ["id", "subject", "date", "author_id", "body", "model", "res_id", "record_name"],
            order="date DESC",
        )
        result = []
        for msg in messages:
            body = msg.get("body") or ""
            preview = re.sub(r"<[^>]+>", " ", body)
            preview = " ".join(preview.split())
            author = msg.get("author_id")
            result.append({
                "id": msg["id"],
                "subject": msg.get("subject") or msg.get("record_name") or "(No subject)",
                "date": msg.get("date"),
                "author_id": author[0] if author else False,
                "author_name": author[1] if author else "",
                "preview": preview[:200],
                "body": body,
                "model": msg.get("model") or False,
                "res_id": msg.get("res_id") or False,
                "record_name": msg.get("record_name") or "",
            })
        return result

    def write(self, vals):
        if vals.get("body"):
            vals["body"] = html_sanitize(vals["body"])
        result = super().write(vals)
        if vals.get("attachment_ids") and not self.calendar_event_id:
            self.action_parse_calendar_invitation()
        return result

    def action_mark_read(self):
        return self.write({"state": "read"})

    def action_mark_unread(self):
        return self.write({"state": "unread"})

    def action_toggle_starred(self):
        return self.write({"is_starred": not self.is_starred})

    def action_toggle_important(self):
        return self.write({"is_important": not self.is_important})

    def action_move_to_folder(self, folder_id):
        folder = self.env["mail.personal.folder"].browse(folder_id)
        if any(msg.user_id != folder.user_id for msg in self):
            raise UserError(_("You can only move messages to your own folders."))
        return self.write({"folder_id": folder_id})

    def action_move_to_trash(self):
        self.unlink()

    def action_archive(self):
        self.write({"state": "archived"})

    def action_create_lead(self):
        self.ensure_one()
        if self.crm_lead_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "crm.lead",
                "res_id": self.crm_lead_id.id,
                "view_mode": "form",
                "target": "current",
            }
        lead = self.env["crm.lead"].create({
            "name": self.name,
            "partner_id": self.partner_id.id,
            "description": self.body,
            "type": "lead",
            "source_id": self.env.ref("crm.utm_source_email", raise_if_not_found=False).id,
        })
        self.crm_lead_id = lead
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "res_id": lead.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_log_to_lead(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "crm.lead",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_description": self.body,
                "default_partner_id": self.partner_id.id,
                "default_type": "lead",
            },
        }

    def action_create_task(self):
        self.ensure_one()
        if self.project_task_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "project.task",
                "res_id": self.project_task_id.id,
                "view_mode": "form",
                "target": "current",
            }
        task = self.env["project.task"].create({
            "name": self.name,
            "partner_id": self.partner_id.id,
            "description": self.body,
        })
        self.project_task_id = task
        return {
            "type": "ir.actions.act_window",
            "res_model": "project.task",
            "res_id": task.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_book_meeting(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "calendar.event",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_name": self.name,
                "default_description": self.body,
                "default_partner_ids": [(6, 0, self.partner_id.ids)],
            },
        }

    def action_view_partner(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_("No contact is linked to this email."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": self.partner_id.id,
            "view_mode": "form",
            "target": "current",
        }

    # ------------------------------------------------------------------
    # Calendar invitation (.ics) handling
    # ------------------------------------------------------------------

    def _find_ics_attachments(self):
        """Return the .ics attachments on this message."""
        self.ensure_one()
        return self.attachment_ids.filtered(
            lambda a: a.mimetype == "text/calendar" or a.name.lower().endswith(".ics")
        )

    @api.model
    def _ics_datetime_to_utc(self, value):
        """Convert a vobject date/datetime value to a UTC datetime or date."""
        if isinstance(value, datetime):
            if value.tzinfo:
                return value.astimezone(timezone.utc).replace(tzinfo=None)
            return value
        return value

    @api.model
    def _parse_ics_attachment(self, attachment):
        """Parse a single .ics attachment and return a dict of event values."""
        if not attachment.datas:
            return None
        try:
            ics_bytes = base64.b64decode(attachment.datas)
            ics_text = ics_bytes.decode("utf-8", errors="replace")
            cal = vobject.readOne(ics_text)
        except Exception as e:
            _logger.warning("Failed to parse .ics attachment %(name)s: %(error)s", {
                "name": attachment.name, "error": e,
            })
            return None

        for vevent in cal.vevent_list:
            uid = getattr(vevent, "uid", None)
            uid = uid.value if uid else None
            name = getattr(vevent, "summary", None)
            name = name.value if name else _("(No subject)")
            description = getattr(vevent, "description", None)
            description = description.value if description else ""
            location = getattr(vevent, "location", None)
            location = location.value if location else ""

            dtstart = getattr(vevent, "dtstart", None)
            dtstart = dtstart.value if dtstart else None
            dtend = getattr(vevent, "dtend", None)
            dtend = dtend.value if dtend else None

            allday = not isinstance(dtstart, datetime)
            if allday:
                start = datetime.combine(dtstart, time(8, 0))
                if dtend:
                    stop = datetime.combine(dtend, time(18, 0))
                else:
                    stop = datetime.combine(dtstart, time(18, 0))
            else:
                start = self._ics_datetime_to_utc(dtstart)
                if dtend:
                    stop = self._ics_datetime_to_utc(dtend)
                else:
                    stop = start and start.replace(hour=start.hour + 1)

            organizer = getattr(vevent, "organizer", None)
            organizer_email = ""
            if organizer:
                organizer_email = organizer.value.replace("mailto:", "").strip()

            attendee_emails = []
            if hasattr(vevent, "attendee_list"):
                for attendee in vevent.attendee_list:
                    email = attendee.value.replace("mailto:", "").strip()
                    if email:
                        attendee_emails.append(email)

            return {
                "uid": uid,
                "name": name,
                "description": description,
                "location": location,
                "start": start,
                "stop": stop,
                "allday": allday,
                "organizer_email": organizer_email,
                "attendee_emails": attendee_emails,
            }
        return None

    def action_parse_calendar_invitation(self):
        """Find the first .ics attachment and create or update a calendar.event."""
        self.ensure_one()
        ics_attachments = self._find_ics_attachments()
        if not ics_attachments:
            return False

        event_values = self._parse_ics_attachment(ics_attachments[0])
        if not event_values:
            return False

        CalendarEvent = self.env["calendar.event"]
        Attendee = self.env["calendar.attendee"]
        Partner = self.env["res.partner"]

        existing = CalendarEvent
        if event_values["uid"]:
            existing = self.env["mail.personal.mailbox"].search([
                ("calendar_event_uid", "=", event_values["uid"]),
                ("calendar_event_id", "!=", False),
                ("id", "!=", self.id),
            ], limit=1, order="date DESC").calendar_event_id

        # Build partner/attendee lists.
        attendee_emails = list(dict.fromkeys(
            [event_values["organizer_email"]] + event_values["attendee_emails"]
        ))
        partner_by_email = {}
        for email_addr in attendee_emails:
            if not email_addr:
                continue
            partner = Partner.search([("email", "=ilike", email_addr)], limit=1)
            if not partner:
                partner = Partner.create({"name": email_addr, "email": email_addr})
            partner_by_email[email_addr] = partner

        organizer_partner = partner_by_email.get(event_values["organizer_email"])
        attendee_commands = []
        partners = Partner
        owner_partner = self.user_id.partner_id
        for email_addr, partner in partner_by_email.items():
            partners |= partner
            state = "needsAction"
            if partner == owner_partner:
                state = self.calendar_rsvp_state or "needsAction"
            attendee_commands.append((0, 0, {
                "partner_id": partner.id,
                "state": state,
            }))

        values = {
            "name": event_values["name"],
            "description": event_values["description"],
            "location": event_values["location"],
            "start": event_values["start"],
            "stop": event_values["stop"],
            "allday": event_values["allday"],
            "partner_ids": [(6, 0, partners.ids)],
            "attendee_ids": attendee_commands,
        }
        if organizer_partner:
            values["partner_id"] = organizer_partner.id

        if existing:
            existing.write(values)
            event = existing
        else:
            event = CalendarEvent.create(values)

        self.write({
            "calendar_event_id": event.id,
            "calendar_event_uid": event_values["uid"],
        })
        return event.id

    def _set_attendee_state(self, state):
        """Update the mailbox owner's attendee state for the linked event."""
        self.ensure_one()
        if not self.calendar_event_id:
            return False
        owner_partner = self.user_id.partner_id
        attendee = self.calendar_event_id.attendee_ids.filtered(
            lambda a: a.partner_id == owner_partner
        )
        if not attendee:
            self.env["calendar.attendee"].create({
                "event_id": self.calendar_event_id.id,
                "partner_id": owner_partner.id,
                "state": state,
            })
        else:
            attendee.write({"state": state})
        self.write({"calendar_rsvp_state": state})
        return True

    def action_accept_event(self):
        self.ensure_one()
        self._set_attendee_state("accepted")
        return True

    def action_tentative_event(self):
        self.ensure_one()
        self._set_attendee_state("tentative")
        return True

    def action_decline_event(self):
        self.ensure_one()
        self._set_attendee_state("declined")
        return True

    def action_get_thread(self):
        """Return the conversation thread for this message as a list of dicts."""
        self.ensure_one()
        root = self
        while root.parent_id:
            root = root.parent_id
        thread = self.search([("id", "child_of", root.id)], order="date ASC, id ASC")
        return thread.read(["id", "name", "email_from", "date", "state"])

    def action_timer_start(self):
        """Start the timer on this email thread."""
        self.ensure_one()
        self.write({"timer_start": fields.Datetime.now()})
        return True

    def action_timer_stop(self):
        """Stop the timer and add elapsed time to timer_duration."""
        self.ensure_one()
        if not self.timer_start:
            return 0.0
        elapsed = (fields.Datetime.now() - self.timer_start).total_seconds() / 3600.0
        self.write({
            "timer_start": False,
            "timer_duration": self.timer_duration + elapsed,
        })
        return elapsed

    def action_log_time_to_task(self):
        """Log the accumulated timer time on the linked project.task."""
        self.ensure_one()
        task = self.project_task_id
        if not task:
            raise UserError(_("Link a task to this email before logging time."))
        if not self.timer_duration:
            raise UserError(_("No time has been recorded for this email."))
        employee = self.env.user.employee_id
        self.env["account.analytic.line"].create({
            "name": self.name,
            "date": fields.Date.context_today(self),
            "unit_amount": self.timer_duration,
            "task_id": task.id,
            "project_id": task.project_id.id,
            "employee_id": employee.id,
        })
        self.write({"timer_duration": 0.0})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _(
                    "%(hours).2f hours logged on %(task)s",
                    hours=self.timer_duration,
                    task=task.name,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_log_activity(self):
        """Open the standard activity scheduler for this email."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.activity.schedule",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": self._name,
                "active_id": self.id,
                "active_ids": [self.id],
                "default_summary": self.name,
                "default_note": self.body,
            },
        }

    def action_save_attachments_to_record(self):
        """Copy attachments to the linked partner, lead or task."""
        self.ensure_one()
        target = self.crm_lead_id or self.project_task_id or self.partner_id
        if not target:
            raise UserError(_(
                "Link a contact, lead or task before saving attachments."
            ))
        Attachment = self.env["ir.attachment"]
        copied = Attachment
        for attachment in self.attachment_ids:
            copied |= attachment.copy({
                "res_model": target._name,
                "res_id": target.id,
            })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _(
                    "%(count)d attachment(s) saved to %(record)s",
                    count=len(copied),
                    record=target.display_name,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_save_attachments_to_dms(self):
        """Copy attachments to OCA DMS under the sender's partner directory."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            raise UserError(_(
                "No contact is linked to this email."
            ))

        Storage = self.env["dms.storage"].sudo()
        Directory = self.env["dms.directory"].sudo()
        File = self.env["dms.file"].sudo()

        storage = Storage.search([("name", "=", _("Personal Email Attachments"))], limit=1)
        if not storage:
            storage = Storage.create({
                "name": _("Personal Email Attachments"),
                "save_type": "attachment",
                "model_ids": [(6, 0, [self.env["ir.model"]._get("res.partner").id])],
            })

        directory = Directory.search([
            ("storage_id", "=", storage.id),
            ("res_model", "=", "res.partner"),
            ("res_id", "=", partner.id),
            ("is_root_directory", "=", True),
        ], limit=1)
        if not directory:
            directory = Directory.create({
                "name": partner.name or partner.email or _("Unknown"),
                "is_root_directory": True,
                "storage_id": storage.id,
                "res_model": "res.partner",
                "res_id": partner.id,
            })

        created = File
        for attachment in self.attachment_ids:
            created |= File.create({
                "name": attachment.name,
                "directory_id": directory.id,
                "content": attachment.datas,
                "category_id": False,
            })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _(
                    "%(count)d attachment(s) saved to DMS under %(partner)s",
                    count=len(created),
                    partner=partner.name,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def action_save_to_knowledge(self):
        """Save the current email as an OCA Knowledge article."""
        self.ensure_one()
        if not self.is_important:
            raise UserError(_(
                "Only emails marked as important can be saved to Knowledge."
            ))

        Page = self.env["document.page"]
        category = Page.search([
            ("name", "=", _("Personal Email Articles")),
            ("type", "=", "category"),
        ], limit=1)
        if not category:
            category = Page.create({
                "name": _("Personal Email Articles"),
                "type": "category",
            })

        body = self.body or "<p></p>"
        header = _(
            "<p><em>Originally from %(sender)s, received %(date)s.</em></p>",
            sender=self.email_from or _("Unknown sender"),
            date=self.date or _("Unknown date"),
        )
        article = Page.create({
            "name": self.name or _("(No subject)"),
            "type": "content",
            "parent_id": category.id,
            "content": f"{header}{body}",
        })

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _(
                    "Email saved to Knowledge as %(article)s",
                    article=article.name,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    @api.model
    def save_draft(self, values):
        """Create or update a draft message in the user's Inbox."""
        Mailbox = self.env["mail.personal.mailbox"]
        Folder = self.env["mail.personal.folder"]
        inbox = Folder._get_system_folder(self.env.user, "inbox")
        draft_id = values.get("draft_id")
        if draft_id:
            draft = Mailbox.browse(draft_id)
            draft.write({
                "name": values.get("subject") or draft.name,
                "email_to": values.get("email_to", ""),
                "email_cc": values.get("email_cc", ""),
                "email_bcc": values.get("email_bcc", ""),
                "body": values.get("body", ""),
                "attachment_ids": values.get("attachment_ids", [(6, 0, [])]),
                "state": "draft",
            })
            return draft.id
        draft = Mailbox.create({
            "user_id": self.env.user.id,
            "folder_id": inbox.id,
            "name": values.get("subject") or _("(No subject)"),
            "email_to": values.get("email_to", ""),
            "email_cc": values.get("email_cc", ""),
            "email_bcc": values.get("email_bcc", ""),
            "body": values.get("body", ""),
            "parent_id": values.get("parent_id") or False,
            "attachment_ids": values.get("attachment_ids", [(6, 0, [])]),
            "state": "draft",
        })
        return draft.id

    def action_get_reply_body(self):
        """Return the standard quoted reply body for this message."""
        self.ensure_one()
        return self._prepare_reply_body()

    def action_reply(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_composition_mode": "reply",
                "default_model": self._name,
                "default_res_id": self.id,
                "default_partner_ids": [(6, 0, self.partner_id.ids)],
                "default_subject": _("Re: %(subject)s", subject=self.name or ""),
                "default_body": self._prepare_reply_body(),
            },
        }

    def action_reply_all(self):
        self.ensure_one()
        partners = self.partner_id
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_composition_mode": "reply",
                "default_model": self._name,
                "default_res_id": self.id,
                "default_partner_ids": [(6, 0, partners.ids)],
                "default_subject": _("Re: %(subject)s", subject=self.name or ""),
                "default_body": self._prepare_reply_body(),
            },
        }

    def action_forward(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_composition_mode": "forward",
                "default_model": self._name,
                "default_res_id": self.id,
                "default_subject": _("Fwd: %(subject)s", subject=self.name or ""),
                "default_body": self.body,
            },
        }

    def _prepare_reply_body(self):
        self.ensure_one()
        return _(
            "<p></p>"
            "<p>On %(date)s, %(sender)s wrote:</p>"
            "<blockquote>%(body)s</blockquote>",
            date=self.date,
            sender=self.email_from or _("Unknown sender"),
            body=self.body or "",
        )

    @api.model
    def _cron_auto_archive_and_delete(self):
        """Archive old emails and/or delete emails by GDPR threshold."""
        Icp = self.env["ir.config_parameter"].sudo()

        archive_enabled = Icp.get_param("unified_workspace.auto_archive_enabled") == "True"
        archive_days = int(Icp.get_param("unified_workspace.auto_archive_days") or "365")
        delete_enabled = Icp.get_param("unified_workspace.gdpr_deletion_enabled") == "True"
        delete_days = int(Icp.get_param("unified_workspace.gdpr_deletion_days") or "2555")

        now = fields.Datetime.now()

        if archive_enabled:
            archive_before = now - timedelta(days=archive_days)
            messages = self.search([
                ("state", "!=", "archived"),
                ("date", "<", archive_before),
            ])
            if messages:
                messages.write({"state": "archived"})

        if delete_enabled:
            delete_before = now - timedelta(days=delete_days)
            messages = self.search([("date", "<", delete_before)])
            if messages:
                messages.unlink()
