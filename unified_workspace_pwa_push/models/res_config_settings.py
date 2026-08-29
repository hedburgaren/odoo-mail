# =============================================================================
# Inställningar för PWA push
# =============================================================================

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pwa_push_enabled = fields.Boolean(
        string="Aktivera PWA-pushnotiser",
        config_parameter="unified_workspace_pwa_push.push_enabled",
        default=True,
        help="Slå på/av Web Push-notiser för PWA:n.",
    )
    pwa_push_vapid_public_key = fields.Char(
        string="VAPID publik nyckel",
        readonly=True,
        config_parameter="unified_workspace_pwa_push.vapid_public_key",
    )
    pwa_push_vapid_subscriber = fields.Char(
        string="VAPID ägare (e-post)",
        config_parameter="unified_workspace_pwa_push.vapid_subscriber_email",
        help="Mailto-adress som äger VAPID-nycklarna.",
    )
