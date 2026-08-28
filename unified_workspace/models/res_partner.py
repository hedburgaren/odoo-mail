# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def get_sales_insights(self):
        """Return a CRM pipeline summary for this contact."""
        self.ensure_one()
        Lead = self.env["crm.lead"]
        leads = Lead.search([
            ("partner_id", "=", self.id),
            ("type", "=", "opportunity"),
            ("probability", "<", 100),
            ("active", "=", True),
        ])
        next_activity = self.env["mail.activity"].search([
            ("res_model", "=", "crm.lead"),
            ("res_id", "in", leads.ids),
        ], order="date_deadline ASC, id ASC", limit=1)
        return {
            "open_opportunities_count": len(leads),
            "total_expected_revenue": sum(leads.mapped("expected_revenue")),
            "currency_symbol": self.env.company.currency_id.symbol,
            "next_activity": next_activity.summary or next_activity.activity_type_id.name if next_activity else None,
            "next_activity_date": next_activity.date_deadline if next_activity else None,
            "lead_ids": leads.ids,
        }
