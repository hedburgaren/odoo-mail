# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


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

    @api.depends("body")
    def _compute_body_text(self):
        import re
        for template in self:
            text = re.sub(r"<[^>]+>", " ", template.body or "")
            template.body_text = " ".join(text.split())

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

    def action_use_template(self):
        """Return the template data for the composer."""
        self.ensure_one()
        return {
            "subject": self.subject,
            "body": self.body or "",
        }
