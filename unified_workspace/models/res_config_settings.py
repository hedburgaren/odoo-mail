# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    unified_workspace_auto_archive_enabled = fields.Boolean(
        string="Auto-archive old emails",
        help="Move personal emails older than the configured threshold to the trash folder.",
        config_parameter="unified_workspace.auto_archive_enabled",
        default=False,
    )
    unified_workspace_auto_archive_days = fields.Integer(
        string="Archive after (days)",
        help="Emails older than this number of days are moved to trash.",
        config_parameter="unified_workspace.auto_archive_days",
        default=365,
    )
    unified_workspace_gdpr_deletion_enabled = fields.Boolean(
        string="GDPR deletion of old emails",
        help="Permanently delete personal emails older than the configured threshold.",
        config_parameter="unified_workspace.gdpr_deletion_enabled",
        default=False,
    )
    unified_workspace_gdpr_deletion_days = fields.Integer(
        string="Delete after (days)",
        help="Emails older than this number of days are permanently deleted.",
        config_parameter="unified_workspace.gdpr_deletion_days",
        default=2555,
    )

    @api.constrains("unified_workspace_auto_archive_days")
    def _check_auto_archive_days(self):
        for setting in self:
            if setting.unified_workspace_auto_archive_enabled and setting.unified_workspace_auto_archive_days < 1:
                raise ValueError("Archive threshold must be at least 1 day.")

    @api.constrains("unified_workspace_gdpr_deletion_days")
    def _check_gdpr_deletion_days(self):
        for setting in self:
            if setting.unified_workspace_gdpr_deletion_enabled and setting.unified_workspace_gdpr_deletion_days < 1:
                raise ValueError("Deletion threshold must be at least 1 day.")
