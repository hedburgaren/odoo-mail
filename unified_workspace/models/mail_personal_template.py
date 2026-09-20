# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import html
import re

from odoo import api, fields, models, _

# Placeholders are written as {{ namespace.field }} and resolved against a
# whitelist. Nothing outside the whitelist is touched, so a template can never
# reach a field or a method it was not meant to.
PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}")

# The dynamic fields a template may use. Keys are the placeholder names, values
# are the human labels shown in the template form.
PLACEHOLDER_FIELDS = {
    "partner.name": _("Recipient name"),
    "partner.company_name": _("Recipient company"),
    "partner.email": _("Recipient email"),
    "partner.phone": _("Recipient phone"),
    "partner.city": _("Recipient city"),
    "user.name": _("Your name"),
    "user.email": _("Your email"),
    "user.phone": _("Your phone"),
    "user.company_name": _("Your company"),
    "date": _("Today's date"),
}

# Aliases resolved to the same value as their target, so "recipient" reads
# naturally in a template without doubling the whitelist.
PLACEHOLDER_ALIASES = {
    "recipient.name": "partner.name",
    "recipient.company_name": "partner.company_name",
    "recipient.email": "partner.email",
    "recipient.phone": "partner.phone",
    "recipient.city": "partner.city",
    "company.name": "user.company_name",
}


class MailPersonalTemplate(models.Model):
    _name = "mail.personal.template"
    _description = "Personal Email Template"
    _order = "is_default DESC, name"

    name = fields.Char(string="Template Name", required=True, translate=True)
    user_id = fields.Many2one(
        "res.users",
        string="User",
        default=lambda self: self.env.user,
        index=True,
        ondelete="cascade",
        help="Leave empty to share the template with all users.",
    )
    subject = fields.Char(string="Subject", required=True, translate=True)
    body = fields.Html(string="Body", sanitize=True, translate=True)
    body_text = fields.Text(
        string="Body Preview",
        compute="_compute_body_text",
        store=True,
    )
    is_default = fields.Boolean(string="Default Template", default=False)
    placeholder_help = fields.Text(
        string="Available Placeholders",
        compute="_compute_placeholder_help",
    )

    @api.depends("body")
    def _compute_body_text(self):
        for template in self:
            text = re.sub(r"<[^>]+>", " ", template.body or "")
            template.body_text = " ".join(text.split())

    @api.depends()
    def _compute_placeholder_help(self):
        for template in self:
            template.placeholder_help = "\n".join(
                "{{ %s }}: %s" % (key, label)
                for key, label in PLACEHOLDER_FIELDS.items()
            )

    @api.model
    def get_placeholder_fields(self):
        """Return the placeholder names and labels for the UI."""
        return dict(PLACEHOLDER_FIELDS)

    def _placeholder_values(self, partner=None):
        """Build the placeholder value map for the current user and partner.

        Returns plain strings. The caller decides whether they need HTML
        escaping (body) or not (subject).
        """
        self.ensure_one()
        user = self.env.user
        partner = partner or self.env["res.partner"]
        today = fields.Date.context_today(self)
        return {
            "partner.name": partner.name or "",
            "partner.company_name": partner.company_name or "",
            "partner.email": partner.email or "",
            "partner.phone": partner.phone or "",
            "partner.city": partner.city or "",
            "user.name": user.name or "",
            "user.email": user.email or "",
            "user.phone": user.phone or "",
            "user.company_name": user.company_id.name or "",
            "date": today.strftime("%Y-%m-%d"),
        }

    def _render_placeholders(self, text, partner=None, escape=True):
        """Replace whitelisted {{ placeholders }} in ``text``.

        Unknown placeholders are left as they are, so a half-finished template
        stays visible instead of silently losing text. When ``escape`` is set,
        the substituted values are HTML-escaped so a partner name containing
        markup cannot break the body.
        """
        self.ensure_one()
        if not text:
            return text or ""
        values = self._placeholder_values(partner)

        def _replace(match):
            key = match.group(1)
            key = PLACEHOLDER_ALIASES.get(key, key)
            if key not in values:
                return match.group(0)
            value = values[key]
            return html.escape(value) if escape else value

        return PLACEHOLDER_RE.sub(_replace, text)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("is_default"):
                domain = [("user_id", "=", vals.get("user_id", self.env.user.id))]
                if not vals.get("user_id"):
                    domain = [("user_id", "=", False)]
                self.search(domain).write({"is_default": False})
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("is_default"):
            for template in self:
                domain = [("user_id", "=", template.user_id.id)]
                if not template.user_id:
                    domain = [("user_id", "=", False)]
                self.search(domain).write({"is_default": False})
        return super().write(vals)

    def action_use_template(self, partner_id=None):
        """Return the template data for the composer, placeholders rendered.

        ``partner_id`` is the recipient the placeholders resolve against. It is
        optional: without it the partner placeholders render as empty strings
        and the user/user/date placeholders still resolve.
        """
        self.ensure_one()
        partner = self.env["res.partner"].browse(partner_id) if partner_id else None
        return {
            "subject": self._render_placeholders(self.subject, partner, escape=False),
            "body": self._render_placeholders(self.body or "", partner, escape=True),
        }
