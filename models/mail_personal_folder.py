# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MailPersonalFolder(models.Model):
    _name = "mail.personal.folder"
    _description = "Personal Email Folder"
    _order = "sequence, name"
    _rec_name = "display_name"

    name = fields.Char(string="Folder Name", required=True, translate=True)
    display_name = fields.Char(string="Display Name", compute="_compute_display_name")
    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        ondelete="cascade",
    )
    parent_id = fields.Many2one(
        "mail.personal.folder",
        string="Parent Folder",
        index=True,
        ondelete="cascade",
        domain="[('user_id', '=', user_id)]",
    )
    child_ids = fields.One2many("mail.personal.folder", "parent_id", string="Subfolders")
    message_ids = fields.One2many(
        "mail.personal.mailbox",
        "folder_id",
        string="Messages",
    )
    folder_type = fields.Selection(
        selection=[
            ("inbox", "Inbox"),
            ("custom", "Custom"),
        ],
        string="Folder Type",
        default="custom",
        required=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)
    is_system = fields.Boolean(
        string="System Folder",
        compute="_compute_is_system",
        store=True,
        help="System folders are created automatically and cannot be deleted.",
    )
    message_count = fields.Integer(
        string="Message Count",
        compute="_compute_message_count",
        store=False,
    )

    _sql_constraints = [
        (
            "unique_system_folder_per_user",
            "UNIQUE(user_id, folder_type)",
            "A user can only have one system folder of each type.",
        ),
    ]

    @api.depends("name", "folder_type")
    def _compute_display_name(self):
        for folder in self:
            folder.display_name = folder.name

    @api.depends("folder_type")
    def _compute_is_system(self):
        for folder in self:
            folder.is_system = folder.folder_type != "custom"

    @api.depends("message_ids")
    def _compute_message_count(self):
        counts = {
            item["folder_id"][0]: item["folder_id_count"]
            for item in self.env["mail.personal.mailbox"].read_group(
                [("folder_id", "in", self.ids)],
                ["folder_id"],
                ["folder_id"],
            )
        }
        for folder in self:
            folder.message_count = counts.get(folder.id, 0)

    @api.constrains("parent_id")
    def _check_parent_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_("You cannot create recursive folder structures."))

    @api.constrains("folder_type")
    def _check_unique_system_folder(self):
        # Enforced by SQL constraint, but keep a friendly Python check.
        for folder in self.filtered(lambda f: f.is_system):
            existing = self.search([
                ("id", "!=", folder.id),
                ("user_id", "=", folder.user_id.id),
                ("folder_type", "=", folder.folder_type),
            ], limit=1)
            if existing:
                raise ValidationError(_(
                    "User %(user)s already has a %(type)s folder.",
                    user=folder.user_id.name,
                    type=folder.folder_type,
                ))

    @api.ondelete(at_uninstall=False)
    def _unlink_except_system(self):
        for folder in self:
            if folder.is_system:
                raise ValidationError(_(
                    "System folder '%(folder)s' cannot be deleted.",
                    folder=folder.name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("folder_type") and vals["folder_type"] != "custom":
                user_id = vals.get("user_id", self.env.user.id)
                existing = self.search([
                    ("user_id", "=", user_id),
                    ("folder_type", "=", vals["folder_type"]),
                ], limit=1)
                if existing:
                    raise ValidationError(_(
                        "User already has a %(type)s folder.",
                        type=vals["folder_type"],
                    ))
                if not vals.get("name"):
                    vals["name"] = dict(self._fields["folder_type"].selection).get(
                        vals["folder_type"], vals["folder_type"]
                    )
        return super().create(vals_list)

    def _get_system_folder(self, user, folder_type):
        """Return the system folder for a user, creating it if needed.

        Only Inbox remains as a system folder; Sent/Drafts/Trash have been removed.
        """
        if folder_type != "inbox":
            raise UserError(_("%(type)s is no longer a system folder.", type=folder_type))
        folder = self.search([
            ("user_id", "=", user.id),
            ("folder_type", "=", folder_type),
        ], limit=1)
        if folder:
            return folder
        return self.create({
            "user_id": user.id,
            "folder_type": folder_type,
            "sequence": 1,
        })
