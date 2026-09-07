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
                        thread_id=None):
        """Route personal emails to user inboxes before alias routing.

        The signature must mirror mail.thread.message_process exactly: Odoo 18
        takes thread_id, not thread_model. The earlier invented thread_model
        kwarg made every super() call raise TypeError, so all non-personal
        mail silently failed instead of reaching alias routing.
        """
        msg = email.message_from_bytes(message) if isinstance(message, bytes) else email.message_from_string(message)
        to_addresses = self._extract_to_addresses(msg)
        matched_user = self._match_personal_user(to_addresses)
        if matched_user:
            record_id = self._create_personal_mailbox_message(matched_user, msg, message)
            # Ett mail till BÅDE en personlig adress och en tråd (t.ex. svar
            # på en RFQ som gått till chrille@ + catchall@) får inte slukas av
            # inkorgen: trådens chatter och notiser uteblev (Magdalena/RFQ-00005,
            # 2026-09-07). Kör ordinarie routing också, men ENDAST vid säker
            # trådmatchning så att bounce-vägen aldrig kan nås.
            if self._has_thread_match(msg):
                try:
                    super().message_process(
                        model, message,
                        custom_values=custom_values,
                        save_original=save_original,
                        strip_attachments=strip_attachments,
                        thread_id=thread_id,
                    )
                except Exception:
                    _logger.exception(
                        "Thread routing after personal delivery failed for %s",
                        msg.get("message-id"),
                    )
            return record_id
        catchall_user = self._match_catchall_fallback_user(to_addresses)
        if catchall_user:
            # Catchall-adresserat mail får ALDRIG nå Odoos bounce-väg: vår
            # personliga sändning auto-raderar sitt Message-ID, så svar på
            # personliga mail kan inte trådmatchas. Odoo bouncade då varje
            # IMAP-omhämtning (Seen-flaggan fastnar inte hos Gmail) och en
            # kund fick 24 studsar på ett svar (2026-09-07). Routa istället
            # till direktörens inkorg; Message-ID-dedupen gör det idempotent.
            return self._create_personal_mailbox_message(catchall_user, msg, message)
        return super().message_process(
            model, message,
            custom_values=custom_values,
            save_original=save_original,
            strip_attachments=strip_attachments,
            thread_id=thread_id,
        )

    @api.model
    def _has_thread_match(self, msg):
        """True when References/In-Reply-To points at an existing message."""
        refs = []
        for header in ("in-reply-to", "references"):
            value = msg.get(header, "") or ""
            refs.extend(r.strip("<> \t") for r in value.split() if r.strip("<> \t"))
        if not refs:
            return False
        return bool(self.env["mail.message"].sudo().search_count(
            [("message_id", "in", [f"<{r}>" for r in refs] + refs)],
        ))

    @api.model
    def _match_catchall_fallback_user(self, addresses):
        """Return the fallback user for catchall-addressed mail, if any.

        Applies when a recipient is catchall@<alias-domain>. The fallback is
        the configured user (unified_workspace.catchall_fallback_user_id),
        default: the personal-mailbox admin (uid 2).
        """
        if not addresses:
            return self.env["res.users"]
        domains = self.env["mail.alias.domain"].sudo().search([])
        catchalls = {
            f"{d.catchall_alias}@{d.name}".lower()
            for d in domains if d.catchall_alias
        }
        if not catchalls.intersection(addresses):
            return self.env["res.users"]
        Param = self.env["ir.config_parameter"].sudo()
        uid = int(Param.get_param("unified_workspace.catchall_fallback_user_id") or "2")
        user = self.env["res.users"].browse(uid)
        if user.exists() and user.active and not user.share:
            return user
        return self.env["res.users"]

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

        # Dedupe on Message-ID per user. The IMAP poller refetches messages
        # whenever the \Seen flag does not stick on the server; without this
        # guard every poll cycle creates a new copy (56k rows of ~57 mails,
        # 2026-08-26 to 2026-09-02). Native message_process has the same
        # guard via mail.message; this override must supply its own.
        incoming_message_id = (msg.get("message-id") or "").strip("<> ")
        if incoming_message_id:
            existing = Mailbox.sudo().search([
                ("user_id", "=", user.id),
                ("message_id", "=", incoming_message_id),
            ], limit=1)
            if existing:
                _logger.debug(
                    "Personal mailbox dedupe: skipping already imported %s for %s",
                    incoming_message_id, user.login,
                )
                return existing.id

        body, attachments = FetchmailServer._parse_message_body_and_attachments(msg)

        values = {
            "user_id": user.id,
            "folder_id": inbox.id,
            "name": FetchmailServer._decode_header(msg, "subject") or _("(No subject)"),
            "message_id": incoming_message_id,
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
