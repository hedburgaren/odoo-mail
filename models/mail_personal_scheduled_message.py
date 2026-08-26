# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import html_sanitize


class MailPersonalScheduledMessage(models.Model):
    _name = "mail.personal.scheduled.message"
    _description = "Scheduled Personal Email"
    _order = "scheduled_date ASC, id ASC"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete="cascade",
    )
    subject = fields.Char(string="Subject", required=True)
    body = fields.Html(string="Body", sanitize=True)
    email_to = fields.Char(string="To")
    email_cc = fields.Char(string="CC")
    email_bcc = fields.Char(string="BCC")
    partner_ids = fields.Many2many(
        "res.partner",
        "mail_personal_scheduled_message_partner_rel",
        "scheduled_id",
        "partner_id",
        string="Recipients",
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "mail_personal_scheduled_message_attachment_rel",
        "scheduled_id",
        "attachment_id",
        string="Attachments",
    )
    parent_mailbox_id = fields.Many2one(
        "mail.personal.mailbox",
        string="Parent Message",
        ondelete="set null",
    )
    draft_id = fields.Many2one(
        "mail.personal.mailbox",
        string="Draft to Delete",
        ondelete="set null",
    )
    scheduled_date = fields.Datetime(string="Scheduled For", required=True, index=True)
    state = fields.Selection(
        selection=[
            ("scheduled", "Scheduled"),
            ("sent", "Sent"),
            ("error", "Error"),
        ],
        string="State",
        default="scheduled",
        required=True,
        index=True,
    )
    log_to_model = fields.Char(string="Log To Model")
    log_to_res_id = fields.Integer(string="Log To Record")

    @api.model
    def _cron_send_due_messages(self):
        """Send scheduled messages whose time has come."""
        due_messages = self.search([
            ("state", "=", "scheduled"),
            ("scheduled_date", "<=", fields.Datetime.now()),
        ])
        for message in due_messages:
            try:
                message._send()
                message.write({"state": "sent"})
            except Exception:
                message.write({"state": "error"})
        return True

    def _send(self):
        """Create a real composer and send the scheduled email."""
        self.ensure_one()
        body = self.body or ""
        values = {
            "composition_mode": "personal_email",
            "subject": self.subject,
            "body": html_sanitize(body),
            "partner_ids": [(6, 0, self.partner_ids.ids)],
            "email_cc": self.email_cc or "",
            "email_bcc": self.email_bcc or "",
            "log_to_model": self.log_to_model,
            "log_to_res_id": self.log_to_res_id,
        }
        if self.parent_mailbox_id:
            values["personal_mailbox_id"] = self.parent_mailbox_id.id
        composer = self.env["mail.compose.message"].create(values)
        if self.attachment_ids:
            composer.attachment_ids = [(6, 0, self.attachment_ids.ids)]
        composer.action_send_mail()
        if self.draft_id:
            self.draft_id.unlink()
        return True
