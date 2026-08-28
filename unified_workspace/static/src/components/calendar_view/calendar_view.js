/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

/**
 * Calendar agenda view shown inside the Unified Workspace.
 *
 * Displays today's events for the current user and links to the full calendar
 * app for scheduling.
 */
export class CalendarView extends Component {
    static template = "unified_workspace.CalendarView";
    static props = [];

    setup() {
        this.mailbox = useState(useService("mailbox"));
        onMounted(() => this.mailbox.loadAgenda());
    }

    formatDateTime(dateString) {
        if (!dateString) {
            return "";
        }
        return formatDateTime(deserializeDateTime(dateString), { format: "MMM d, HH:mm" });
    }

    onOpenEvent(eventId) {
        this.mailbox.env.services.action.doAction({
            type: "ir.actions.act_window",
            res_model: "calendar.event",
            res_id: eventId,
            view_mode: "form",
            target: "current",
        });
    }
}
