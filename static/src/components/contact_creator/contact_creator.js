/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Modal for creating a res.partner from an unknown email address.
 *
 * Lets the user set first name, last name and company before the contact
 * is created, so the partner is not left floating without a company link.
 */
export class ContactCreator extends Component {
    static template = "unified_workspace.ContactCreator";
    static props = {
        email: { type: String },
        close: { type: Function },
        onCreate: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            firstName: "",
            lastName: "",
            companyName: "",
            isLoading: false,
        });
        this._prefillFromEmail();
    }

    _prefillFromEmail() {
        const local = this.props.email.split("@")[0] || "";
        const parts = local.replace(/[._]+/g, " ").trim().split(/\s+/);
        if (parts.length > 1) {
            this.state.firstName = parts[0];
            this.state.lastName = parts.slice(1).join(" ");
        } else {
            this.state.firstName = local;
        }
    }

    async onSave() {
        const name = `${this.state.firstName} ${this.state.lastName}`.trim();
        if (!name) {
            this.notification.add("First name and last name are required.", { type: "danger" });
            return;
        }
        this.state.isLoading = true;
        try {
            let companyId = false;
            if (this.state.companyName.trim()) {
                companyId = await this._findOrCreateCompany(this.state.companyName.trim());
            }
            const values = {
                name: name,
                email: this.props.email,
                company_type: "person",
            };
            if (companyId) {
                values.parent_id = companyId;
            }
            let partnerId = await this.orm.create("res.partner", [values]);
            if (Array.isArray(partnerId)) {
                partnerId = partnerId[0];
            }
            if (this.props.onCreate) {
                this.props.onCreate(partnerId);
            }
            this.props.close();
        } finally {
            this.state.isLoading = false;
        }
    }

    async _findOrCreateCompany(companyName) {
        const companies = await this.orm.searchRead(
            "res.partner",
            [["is_company", "=", true], ["name", "=ilike", companyName]],
            ["id"]
        );
        if (companies.length) {
            return companies[0].id;
        }
        const companyId = await this.orm.create("res.partner", [{
            name: companyName,
            is_company: true,
            company_type: "company",
        }]);
        return Array.isArray(companyId) ? companyId[0] : companyId;
    }

    onCancel() {
        if (this.props.onCreate) {
            this.props.onCreate(null);
        }
        this.props.close();
    }
}
