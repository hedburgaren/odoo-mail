/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Sidebar } from "@unified_workspace/components/sidebar/sidebar";
import { EmailList } from "@unified_workspace/components/email_list/email_list";
import { ReadingPane } from "@unified_workspace/components/reading_pane/reading_pane";
import { CalendarPanel } from "@unified_workspace/components/calendar_panel/calendar_panel";
import { GroupInboxPanel } from "@unified_workspace/components/group_inbox_panel/group_inbox_panel";

/**
 * Main Unified Workspace client action.
 *
 * Replaces the traditional Discuss landing with a three-column communication
 * hub: navigation sidebar, email list and reading pane. Existing Discuss chat
 * is reachable through the Chat entry in the sidebar.
 */
export class Workspace extends Component {
    static template = "unified_workspace.Workspace";
    static components = { Sidebar, EmailList, ReadingPane, CalendarPanel, GroupInboxPanel };
    static props = ["*"];

    setup() {
        this.mailbox = useState(useService("mailbox"));
        this.rootRef = useRef("root");
        this.state = useState({
            goPending: false,
        });
        onWillStart(async () => {
            await this.mailbox.loadFolders();
            await this.mailbox.loadMessages();
        });
        onMounted(() => {
            this.rootRef.el?.focus();
            this.rootRef.el?.addEventListener("keydown", this.onKeydown.bind(this));
        });
    }

    /**
     * Handle Gmail/Outlook-style keyboard shortcuts.
     *
     * Shortcuts are ignored when the user is typing in an editable field
     * (input, textarea, contenteditable) or when a modal/dialog is open.
     */
    onKeydown(ev) {
        const target = ev.target;
        const tag = target.tagName?.toLowerCase();
        const isEditable =
            target.isContentEditable ||
            tag === "input" ||
            tag === "textarea" ||
            tag === "select";
        if (isEditable) {
            return;
        }
        // Do not fire shortcuts while a dialog/modal is open.
        if (document.querySelector(".modal.show, .modal[role='dialog']")) {
            return;
        }

        const key = ev.key.toLowerCase();
        const messageId = this.mailbox.selectedMessageId;

        if (this.state.goPending) {
            ev.preventDefault();
            this._handleGoShortcut(key);
            return;
        }

        if (key === "g") {
            ev.preventDefault();
            this.state.goPending = true;
            setTimeout(() => {
                this.state.goPending = false;
            }, 1000);
            return;
        }

        if (key === "c" || key === "e") {
            ev.preventDefault();
            this.mailbox.openComposer();
        } else if (key === "r" && messageId) {
            ev.preventDefault();
            this.mailbox.reply(messageId);
        } else if (key === "f" && messageId) {
            ev.preventDefault();
            this.mailbox.forward(messageId);
        } else if (key === "#" && messageId) {
            ev.preventDefault();
            this.mailbox.moveToTrash(messageId);
        } else if (key === "s" && messageId) {
            ev.preventDefault();
            this.mailbox.toggleStarred(messageId);
        } else if (key === "!" && messageId) {
            ev.preventDefault();
            this.mailbox.toggleImportant(messageId);
        } else if (key === "j") {
            ev.preventDefault();
            this.mailbox.selectNextMessage();
        } else if (key === "k") {
            ev.preventDefault();
            this.mailbox.selectPreviousMessage();
        } else if (key === "enter") {
            ev.preventDefault();
            this.mailbox.openSelectedMessage();
        } else if (key === "x" && messageId) {
            ev.preventDefault();
            this.mailbox.toggleMessageRead(messageId);
        } else if (key === "/") {
            ev.preventDefault();
            this._focusSearch();
        }
    }

    _handleGoShortcut(key) {
        this.state.goPending = false;
        const map = {
            i: "inbox",
        };
        const folderType = map[key];
        if (folderType) {
            this.mailbox.selectFolderByType(folderType);
        }
    }

    _focusSearch() {
        const input = document.querySelector(".o-unified-email-list-search input");
        if (input) {
            input.focus();
        }
    }
}

registry.category("actions").add("unified_workspace.workspace", Workspace);
