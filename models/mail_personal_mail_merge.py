# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from markupsafe import escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)


class MailPersonalMailMerge(models.TransientModel):
    _name = "mail.personal.mail.merge"
    _description = "Personal Mail Merge"

    partner_ids = fields.Many2many(
        "res.partner",
        string="Recipients",
        required=True,
        help="Contacts that will receive a separate, personalized email.",
    )
    subject = fields.Char(string="Subject")
    body = fields.Html(
        string="Body",
        sanitize=True,
        help="Available placeholders: {{name}}, {{email}}, {{company}}, {{first_name}}, {{last_name}}.",
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "mail_personal_mail_merge_attachment_rel",
        "merge_id",
        "attachment_id",
        string="Attachments",
    )

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        active_ids = self.env.context.get("active_ids") or []
        if active_ids and self.env.context.get("active_model") == "res.partner":
            defaults["partner_ids"] = [(6, 0, active_ids)]
        return defaults

    def action_open_wizard(self):
        """Return an action that opens the mail merge wizard."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "views": [(False, "form")],
            "name": _("Mail Merge"),
        }

    def action_send(self):
        """Send one personalized email per recipient."""
        self.ensure_one()
        if not self.subject:
            raise UserError(_("Please enter a subject."))
        if not self.body:
            raise UserError(_("Please enter a message body."))
        partners = self.partner_ids.filtered("email")
        skipped = len(self.partner_ids) - len(partners)

        for partner in partners:
            subject = self._render_text(self.subject or "", partner)
            body = self._render_html(self.body or "", partner)
            composer_values = {
                "composition_mode": "personal_email",
                "subject": subject,
                "body": body,
                "partner_ids": [(6, 0, partner.ids)],
            }
            composer = self.env["mail.compose.message"].create(composer_values)
            if self.attachment_ids:
                composer.attachment_ids = [(6, 0, self.attachment_ids.ids)]
            composer.action_send_mail()

        message = _(
            "%(count)d email(s) sent.",
            count=len(partners),
        )
        if skipped:
            message = _(
                "%(count)d email(s) sent; %(skipped)d contact(s) skipped because they have no email address.",
                count=len(partners),
                skipped=skipped,
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": message,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _render_text(self, text, partner):
        """Replace placeholders in a plain text string."""
        return self._replace_tokens(text, partner, escape_html=False)

    def _render_html(self, text, partner):
        """Replace placeholders in an HTML string."""
        rendered = self._replace_tokens(text, partner, escape_html=True)
        return html_sanitize(rendered)

    def _replace_tokens(self, text, partner, escape_html=False):
        """Replace supported placeholders with partner data."""
        if not text:
            return text

        first_name, last_name = self._split_name(partner.name or "")
        company = partner.parent_id.name or partner.company_name or ""

        values = {
            "name": partner.name or "",
            "email": partner.email or "",
            "company": company,
            "first_name": first_name,
            "last_name": last_name,
        }

        result = text
        for key, value in values.items():
            token = f"{{{{{key}}}}}"
            replacement = escape(value) if escape_html else value
            result = result.replace(token, replacement)

        return result

    @api.model
    def _split_name(self, name):
        """Return (first_name, last_name) from a full name."""
        parts = (name or "").strip().split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])
