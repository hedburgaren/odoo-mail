# =============================================================================
# Hook för mail.personal.mailbox -> push-notis vid nytt inkommande mail
# =============================================================================

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class MailPersonalMailbox(models.Model):
    _inherit = "mail.personal.mailbox"

    @api.model_create_multi
    def create(self, vals_list):
        records = super(MailPersonalMailbox, self).create(vals_list)
        for mail in records:
            mail._schedule_push()
        return records

    def write(self, vals):
        result = super(MailPersonalMailbox, self).write(vals)
        if vals.get("state") == "unread":
            for mail in self:
                mail._schedule_push()
        return result

    def _schedule_push(self):
        """Skicka push när ett nytt inkommande mail landar i inbox."""
        self.ensure_one()
        if self.state != "unread":
            return
        if not self.user_id or not self.user_id.partner_id:
            return
        # Bara om mailet ligger i en inbox-mapp
        if not self.folder_id or self.folder_id.folder_type != "inbox":
            return

        sender = self.email_from or "Okänd avsändare"
        # Försök plocka ut namn om formatet är "Namn <email>"
        if "<" in sender and ">" in sender:
            sender = sender.split("<")[0].strip().strip('"')

        body_text = self.name or "Nytt mail"
        if len(body_text) > 120:
            body_text = body_text[:117] + "..."

        self.env["pwa.push.subscription"].sudo().send_push_to_partner(
            self.user_id.partner_id.id,
            title=f"Mail från {sender}",
            body=body_text,
            url="/unified_workspace",
            tag=f"personal-mail-{self.id}",
            requireInteraction=False,
        )
