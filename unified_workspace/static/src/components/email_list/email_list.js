/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { ContextMenu } from "@unified_workspace/components/context_menu/context_menu";

/**
 * Email list component for the Unified Workspace.
 */
export class EmailList extends Component {
    static template = "unified_workspace.EmailList";
    static components = { ContextMenu };
    static props = [];

    setup() {
        this.mailbox = useState(useService("mailbox"));
        this.state = useState({
            contextMenu: null,
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
        this.mailbox.selectMessage(messageId);
    }

    onLoadMore() {
        this.mailbox.loadMoreMessages();
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

    /**
     * Open the right-click menu for a message.
     *
     * Right-click highlights the row, like Gmail, but does not mark it read.
     */
    onContextMenu(ev) {
        ev.preventDefault();
        const messageId = parseInt(ev.currentTarget.dataset.messageId, 10);
        this.mailbox.selectedMessageId = messageId;
        this.state.contextMenu = {
            x: ev.clientX,
            y: ev.clientY,
            messageId,
        };
    }

    closeContextMenu = () => {
        this.state.contextMenu = null;
    };

    getContextMenuItems(messageId) {
        const message = this.mailbox.messages.find((m) => m.id === messageId);
        if (!message) {
            return [];
        }
        const unread = message.state === "unread";
        return [
            {
                label: "Open",
                icon: "fa fa-envelope-open-o",
                action: () => this.mailbox.selectMessage(messageId),
            },
            {
                label: "Reply",
                icon: "fa fa-reply",
                shortcut: "R",
                action: () => this.mailbox.reply(messageId),
            },
            {
                label: "Reply all",
                icon: "fa fa-reply-all",
                shortcut: "A",
                action: () => this.mailbox.reply(messageId, "reply_all"),
            },
            {
                label: "Forward",
                icon: "fa fa-mail-forward",
                shortcut: "F",
                action: () => this.mailbox.forward(messageId),
            },
            { separator: true },
            {
                label: unread ? "Mark as read" : "Mark as unread",
                icon: unread ? "fa fa-envelope-open-o" : "fa fa-envelope-o",
                shortcut: "X",
                action: () => this.mailbox.toggleMessageRead(messageId),
            },
            {
                label: message.is_starred ? "Remove star" : "Add star",
                icon: message.is_starred ? "fa fa-star" : "fa fa-star-o",
                shortcut: "S",
                action: () => this.mailbox.toggleStarred(messageId),
            },
            {
                label: message.is_important ? "Mark as not important" : "Mark as important",
                icon: "fa fa-exclamation-circle",
                shortcut: "!",
                action: () => this.mailbox.toggleImportant(messageId),
            },
            { separator: true },
            {
                label: "Move to trash",
                icon: "fa fa-trash-o",
                shortcut: "#",
                danger: true,
                action: () => this.mailbox.moveToTrash(messageId),
            },
        ];
    }
}
