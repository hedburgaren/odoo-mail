# =============================================================================
# PWA push subscription-modell
# =============================================================================

import json
import logging

import requests

from odoo import _, api, fields, models

from ..utils.pwa_push_crypto import (
    build_push_headers,
    encrypt_payload,
    generate_vapid_keys,
)

_logger = logging.getLogger(__name__)


class PwaPushSubscription(models.Model):
    _name = "pwa.push.subscription"
    _description = "PWA Push Subscription"
    _order = "write_date desc"

    partner_id = fields.Many2one(
        "res.partner",
        string="Kontakt",
        required=True,
        index=True,
        ondelete="cascade",
        help="Prenumerationen tillhör denna kontakt.",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Användare",
        index=True,
        ondelete="set null",
        help="Om kontakten har en kopplad användare.",
    )
    endpoint = fields.Char(required=True, index=True)
    p256dh = fields.Char(required=True, string="P256DH")
    auth = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("endpoint_unique", "UNIQUE(endpoint)", "Endpoint måste vara unik."),
    ]

    # -------------------------------------------------------------------------
    # VAPID-nycklar via ICP
    # -------------------------------------------------------------------------

    @api.model
    def _get_vapid_keys(self):
        ICP = self.env["ir.config_parameter"].sudo()
        private_key = ICP.get_param("unified_workspace_pwa_push.vapid_private_key")
        public_key = ICP.get_param("unified_workspace_pwa_push.vapid_public_key")

        if not private_key or not public_key:
            private_key, public_key = generate_vapid_keys()
            ICP.set_param(
                "unified_workspace_pwa_push.vapid_private_key", private_key
            )
            ICP.set_param(
                "unified_workspace_pwa_push.vapid_public_key", public_key
            )
            _logger.info("Genererade nya VAPID-nycklar för PWA push.")

        return private_key, public_key

    @api.model
    def _get_vapid_subscriber(self):
        ICP = self.env["ir.config_parameter"].sudo()
        email = ICP.get_param("unified_workspace_pwa_push.vapid_subscriber_email")
        if not email:
            email = self.env.company.email or "info@plastshop.se"
        return email

    # -------------------------------------------------------------------------
    # Prenumerera / avprenumerera
    # -------------------------------------------------------------------------

    @api.model
    def subscribe(self, partner_id, endpoint, p256dh, auth, user_id=None):
        existing = self.search([("endpoint", "=", endpoint)], limit=1)
        if existing:
            existing.write({
                "partner_id": partner_id,
                "user_id": user_id or existing.user_id.id,
                "p256dh": p256dh,
                "auth": auth,
                "active": True,
            })
            return existing.id

        return self.create({
            "partner_id": partner_id,
            "user_id": user_id,
            "endpoint": endpoint,
            "p256dh": p256dh,
            "auth": auth,
        }).id

    @api.model
    def unsubscribe(self, endpoint):
        sub = self.search([("endpoint", "=", endpoint)], limit=1)
        if sub:
            sub.active = False
        return bool(sub)

    # -------------------------------------------------------------------------
    # Skicka push
    # -------------------------------------------------------------------------

    def _build_payload(self, title, body, icon=None, badge=None,
                       tag=None, requireInteraction=False,
                       data=None, url=None):
        """Bygg JSON-payload enligt Web Push Notification standard."""
        payload = {
            "title": title,
            "body": body,
            "requireInteraction": requireInteraction,
        }
        if icon:
            payload["icon"] = icon
        if badge:
            payload["badge"] = badge
        if tag:
            payload["tag"] = tag
        if data:
            payload["data"] = data
        if url:
            payload["data"] = payload.get("data", {})
            payload["data"]["url"] = url
        return payload

    def send_push(self, title, body, icon=None, badge=None, tag=None,
                  requireInteraction=False, data=None, url=None):
        """Skicka push-notis till denna prenumeration."""
        self.ensure_one()
        if not self.active:
            return {"status": "skipped", "reason": "inactive"}

        private_key, public_key = self._get_vapid_keys()
        subscriber_email = self._get_vapid_subscriber()

        payload_dict = self._build_payload(
            title, body, icon=icon, badge=badge, tag=tag,
            requireInteraction=requireInteraction, data=data, url=url,
        )
        plaintext = json.dumps(payload_dict).encode("utf-8")

        encrypted = encrypt_payload(
            plaintext,
            self.p256dh,
            self.auth,
        )

        headers = build_push_headers(
            self.endpoint,
            private_key,
            public_key,
            subscriber_email,
        )

        try:
            response = requests.post(
                self.endpoint,
                data=encrypted,
                headers=headers,
                timeout=10,
            )
            if response.status_code in (404, 410):
                # Prenumerationen är borttagen på klienten
                self.active = False
                return {"status": "unsubscribed", "code": response.status_code}
            response.raise_for_status()
            return {"status": "ok", "code": response.status_code}
        except requests.exceptions.RequestException as e:
            _logger.warning(
                "Kunde inte skicka push till %s: %s", self.endpoint, e
            )
            return {"status": "error", "error": str(e)}

    @api.model
    def send_push_to_partner(self, partner_id, title, body, url=None,
                             tag=None, requireInteraction=False,
                             data=None):
        """Skicka notis till alla aktiva prenumerationer för en partner."""
        ICP = self.env["ir.config_parameter"].sudo()
        if not ICP.get_param("unified_workspace_pwa_push.push_enabled", "True") == "True":
            return []
        subscriptions = self.search([
            ("partner_id", "=", partner_id),
            ("active", "=", True),
        ])
        results = []
        for sub in subscriptions:
            results.append(sub.send_push(
                title, body, url=url, tag=tag,
                requireInteraction=requireInteraction, data=data,
            ))
        return results

    # -------------------------------------------------------------------------
    # Server action: generera nya VAPID-nycklar
    # -------------------------------------------------------------------------

    @api.model
    def action_generate_vapid_keys(self):
        private_key, public_key = generate_vapid_keys()
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("unified_workspace_pwa_push.vapid_private_key", private_key)
        ICP.set_param("unified_workspace_pwa_push.vapid_public_key", public_key)
        _logger.info("VAPID-nycklar genererade om via server action.")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("VAPID-nycklar"),
                "message": _(
                    "Nya nycklar genererade. Kom ihåg att uppdatera "
                    "prenumerationerna på klienterna."
                ),
                "type": "success",
                "sticky": True,
            },
        }
