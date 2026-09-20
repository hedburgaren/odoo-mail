# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import html
import re

from odoo import api, fields, models
from odoo.tools.translate import LazyTranslate

_lt = LazyTranslate(__name__)

# Placeholders are written as {{ namespace.field }} and resolved against a
# whitelist. Nothing outside the whitelist is touched, so a template can never
# reach a field or a method it was not meant to.
#
# The separator class covers ordinary whitespace plus the two shapes an HTML
# editor can leave inside the braces on its own: a literal &nbsp; entity and
# U+00A0. Without them a placeholder the user never touched would go out raw.
_SEP = r"(?:\s|&nbsp;|\u00a0)*"
PLACEHOLDER_RE = re.compile(
    r"\{\{" + _SEP + r"([A-Za-z_][A-Za-z0-9_.]*)" + _SEP + r"\}\}"
)

# The dynamic fields a template may use. Keys are the placeholder names, values
# are the human labels shown in the template form. LazyTranslate: the module is
# imported once, without a language, so an eager _() would freeze the labels in
# English for every user.
PLACEHOLDER_FIELDS = {
    "partner.name": _lt("Recipient name"),
    "partner.company_name": _lt("Recipient company"),
    "partner.email": _lt("Recipient email"),
    "partner.phone": _lt("Recipient phone"),
    "partner.city": _lt("Recipient city"),
    "user.name": _lt("Your name"),
    "user.email": _lt("Your email"),
    "user.phone": _lt("Your phone"),
    "user.company_name": _lt("Your company"),
    "date": _lt("Today's date"),
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
                for key, label in self.get_placeholder_fields().items()
            )

    @api.model
    def get_placeholder_fields(self):
        """Return the placeholder names and labels for the UI.

        The labels are lazily translated, so they are resolved here, in the
        caller's language, and not at import time.
        """
        return {key: str(label) for key, label in PLACEHOLDER_FIELDS.items()}

    @api.model
    def _placeholder_values(self, partner=None, final=False):
        """Build the placeholder value map for the current user and partner.

        Without a recipient the ``partner.*`` keys are left out of the map
        entirely. The renderer leaves anything it does not know untouched, so
        the placeholder survives in the text and can be filled in once the
        recipient is known. Rendering them to empty strings instead would
        delete them the moment the composer opens.

        ``final`` is the send-time pass: there is nothing left to fill in
        afterwards, so the ``partner.*`` keys are always in the map and an
        unresolved one becomes an empty string rather than going out raw.

        Returns plain strings. The caller decides whether they need HTML
        escaping (body) or not (subject).
        """
        user = self.env.user
        today = fields.Date.context_today(self)
        values = {
            "user.name": user.name or "",
            "user.email": user.email or "",
            "user.phone": user.phone or "",
            "user.company_name": user.company_id.name or "",
            "date": today.strftime("%Y-%m-%d"),
        }
        if partner or final:
            values.update({
                "partner.name": partner.name or "",
                "partner.company_name": partner.company_name or "",
                "partner.email": partner.email or "",
                "partner.phone": partner.phone or "",
                "partner.city": partner.city or "",
            })
        return values

    @api.model
    def _render_placeholders(self, text, partner=None, escape=True, final=False):
        """Replace whitelisted {{ placeholders }} in ``text``.

        Unknown placeholders are left as they are, so a half-finished template
        stays visible instead of silently losing text. The same goes for
        ``partner.*`` when no recipient is known yet, unless ``final`` is set
        (the send-time pass). When ``escape`` is set,
        the substituted values are HTML-escaped so a partner name containing
        markup cannot break the body.
        """
        if not text:
            return text or ""
        values = self._placeholder_values(partner, final=final)

        def _replace(match):
            key = match.group(1)
            key = PLACEHOLDER_ALIASES.get(key, key)
            if key not in values:
                return match.group(0)
            value = values[key]
            return html.escape(value) if escape else value

        return PLACEHOLDER_RE.sub(_replace, str(text))

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
        optional: without it the ``partner.*`` placeholders are left in the
        text for later, while user and date resolve straight away.
        """
        self.ensure_one()
        # exists(): a stale id from the browser must not raise MissingError,
        # the template is simply rendered without recipient data.
        partner = (
            self.env["res.partner"].browse(partner_id).exists()
            if partner_id
            else self.env["res.partner"]
        )
        return {
            "subject": self._render_placeholders(self.subject, partner, escape=False),
            "body": self._render_placeholders(self.body or "", partner, escape=True),
        }

    @api.model
    def render_for_partner(self, subject=None, body=None, partner_id=None):
        """Render the placeholders still left in composer text.

        The composer calls this when the recipient changes: the text at that
        point is whatever the user has written or edited, so only the
        placeholders that are still there get filled in and nothing the user
        typed is replaced. Partner data is read as the current user, so the
        record rules on res.partner apply.
        """
        partner = (
            self.env["res.partner"].browse(partner_id).exists()
            if partner_id
            else self.env["res.partner"]
        )
        return {
            "subject": self._render_placeholders(subject or "", partner, escape=False),
            "body": self._render_placeholders(body or "", partner, escape=True),
        }
