# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import email
import logging

from odoo import api, models, _
from odoo.tools import email_split, html_sanitize

_logger = logging.getLogger(__name__)


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    @api.model
    def message_process(self, model, message, custom_values=None,
                        save_original=False, strip_attachments=False,
                        thread_model=None):
        """Route personal emails to user inboxes before alias routing."""
        msg = email.message_from_bytes(message) if isinstance(message, bytes) else email.message_from_string(message)
        to_addresses = self._extract_to_addresses(msg)
        matched_user = self._match_personal_user(to_addresses)
        if matched_user:
            return self._create_personal_mailbox_message(matched_user, msg, message)
        return super().message_process(
            model, message,
            custom_values=custom_values,
            save_original=save_original,
            strip_attachments=strip_attachments,
            thread_model=thread_model,
        )

    @api.model
    def _extract_to_addresses(self, msg):
        """Return normalized addresses from To and CC headers."""
        addresses = []
        for header in ["to", "cc"]:
            value = msg.get(header, "")
            if value:
                addresses.extend(email_split(value))
        return [addr.lower() for addr in addresses if addr]

    @api.model
    def _match_personal_user(self, addresses):
        """Return the first active internal user whose email matches."""
        if not addresses:
            return self.env["res.users"]
        return self.env["res.users"].search([
            ("email", "in", addresses),
            ("share", "=", False),
            ("active", "=", True),
        ], limit=1, order="id")

    @api.model
    def _create_personal_mailbox_message(self, user, msg, raw_message):
        """Create a mail.personal.mailbox record from an incoming email."""
        FetchmailServer = self.env["fetchmail.server"]
        Mailbox = self.env["mail.personal.mailbox"]
        Folder = self.env["mail.personal.folder"]

        inbox = Folder._get_system_folder(user, "inbox")
        body, attachments = FetchmailServer._parse_message_body_and_attachments(msg)

        values = {
            "user_id": user.id,
            "folder_id": inbox.id,
            "name": FetchmailServer._decode_header(msg, "subject") or _("(No subject)"),
            "message_id": (msg.get("message-id") or "").strip("<> "),
            "email_from": FetchmailServer._decode_header(msg, "from"),
            "email_to": FetchmailServer._decode_header(msg, "to"),
            "email_cc": FetchmailServer._decode_header(msg, "cc"),
            "reply_to": FetchmailServer._decode_header(msg, "reply-to"),
            "date": FetchmailServer._parse_date(msg),
            "body": body,
            "state": "unread",
        }

        parent = FetchmailServer._find_parent_message(values["message_id"], msg)
        if parent:
            values["parent_id"] = parent.id

        mailbox_message = Mailbox.with_user(user).create(values)
        if attachments:
            mailbox_message.attachment_ids = [(6, 0, attachments.ids)]

        # Parse any calendar invitation attachments automatically.
        mailbox_message.action_parse_calendar_invitation()

        _logger.info(
            "Routed personal email %(subject)s to user %(user)s",
            {"subject": values["name"], "user": user.login},
        )
        return mailbox_message.id
