/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";

/**
 * Navigation sidebar for the Unified Workspace.
 */
export class Sidebar extends Component {
    static template = "unified_workspace.Sidebar";
    static props = [];

    setup() {
        this.mailbox = useState(useService("mailbox"));
        onMounted(() => {
            this.mailbox.loadAgenda();
            this.mailbox.loadInboxCount();
            this.mailbox.loadChannels();
        });
    }

    get channels() {
        return this.mailbox.channels;
    }

    formatTime(dateString) {
        if (!dateString) {
            return "";
        }
        return formatDateTime(deserializeDateTime(dateString), { format: "HH:mm" });
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

    get folders() {
        return this.mailbox.folders;
    }

    get visibleFolders() {
        return this.mailbox.folders.filter((f) => !f.folder_type || f.folder_type === "custom");
    }

    get allFoldersItem() {
        return {
            id: "all",
            name: "All Mail",
            folder_type: "all",
            message_count: 0,
        };
    }

    getFolderIcon(folderType) {
        const icons = {
            inbox: "fa fa-inbox",
            custom: "fa fa-folder-o",
        };
        return icons[folderType] || icons.custom;
    }

    get personalInboxFolder() {
        return this.mailbox.folders.find((f) => f.folder_type === "inbox");
    }

    onSelectFolder(folderId) {
        this.mailbox.setActivePanel("mail");
        this.mailbox.selectFolder(folderId);
    }

    onCompose() {
        this.mailbox.openComposer();
    }

    onOpenGroupInbox() {
        this.mailbox.openGroupInbox();
    }

    onOpenCalendar() {
        this.mailbox.openCalendar();
    }

    onOpenChannel(channelId) {
        this.mailbox.openChannel(channelId);
    }

    getChannelIcon(channelType) {
        if (channelType === "chat") {
            return "fa fa-user";
        }
        return "fa fa-hashtag";
    }
}
