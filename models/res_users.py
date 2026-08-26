# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ResUsers(models.Model):
    _inherit = "res.users"

    email_signature = fields.Html(
        string="Personal Email Signature",
        help="Signature appended to outgoing emails from the personal mailbox.",
    )
    email_signature_external = fields.Html(
        string="External Personal Email Signature",
        help="Signature used for emails sent to external recipients.",
    )
    imap_server_id = fields.Many2one(
        "fetchmail.server",
        string="Personal IMAP Server",
        domain="[('server_type', '=', 'imap'), ('is_personal_mailbox_server', '=', True)]",
        help="IMAP server used to fetch this user's personal email.",
    )
    smtp_server_id = fields.Many2one(
        "ir.mail_server",
        string="Personal SMTP Server",
        help="SMTP server used to send this user's personal email.",
    )
    use_external_signature = fields.Boolean(
        string="Use External Signature",
        default=False,
        help="Use the external signature when recipients are outside the company.",
    )

    @api.model
    def _get_personal_signature(self, partners=None):
        """Return the signature to use for the given recipient partners."""
        self.ensure_one()
        if not partners:
            return self.email_signature or ""
        internal_users = self.env["res.users"].search([
            ("partner_id", "in", partners.ids),
            ("share", "=", False),
            ("active", "=", True),
        ])
        if internal_users or not self.email_signature_external:
            return self.email_signature or ""
        return self.email_signature_external
