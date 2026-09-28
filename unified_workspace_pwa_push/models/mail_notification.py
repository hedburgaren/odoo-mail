# =============================================================================
# Hook för mail.notification -> push-notis
# =============================================================================

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MailNotification(models.Model):
    _inherit = "mail.notification"

    @api.model_create_multi
    def create(self, vals_list):
        notifications = super(MailNotification, self).create(vals_list)
        for notif in notifications:
            if notif.notification_status == "sent":
                notif._schedule_push()
        return notifications

    def write(self, vals):
        result = super(MailNotification, self).write(vals)
        if vals.get("notification_status") == "sent":
            for notif in self:
                notif._schedule_push()
        return result

    @api.model
    def _push_enabled_on_this_instance(self):
        """Får den här instansen skicka push till en riktig telefon?

        En stagingklon ärver produktionens prenumerationer, och prenumerationen
        pekar på Chrilles faktiska enhet. Den 2026-09-14 aktiverades två workers
        på staging och arbetade av en backlog; 300 chatterposter på arc.case
        blev omkring 250 pushnotiser som låg och väntade tills webbläsaren
        öppnades nästa morgon. Inget mail lämnade klonen, för staging har en
        svarthåls-SMTP. Push hade ingen motsvarande spärr.

        Grinden är samma nyckel som arc_ai_worker använder, med flit. Två
        switchar för samma fråga betyder att någon glömmer den ena, och den
        här nyckeln är redan satt på staging. Saknas nyckeln (modulen inte
        installerad) är default True, alltså oförändrat beteende.

        Att avaktivera prenumerationsraderna räcker inte: de kommer tillbaka
        med nästa klon från produktionen.
        """
        param = self.env["ir.config_parameter"].sudo().get_param(
            "arc_ai_worker.notifications_enabled", "True")
        return str(param).strip().lower() not in ("false", "0", "no", "off")

    def _schedule_push(self):
        """Skicka push till mottagaren om status är sent."""
        self.ensure_one()
        if not self._push_enabled_on_this_instance():
            return
        if not self.res_partner_id:
            return
        if self.notification_status != "sent":
            return
        if self.notification_type not in ("email", "inbox", "push"):
            return

        message = self.mail_message_id
        if not message:
            return

        author_name = message.author_id.name or message.email_from or "PlastShop"
        body_text = message.preview or "Nytt meddelande"
        # Kort ned body_text om den är för lång
        if len(body_text) > 120:
            body_text = body_text[:117] + "..."

        url = self._get_notification_url()
        self.env["pwa.push.subscription"].sudo().send_push_to_partner(
            self.res_partner_id.id,
            title=author_name,
            body=body_text,
            url=url,
            tag=f"mail-{self.id}",
            requireInteraction=False,
        )

    def _get_notification_url(self):
        """Bygg en URL som öppnar chatter/meddelandet."""
        message = self.mail_message_id
        if message and message.res_id and message.model:
            return f"/web#id={message.res_id}&model={message.model}&view_type=form"
        return "/web"
