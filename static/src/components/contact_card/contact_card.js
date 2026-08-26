/** @odoo-module **/

import { Component, onWillUpdateProps, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Contact card shown in the reading pane.
 */
export class ContactCard extends Component {
    static template = "unified_workspace.ContactCard";
    static props = {
        partnerId: { type: [Number, { value: null }], optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ partner: null, leads: [], tasks: [], insights: null });
        if (this.props.partnerId) {
            this.loadPartner(this.props.partnerId);
        }
        onWillUpdateProps((nextProps) => {
            if (nextProps.partnerId && nextProps.partnerId !== this.props.partnerId) {
                this.loadPartner(nextProps.partnerId);
            }
        });
    }

    get partner() {
        return this.state.partner;
    }

    get opportunityLabel() {
        const count = this.state.insights?.open_opportunities_count || 0;
        return `${count} open opportunity${count === 1 ? "" : "ies"}`;
    }

    async loadPartner(partnerId) {
        const partners = await this.orm.read(
            "res.partner",
            [partnerId],
            ["name", "email", "phone", "mobile", "is_company", "title"]
        );
        this.state.partner = partners[0] || null;
        this.state.leads = await this.orm.searchRead(
            "crm.lead",
            [["partner_id", "=", partnerId]],
            ["name", "stage_id", "email_from"],
            { limit: 5, order: "create_date DESC" }
        );
        this.state.tasks = await this.orm.searchRead(
            "project.task",
            [["partner_id", "=", partnerId]],
            ["name", "stage_id"],
            { limit: 5, order: "create_date DESC" }
        );
        this.state.insights = await this.orm.call("res.partner", "get_sales_insights", [[partnerId]]);
    }
}
