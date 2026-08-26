# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, _
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)


class MailComposeMessage(models.TransientModel):
    _inherit = "mail.compose.message"

    composition_mode = fields.Selection(
        selection_add=[("personal_email", "Personal Email")],
    )
    personal_mailbox_id = fields.Many2one(
        "mail.personal.mailbox",
        string="Personal Mailbox Message",
        help="The personal mailbox message this composer is linked to.",
    )
    email_cc = fields.Char(string="CC")
    email_bcc = fields.Char(string="BCC")
    log_to_model = fields.Char(string="Log To Model")
    log_to_res_id = fields.Integer(string="Log To Record")

    def _action_send_mail(self, auto_commit=False):
        """After sending, save a copy to the sender's personal Sent folder."""
        personal = self.filtered(lambda c: c.composition_mode == "personal_email")
        for composer in personal:
            composer._action_send_personal_email()
            composer._save_sent_copy()
        regular = self - personal
        if regular:
            result = super(MailComposeMessage, regular)._action_send_mail(auto_commit=auto_commit)
            for composer in regular:
                if composer.model == "mail.personal.mailbox" and composer.res_id:
                    composer._save_sent_copy()
            return result
        return self.env["mail.mail"].sudo(), self.env["mail.message"]

    def _action_send_personal_email(self):
        """Send a personal email directly through mail.mail."""
        self.ensure_one()
        cc_emails = [e.strip().lower() for e in (self.email_cc or "").split(",") if e.strip()]
        bcc_emails = [e.strip().lower() for e in (self.email_bcc or "").split(",") if e.strip()]
        to_partners = self.partner_ids.filtered(
            lambda p: p.email and p.email.lower() not in cc_emails and p.email.lower() not in bcc_emails
        )
        if not to_partners and not cc_emails:
            raise UserError(_("No recipient found."))
        mail_values = {
            "subject": self.subject or _("(No subject)"),
            "body_html": self.body or "",
            "email_from": self.email_from or self.env.user.email_formatted,
            "recipient_ids": [(6, 0, to_partners.ids)],
            "email_cc": self.email_cc or "",
            "attachment_ids": [(6, 0, self.attachment_ids.ids)],
            "auto_delete": True,
        }
        mail = self.env["mail.mail"].sudo().create(mail_values)
        mail.send(raise_exception=True)

    def _save_sent_copy(self):
        """Create a copy of the sent message in the user's Inbox as read."""
        self.ensure_one()
        Mailbox = self.env["mail.personal.mailbox"]
        Folder = self.env["mail.personal.folder"]

        inbox = Folder._get_system_folder(self.env.user, "inbox")
        body = self.body or ""
        signature = self.env.user._get_personal_signature(self.partner_ids)
        if signature and signature not in body:
            body += "<br/>" + signature

        cc_emails = [e.strip() for e in (self.email_cc or "").split(",") if e.strip()]
        bcc_emails = [e.strip() for e in (self.email_bcc or "").split(",") if e.strip()]
        to_partners = self.partner_ids.filtered(lambda p: p.email and p.email not in cc_emails and p.email not in bcc_emails)

        values = {
            "user_id": self.env.user.id,
            "folder_id": inbox.id,
            "name": self.subject or _("(No subject)"),
            "email_from": self.email_from or self.env.user.email,
            "email_to": ", ".join(to_partners.mapped("email")),
            "email_cc": self.email_cc or "",
            "email_bcc": self.email_bcc or "",
            "body": html_sanitize(body),
            "state": "read",
        }

        if self.personal_mailbox_id:
            values["parent_id"] = self.personal_mailbox_id.id

        mailbox_message = Mailbox.create(values)

        if self.attachment_ids:
            mailbox_message.attachment_ids = [(6, 0, self.attachment_ids.ids)]

        # Link the original message if it was a reply/forward.
        if self.personal_mailbox_id:
            if self.subject and self.subject.lower().startswith("fwd:"):
                self.personal_mailbox_id.write({"state": "forwarded"})
            else:
                self.personal_mailbox_id.write({"state": "replied"})

        if self.log_to_model and self.log_to_res_id:
            self._post_to_record(mailbox_message)

        return mailbox_message

    def _post_to_record(self, mailbox_message):
        """Post a copy of the sent email to the chatter of another record."""
        self.ensure_one()
        try:
            record = self.env[self.log_to_model].browse(self.log_to_res_id)
            if record.exists() and hasattr(record, "message_post"):
                record.message_post(
                    subject=self.subject,
                    body=mailbox_message.body or "",
                    partner_ids=self.partner_ids.ids,
                    attachment_ids=self.attachment_ids.ids,
                )
        except Exception:
            _logger.exception("Failed to log personal email to %s/%s", self.log_to_model, self.log_to_res_id)

    def action_send_and_discard(self):
        """Send the message and close the composer."""
        self._action_send_mail()
        return {"type": "ir.actions.act_window_close"}
