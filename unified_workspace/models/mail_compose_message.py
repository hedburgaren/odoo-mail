# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError
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
        body = self._ensure_signature(self.body or "")
        mail_values = {
            "subject": self.subject or _("(No subject)"),
            "body_html": body,
            "email_from": self.email_from or self.env.user.email_formatted,
            # Utan explicit reply_to satte Odoo catchall@<domän> som Reply-To.
            # Svar hamnade då i catchall-routing där tråden inte finns kvar
            # (auto_delete raderar vårt Message-ID) och bouncades: Oscar fick
            # 24 studsar på ett svar (2026-09-07). Svar ska gå till avsändaren.
            "reply_to": self.email_from or self.env.user.email_formatted,
            "recipient_ids": [(6, 0, to_partners.ids)],
            "email_cc": self.email_cc or "",
            "attachment_ids": [(6, 0, self.attachment_ids.ids)],
            "auto_delete": True,
        }
        mail = self.env["mail.mail"].sudo().create(mail_values)
        mail.send(raise_exception=True)

    def _ensure_signature(self, body):
        """Insert the sender's signature above the quoted part, once.

        Signaturen infogas server-side vid själva sändningen: klientens
        infogning byggde på mail.store-uid som saknas i workspacet, så
        mottagaren fick mail utan signatur medan den lokala kopian fick en
        i efterhand (2026-09-07). Placering: i slutet av svaret, ovanför
        det citerade (uw_quote-markören från _prepare_reply_body).
        """
        # str-koercering: body är Markup (Html-fält) och Markup + str
        # HTML-escapar inskottet ('<br/>' blev '&lt;br/&gt;' i test).
        body = str(body)
        signature = str(self.env.user._get_personal_signature(self.partner_ids) or "")
        if not signature or signature in body:
            return body
        marker = '<div class="uw_quote"'
        idx = body.find(marker)
        if idx >= 0:
            return body[:idx] + "<br/>" + signature + body[idx:]
        return body + "<br/>" + signature

    def _save_sent_copy(self):
        """Post-send bookkeeping for a personal email.

        Ingen inkorgskopia längre: blandad in- och utkorg var rörigt och
        Gmail sparar utgående i sin Sent-katalog (Chrille 2026-09-07).
        Kvar: statusflytt på originalet och loggning till valt record.
        """
        self.ensure_one()
        # Link the original message if it was a reply/forward.
        if self.personal_mailbox_id:
            if self.subject and self.subject.lower().startswith("fwd:"):
                self.personal_mailbox_id.write({"state": "forwarded"})
            else:
                self.personal_mailbox_id.write({"state": "replied"})

        if self.log_to_model and self.log_to_res_id:
            self._post_to_record()

    def _post_to_record(self):
        """Post a copy of the sent email to the chatter of another record."""
        self.ensure_one()
        try:
            record = self.env[self.log_to_model].browse(self.log_to_res_id)
            if record.exists() and hasattr(record, "message_post"):
                record.message_post(
                    subject=self.subject,
                    body=html_sanitize(self._ensure_signature(self.body or "")),
                    partner_ids=self.partner_ids.ids,
                    attachment_ids=self.attachment_ids.ids,
                )
        except Exception:
            _logger.exception("Failed to log personal email to %s/%s", self.log_to_model, self.log_to_res_id)

    def action_send_and_discard(self):
        """Send the message and close the composer."""
        self._action_send_mail()
        return {"type": "ir.actions.act_window_close"}
