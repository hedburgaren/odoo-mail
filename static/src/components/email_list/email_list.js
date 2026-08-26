/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

/**
 * Email list component for the Unified Workspace.
 */
export class EmailList extends Component {
    static template = "unified_workspace.EmailList";
    static props = [];

    setup() {
        this.mailbox = useState(useService("mailbox"));
    }

    formatDate(dateString) {
        if (!dateString) {
            return "";
        }
        return formatDateTime(deserializeDateTime(dateString), { format: "MMM d, HH:mm" });
    }

    onSelectMessage(ev) {
        const messageId = parseInt(ev.currentTarget.dataset.messageId, 10);
        this.mailbox.selectMessage(messageId);
    }

    onDragStart(ev) {
        const messageId = parseInt(ev.currentTarget.dataset.messageId, 10);
        ev.dataTransfer.setData("text/plain", messageId);
        ev.dataTransfer.effectAllowed = "move";
    }

    onSearchInput(ev) {
        this.mailbox.setSearchQuery(ev.target.value);
    }

    onToggleFilter(filter) {
        this.mailbox.setFilter(filter, !this.mailbox.filters[filter]);
    }

    onToggleImportant(ev) {
        ev.stopPropagation();
        const messageId = parseInt(ev.currentTarget.dataset.messageId, 10);
        this.mailbox.toggleImportant(messageId);
    }
}
