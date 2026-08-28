# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import base64
import email
import logging

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.tools import email_split, html_sanitize

_logger = logging.getLogger(__name__)


class FetchmailServer(models.Model):
    _inherit = "fetchmail.server"

    is_personal_mailbox_server = fields.Boolean(
        string="Personal Mailbox Server",
        default=False,
        help=(
            "When enabled, emails whose To address matches an active user's "
            "email are routed to that user's personal inbox instead of going "
            "through alias routing."
        ),
    )

    @api.model
    def _extract_addresses(self, msg, headers):
        """Return a normalized list of email addresses from the given headers."""
        addresses = []
        for header in headers:
            value = msg.get(header, "")
            if value:
                addresses.extend(email_split(value))
        return [addr.lower() for addr in addresses if addr]

    @api.model
    def _match_user_by_email(self, addresses):
        """Return the first active internal user whose email matches one of the addresses."""
        if not addresses:
            return self.env["res.users"]
        return self.env["res.users"].search([
            ("email", "in", addresses),
            ("share", "=", False),
            ("active", "=", True),
        ], limit=1, order="id")

    @api.model
    def _find_parent_message(self, message_id, msg):
        """Find a parent message based on In-Reply-To or References headers."""
        if not message_id:
            return self.env["mail.personal.mailbox"]

        references = []
        in_reply_to = msg.get("in-reply-to", "").strip("<> ")
        if in_reply_to:
            references.append(in_reply_to)
        refs = msg.get("references", "")
        if refs:
            references.extend([r.strip("<> ") for r in refs.split()])

        if references:
            return self.env["mail.personal.mailbox"].search([
                ("message_id", "in", references),
            ], limit=1, order="date DESC")
        return self.env["mail.personal.mailbox"]

    @api.model
    def _decode_header(self, msg, header):
        """Decode a message header into a readable string."""
        value = msg.get(header, "")
        if not value:
            return ""
        decoded_parts = email.header.decode_header(value)
        result = []
        for part, charset in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(charset or "utf-8", errors="replace"))
                except LookupError:
                    result.append(part.decode("utf-8", errors="replace"))
            else:
                result.append(part)
        return " ".join(result).strip()

    @api.model
    def _parse_date(self, msg):
        """Parse the Date header into a UTC datetime."""
        from odoo.fields import Datetime
        date_header = msg.get("date")
        if date_header:
            try:
                parsed = email.utils.parsedate_to_datetime(date_header)
                if parsed:
                    return Datetime.to_datetime(parsed)
            except Exception:
                pass
        return fields.Datetime.now()

    @api.model
    def _parse_message_body_and_attachments(self, msg):
        """Extract HTML/plain body and attachments from a message."""
        body_html = ""
        body_text = ""
        attachments = self.env["ir.attachment"]

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                disposition = part.get("Content-Disposition", "")
                if content_type == "text/html" and "attachment" not in disposition:
                    body_html = self._decode_payload(part)
                elif content_type == "text/plain" and "attachment" not in disposition:
                    body_text = self._decode_payload(part)
                elif "attachment" in disposition or part.get_filename():
                    attachments |= self._create_attachment(part)
        else:
            content_type = msg.get_content_type()
            if content_type == "text/html":
                body_html = self._decode_payload(msg)
            else:
                body_text = self._decode_payload(msg)

        if body_html:
            body = html_sanitize(body_html)
        elif body_text:
            body = Markup("<pre>%s</pre>") % Markup.escape(body_text)
        else:
            body = ""

        return body, attachments

    @api.model
    def _decode_payload(self, part):
        """Decode the payload of a message part."""
        charset = part.get_content_charset() or "utf-8"
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        try:
            return payload.decode(charset, errors="replace")
        except LookupError:
            return payload.decode("utf-8", errors="replace")

    @api.model
    def _create_attachment(self, part):
        """Create an ir.attachment from a message part."""
        filename = part.get_filename()
        if not filename:
            return self.env["ir.attachment"]
        content = part.get_payload(decode=True) or b""
        mimetype = part.get_content_type() or "application/octet-stream"
        return self.env["ir.attachment"].create({
            "name": filename,
            "datas": base64.b64encode(content),
            "mimetype": mimetype,
        })
