/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Sidebar } from "@unified_workspace/components/sidebar/sidebar";
import { EmailList } from "@unified_workspace/components/email_list/email_list";
import { ReadingPane } from "@unified_workspace/components/reading_pane/reading_pane";
import { CalendarPanel } from "@unified_workspace/components/calendar_panel/calendar_panel";
import { CalendarView } from "@unified_workspace/components/calendar_view/calendar_view";
import { GroupInboxPanel } from "@unified_workspace/components/group_inbox_panel/group_inbox_panel";
import { PipelineOverlay } from "@unified_workspace/components/pipeline_overlay/pipeline_overlay";

/**
 * Main Unified Workspace client action.
 *
 * Replaces the traditional Discuss landing with a three-column communication
 * hub: navigation sidebar, email list and reading pane. Existing Discuss chat
 * is reachable through the Chat entry in the sidebar.
 */
export class Workspace extends Component {
    static template = "unified_workspace.Workspace";
    static components = { Sidebar, EmailList, ReadingPane, CalendarPanel, CalendarView, GroupInboxPanel, PipelineOverlay };
    static props = ["*"];

    setup() {
        this.mailbox = useState(useService("mailbox"));
        this.rootRef = useRef("root");
        this.state = useState({
            goPending: false,
            showShortcuts: false,
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
        // Never swallow browser and OS combinations (Ctrl/Cmd/Alt). Gmail does
        // the same: Ctrl+F must open find, not forward the selected mail.
        if (ev.ctrlKey || ev.metaKey || ev.altKey) {
            return;
        }

        const key = ev.key.toLowerCase();

        // Escape and ? stay available even while the help dialog is open.
        if (key === "escape") {
            ev.preventDefault();
            if (this.state.showShortcuts) {
                this.state.showShortcuts = false;
            } else if (this.mailbox.selectedMessageId) {
                this._backToList();
            }
            return;
        }
        if (key === "?") {
            ev.preventDefault();
            this.state.showShortcuts = !this.state.showShortcuts;
            return;
        }

        // Do not fire other shortcuts while the help dialog is open.
        if (this.state.showShortcuts) {
            return;
        }
        // Do not fire shortcuts while a dialog/modal is open.
        if (document.querySelector(".modal.show, .modal[role='dialog']")) {
            return;
        }

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
        } else if (key === "a" && messageId) {
            ev.preventDefault();
            this.mailbox.reply(messageId, "reply_all");
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
        } else if (key === "o" || key === "enter") {
            ev.preventDefault();
            this.mailbox.openSelectedMessage();
        } else if (key === "u") {
            ev.preventDefault();
            this._backToList();
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
        // The sidebar switches to the mail panel before selecting a folder;
        // the shortcut has to do the same, or G+I from Calendar/Group Inbox
        // changes the folder behind the visible panel.
        this.mailbox.setActivePanel("mail");
        const map = {
            i: () => this.mailbox.selectFolderByType("inbox"),
            a: () => this.mailbox.selectFolder("all"),
            s: () => this.mailbox.setFilter("starred", !this.mailbox.filters.starred),
            u: () => this.mailbox.setFilter("unread", !this.mailbox.filters.unread),
        };
        const action = map[key];
        if (action) {
            action();
        }
    }

    _backToList() {
        this.mailbox.selectedMessageId = null;
        const list = document.querySelector(".o-unified-email-list-items");
        if (list) {
            list.focus();
        }
    }

    _focusSearch() {
        const input = document.querySelector(".o-unified-email-list-search input");
        if (input) {
            input.focus();
        }
    }

    closeShortcuts = () => {
        this.state.showShortcuts = false;
    };

    onDialogClick = (ev) => {
        ev.stopPropagation();
    };

    get shortcutGroups() {
        return [
            {
                title: "Navigation",
                items: [
                    { keys: "J / K", label: "Next / previous message" },
                    { keys: "Enter or O", label: "Open selected message" },
                    { keys: "U", label: "Back to the list" },
                    { keys: "G then I", label: "Go to Inbox" },
                    { keys: "G then A", label: "Go to All Mail" },
                    { keys: "/", label: "Search mail" },
                ],
            },
            {
                title: "Actions",
                items: [
                    { keys: "C or E", label: "Compose" },
                    { keys: "R", label: "Reply" },
                    { keys: "A", label: "Reply all" },
                    { keys: "F", label: "Forward" },
                    { keys: "S", label: "Star / unstar" },
                    { keys: "!", label: "Mark important" },
                    { keys: "X", label: "Mark read / unread" },
                    { keys: "#", label: "Move to trash" },
                ],
            },
            {
                title: "View",
                items: [
                    { keys: "G then S", label: "Toggle starred filter" },
                    { keys: "G then U", label: "Toggle unread filter" },
                    { keys: "?", label: "Show this help" },
                    { keys: "Esc", label: "Close dialog or deselect" },
                ],
            },
        ];
    }
}

registry.category("actions").add("unified_workspace.workspace", Workspace);
