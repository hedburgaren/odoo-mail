/** @odoo-module **/

import { Component } from "@odoo/owl";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

/**
 * Show the conversation thread inside the reading pane.
 */
export class ThreadPanel extends Component {
    static template = "unified_workspace.ThreadPanel";
    static props = {
        threadMessages: { type: Array },
        selectedMessageId: { type: [Number, { value: null }], optional: true },
        onSelectMessage: { type: Function },
    };

    formatDate(dateString) {
        if (!dateString) {
            return "";
        }
        return formatDateTime(deserializeDateTime(dateString), { format: "MMM d, HH:mm" });
    }

    onSelect(messageId) {
        this.props.onSelectMessage(messageId);
    }
}
