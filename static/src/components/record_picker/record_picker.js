/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Simple record picker for logging a sent email to another Odoo record.
 *
 * Lets the user choose a model (CRM lead, partner, sale order, purchase order,
 * project task) and search for a record by name.
 */
export class RecordPicker extends Component {
    static template = "unified_workspace.RecordPicker";
    static props = {
        close: { type: Function },
        onSelect: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.onConfirm = this.onConfirm.bind(this);
        this.onCancel = this.onCancel.bind(this);
        this.onSearch = this.onSearch.bind(this);
        this.state = useState({
            selectedModel: "crm.lead",
            searchQuery: "",
            records: [],
            selectedRecordId: null,
            isLoading: false,
        });
        this.models = [
            { value: "crm.lead", label: "CRM Lead" },
            { value: "res.partner", label: "Contact" },
            { value: "sale.order", label: "Sales Order" },
            { value: "purchase.order", label: "Purchase Order" },
            { value: "project.task", label: "Project Task" },
        ];
    }

    async onSearch() {
        if (!this.state.searchQuery.trim()) {
            this.state.records = [];
            return;
        }
        this.state.isLoading = true;
        try {
            const result = await this.orm.call(this.state.selectedModel, "name_search", [], {
                name: this.state.searchQuery.trim(),
                operator: "ilike",
                limit: 20,
            });
            this.state.records = result.map(([id, name]) => ({ id, name }));
        } finally {
            this.state.isLoading = false;
        }
    }

    onConfirm() {
        const recordId = parseInt(this.state.selectedRecordId, 10);
        if (!recordId) {
            this.notification.add("Please select a record.", { type: "warning" });
            return;
        }
        if (this.props.onSelect) {
            this.props.onSelect({
                model: this.state.selectedModel,
                res_id: recordId,
            });
        }
        this.props.close();
    }

    onCancel() {
        if (this.props.onSelect) {
            this.props.onSelect(null);
        }
        this.props.close();
    }
}
