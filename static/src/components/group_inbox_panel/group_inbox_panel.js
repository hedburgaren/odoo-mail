/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

/**
 * Inline Group Inbox panel for the Unified Workspace.
 *
 * Displays the current user's Discuss inbox notifications without leaving the
 * workspace. Messages can be marked as read and the related record can be
 * opened when one exists.
 */
export class GroupInboxPanel extends Component {
    static template = "unified_workspace.GroupInboxPanel";
    static props = [];

    setup() {
        this.mailbox = useState(useService("mailbox"));
        onMounted(() => {
            this.mailbox.loadGroupInboxMessages();
        });
    }

    formatDate(dateString) {
        if (!dateString) {
            return "";
        }
        return formatDateTime(deserializeDateTime(dateString), { format: "MMM d, HH:mm" });
    }

    onSelectMessage(ev) {
        const messageId = parseInt(ev.currentTarget.dataset.messageId, 10);
        this.mailbox.selectGroupInboxMessage(messageId);
    }

    onMarkAsRead(ev) {
        ev.stopPropagation();
        const messageId = parseInt(ev.currentTarget.dataset.messageId, 10);
        this.mailbox.markGroupInboxMessageRead(messageId);
    }

    onOpenRecord() {
        this.mailbox.openGroupInboxMessageRecord();
    }
}
