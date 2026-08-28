{
    "name": "Unified Workspace PWA Push",
    "version": "18.0.1.0.0",
    "author": "ARC Gruppen AB",
    "maintainer": "Chrille Hedberg",
    "maintainer_email": "chrille.hedberg@arcgruppen.se",
    "website": "https://github.com/hedburgaren/odoo-mail",
    "license": "LGPL-3",
    "category": "Productivity",
    "summary": "Web Push-notiser for PlastShop PWA: mail, chatter och live chat.",
    "description": """
Unified Workspace PWA Push
==========================

Lagger Web Push-notiser ovanpa PWA:n i arc_industrial_ui. Prenumerationer
kopplas till res.partner. Notiser skickas vid:

* nya mail.notification (chatter/mentions/live chat)
* nya inkommande mail i mail.personal.mailbox

Implementeringen anvander Python-biblioteket cryptography for VAPID-signering
och aes128gcm-kryptering, sa inget extra pip-paket behovs.

Beroenden: arc_industrial_ui, mail, im_livechat, unified_workspace.
""",
    "depends": [
        "arc_industrial_ui",
        "mail",
        "im_livechat",
        "unified_workspace",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "data/server_actions.xml",
        "views/res_config_settings_views.xml",
        "views/pwa_push_subscription_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "unified_workspace_pwa_push/static/src/js/pwa_push_register.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
