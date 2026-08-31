/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Reactive } from "@web/core/utils/reactive";
import { markup } from "@odoo/owl";
import { Composer } from "@unified_workspace/components/composer/composer";

/**
 * Reactive mailbox state and RPC helpers for the Unified Workspace.
 */
export class MailboxService extends Reactive {
    constructor(env, services) {
        super();
        this.env = env;
        this.orm = services.orm;
        this.notification = services.notification;
        this.messages = [];
        this.folders = [];
        this.selectedMessageId = null;
        this.selectedFolderId = null;
        this.messagesPageSize = 50;
        this.messagesOffset = 0;
        this.hasMoreMessages = false;
        this.isLoadingMore = false;
        this.searchQuery = "";
        this.isLoading = false;
        this.filters = {
            unread: false,
            starred: false,
            attachments: false,
            important: false,
        };
        this.agenda = [];
        this.channels = [];
        this.inboxCount = 0;
        this.activePanel = "mail";
        this.groupInboxMessages = [];
        this.selectedGroupMessageId = null;
        this.groupInboxLoading = false;
    }

    setActivePanel(panel) {
        this.activePanel = panel;
    }

    _currentPartnerId() {
        return this.env.services["mail.store"]?.self?.id;
    }

    async loadInboxCount() {
        this.inboxCount = await this.orm.call("mail.personal.mailbox", "get_discuss_inbox_count", []);
    }

    async loadChannels() {
        const partnerId = this._currentPartnerId();
        if (!partnerId) {
            this.channels = [];
            return;
        }
        const members = await this.orm.searchRead(
            "discuss.channel.member",
            [["partner_id", "=", partnerId]],
            ["channel_id", "message_unread_counter"]
        );
        const channelIds = members.map((m) => m.channel_id[0]).filter(Boolean);
        if (!channelIds.length) {
            this.channels = [];
            return;
        }
        const channels = await this.orm.read("discuss.channel", channelIds, ["id", "name", "channel_type"]);
        const unreadByChannel = Object.fromEntries(members.map((m) => [m.channel_id[0], m.message_unread_counter || 0]));
        this.channels = channels.map((c) => ({
            ...c,
            unread_count: unreadByChannel[c.id] || 0,
        }));
    }

    async loadFolders() {
        this.folders = await this.orm.searchRead(
            "mail.personal.folder",
            [],
            ["id", "name", "folder_type", "sequence", "message_count", "parent_id"],
            { order: "sequence, name" }
        );
        if (!this.selectedFolderId && this.folders.length) {
            const inbox = this.folders.find((f) => f.folder_type === "inbox");
            this.selectedFolderId = inbox ? inbox.id : this.folders[0].id;
        }
    }

    async loadAgenda() {
        this.agenda = await this.orm.call("mail.personal.mailbox", "get_today_agenda", []);
    }

    _buildMessageDomain() {
        const domain = [];
        if (this.selectedFolderId && this.selectedFolderId !== "all") {
            domain.push(["folder_id", "=", this.selectedFolderId]);
        }
        if (this.searchQuery) {
            if (domain.length) {
                domain.unshift("&");
            }
            domain.push("|", "|", "|");
            domain.push(["name", "ilike", this.searchQuery]);
            domain.push(["email_from", "ilike", this.searchQuery]);
            domain.push(["email_to", "ilike", this.searchQuery]);
            domain.push(["body_text", "ilike", this.searchQuery]);
        }
        if (this.filters.unread) {
            if (domain.length) {
                domain.unshift("&");
            }
            domain.push(["state", "=", "unread"]);
        }
        if (this.filters.starred) {
            if (domain.length) {
                domain.unshift("&");
            }
            domain.push(["is_starred", "=", true]);
        }
        if (this.filters.attachments) {
            if (domain.length) {
                domain.unshift("&");
            }
            domain.push(["attachment_ids", "!=", false]);
        }
        if (this.filters.important) {
            if (domain.length) {
                domain.unshift("&");
            }
            domain.push(["is_important", "=", true]);
        }
        return domain;
    }

    async loadMessages() {
        this.isLoading = true;
        this.messagesOffset = 0;
        try {
            const messages = await this._fetchMessagePage(0);
            this.hasMoreMessages = messages.length === this.messagesPageSize;
            this.messagesOffset = messages.length;
            await this._hydrateMessages(messages);
            this.messages = messages;
        } finally {
            this.isLoading = false;
        }
    }

    async loadMoreMessages() {
        if (this.isLoading || this.isLoadingMore || !this.hasMoreMessages) {
            return;
        }
        this.isLoadingMore = true;
        try {
            const messages = await this._fetchMessagePage(this.messagesOffset);
            this.hasMoreMessages = messages.length === this.messagesPageSize;
            this.messagesOffset += messages.length;
            await this._hydrateMessages(messages);
            this.messages = [...this.messages, ...messages];
        } finally {
            this.isLoadingMore = false;
        }
    }

    /**
     * Fetch one page of message headers.
     *
     * The HTML body is deliberately left out: it is by far the heaviest field
     * (hundreds of megabytes across a full mailbox) and only the opened message
     * needs it. It is fetched on demand in _ensureMessageBody().
     */
    async _fetchMessagePage(offset) {
        return this.orm.searchRead(
            "mail.personal.mailbox",
            this._buildMessageDomain(),
            [
                "id",
                "name",
                "email_from",
                "email_to",
                "email_cc",
                "date",
                "state",
                "is_starred",
                "is_important",
                "body_text",
                "folder_id",
                "partner_id",
                "attachment_ids",
                "crm_lead_id",
                "project_task_id",
                "calendar_event_id",
                "calendar_rsvp_state",
                "timer_start",
                "timer_duration",
                "timer_active",
            ],
            { order: "date DESC, id DESC", limit: this.messagesPageSize, offset }
        );
    }

    async _hydrateMessages(messages) {
        const attachmentIds = [...new Set(messages.flatMap((m) => m.attachment_ids || []))].filter(Boolean);
        if (attachmentIds.length) {
            // Read metadata only; fetch content on demand via /web/content/<id>.
            const BATCH = 100;
            const attachments = [];
            for (let i = 0; i < attachmentIds.length; i += BATCH) {
                const batch = attachmentIds.slice(i, i + BATCH);
                const batchAttachments = await this.orm.read("ir.attachment", batch, ["id", "name", "mimetype"]);
                attachments.push(...batchAttachments);
            }
            const attachmentById = Object.fromEntries(attachments.map((a) => [a.id, a]));
            for (const message of messages) {
                message.attachment_ids = (message.attachment_ids || []).map((id) => attachmentById[id]).filter(Boolean);
            }
        }
        const eventIds = messages.map((m) => m.calendar_event_id?.[0]).filter(Boolean);
        if (eventIds.length) {
            const events = await this.orm.read(
                "calendar.event",
                [...new Set(eventIds)],
                ["id", "name", "start", "stop", "location", "attendee_ids", "partner_ids"]
            );
            const eventById = Object.fromEntries(events.map((e) => [e.id, e]));
            const attendeeIds = events.flatMap((e) => e.attendee_ids);
            let attendeeById = {};
            if (attendeeIds.length) {
                const attendees = await this.orm.read(
                    "calendar.attendee",
                    attendeeIds,
                    ["id", "partner_id", "state"]
                );
                attendeeById = Object.fromEntries(attendees.map((a) => [a.id, a]));
            }
            const userPartnerId = this._currentPartnerId();
            for (const message of messages) {
                const event = eventById[message.calendar_event_id?.[0]];
                if (event) {
                    message.calendar_event = event;
                    const myAttendee = event.attendee_ids
                        .map((id) => attendeeById[id])
                        .find((a) => a?.partner_id?.[0] === userPartnerId);
                    message.calendar_my_rsvp = myAttendee?.state || message.calendar_rsvp_state || "needsAction";
                }
            }
        }
    }

    /** Load the HTML body of a single message, once, when it is opened. */
    async _ensureMessageBody(messageId) {
        const message = this.messages.find((m) => m.id === messageId);
        if (!message || message.body !== undefined) {
            return;
        }
        message.body = markup("");
        const records = await this.orm.read("mail.personal.mailbox", [messageId], ["body"]);
        message.body = markup(records[0]?.body || "");
    }

    selectMessage(messageId) {
        this.selectedMessageId = messageId;
        const message = this.messages.find((m) => m.id === messageId);
        if (message && message.state === "unread") {
            this.markAsRead(messageId);
        }
        this._ensureMessageBody(messageId);
    }

    selectFolder(folderId) {
        this.selectedFolderId = folderId;
        this.selectedMessageId = null;
        this.loadMessages();
    }

    setSearchQuery(query) {
        this.searchQuery = query;
        this.loadMessages();
    }

    async markAsRead(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_mark_read", [[messageId]]);
        const message = this.messages.find((m) => m.id === messageId);
        if (message) {
            message.state = "read";
        }
    }

    async markAsUnread(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_mark_unread", [[messageId]]);
        const message = this.messages.find((m) => m.id === messageId);
        if (message) {
            message.state = "unread";
        }
    }

    async toggleStarred(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_toggle_starred", [[messageId]]);
        const message = this.messages.find((m) => m.id === messageId);
        if (message) {
            message.is_starred = !message.is_starred;
        }
    }

    async toggleImportant(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_toggle_important", [[messageId]]);
        const message = this.messages.find((m) => m.id === messageId);
        if (message) {
            message.is_important = !message.is_important;
        }
    }

    async moveToTrash(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_move_to_trash", [[messageId]]);
        this.messages = this.messages.filter((m) => m.id !== messageId);
        this.selectedMessageId = null;
    }

    selectNextMessage() {
        const messages = this.messages;
        if (!messages.length) {
            return;
        }
        const currentIndex = messages.findIndex((m) => m.id === this.selectedMessageId);
        const nextIndex = currentIndex < 0 ? 0 : Math.min(currentIndex + 1, messages.length - 1);
        this.selectMessage(messages[nextIndex].id);
    }

    selectPreviousMessage() {
        const messages = this.messages;
        if (!messages.length) {
            return;
        }
        const currentIndex = messages.findIndex((m) => m.id === this.selectedMessageId);
        const prevIndex = currentIndex <= 0 ? 0 : currentIndex - 1;
        this.selectMessage(messages[prevIndex].id);
    }

    openSelectedMessage() {
        if (!this.selectedMessageId && this.messages.length) {
            this.selectMessage(this.messages[0].id);
        }
    }

    async toggleMessageRead(messageId) {
        const message = this.messages.find((m) => m.id === messageId);
        if (!message) {
            return;
        }
        if (message.state === "unread") {
            await this.markAsRead(messageId);
        } else {
            await this.markAsUnread(messageId);
        }
    }

    selectFolderByType(folderType) {
        const folder = this.folders.find((f) => f.folder_type === folderType);
        if (folder) {
            this.selectFolder(folder.id);
        }
    }

    async createLead(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_create_lead", [[messageId]]);
        this.env.services.action.doAction(action);
    }

    async createTask(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_create_task", [[messageId]]);
        this.env.services.action.doAction(action);
    }

    async bookMeeting(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_book_meeting", [[messageId]]);
        this.env.services.action.doAction(action);
    }

    async reply(messageId, mode = "reply") {
        const message = await this._getMessage(messageId);
        if (!message) {
            return;
        }
        const prefix = mode === "forward" ? "Fwd:" : "Re:";
        const replyTo = message.reply_to || message.email_from;
        const userEmail = this.env.services["mail.store"]?.self?.email?.toLowerCase() || "";
        const isSelf = (email) => email.toLowerCase() === userEmail;

        let defaultTo = [];
        let defaultCc = [];
        let defaultBcc = [];

        if (mode === "reply") {
            defaultTo = this._extractEmails(replyTo);
        } else if (mode === "reply_all") {
            defaultTo = this._extractEmails(message.email_from).filter((e) => !isSelf(e));
            defaultCc = this._extractEmails(`${message.email_to || ""}, ${message.email_cc || ""}`)
                .filter((e) => !isSelf(e) && !defaultTo.includes(e));
            defaultBcc = this._extractEmails(message.email_bcc || "").filter((e) => !isSelf(e));
        }

        let defaultBody = "";
        if (mode !== "forward") {
            defaultBody = await this.orm.call("mail.personal.mailbox", "action_get_reply_body", [[messageId]]);
        }

        this.openComposer({
            defaultTo,
            defaultCc,
            defaultBcc,
            defaultSubject: `${prefix} ${message.name || ""}`,
            defaultBody,
            attachments: mode === "forward" ? (message.attachment_ids || []) : [],
            parentMailboxId: messageId,
        });
    }

    async forward(messageId) {
        await this.reply(messageId, "forward");
    }

    async saveDraft(values) {
        return this.orm.call("mail.personal.mailbox", "save_draft", [values]);
    }

    async openDraftComposer(messageId) {
        const message = await this.orm.read(
            "mail.personal.mailbox",
            [messageId],
            ["name", "email_from", "email_to", "email_cc", "email_bcc", "body", "attachment_ids", "parent_id", "folder_id"]
        ).then((records) => records[0] || null);
        if (!message) {
            return;
        }
        let attachments = [];
        if (message.attachment_ids?.length) {
            attachments = await this.orm.read("ir.attachment", message.attachment_ids, ["id", "name", "mimetype"]);
        }
        this.openComposer({
            draftId: messageId,
            defaultTo: this._extractEmails(message.email_to),
            defaultCc: this._extractEmails(message.email_cc),
            defaultBcc: this._extractEmails(message.email_bcc),
            defaultSubject: message.name || "",
            defaultBody: message.body || "",
            attachments,
            parentMailboxId: message.parent_id?.[0] || null,
        });
    }

    async openComposer(props = {}) {
        this.env.services.dialog.add(Composer, props, {
            size: "xl",
        });
    }

    async _getMessage(messageId) {
        return this.orm.read(
            "mail.personal.mailbox",
            [messageId],
            ["name", "email_from", "email_to", "email_cc", "email_bcc", "reply_to", "body", "attachment_ids"]
        ).then((records) => records[0] || null);
    }

    _extractEmails(emailString) {
        if (!emailString) {
            return [];
        }
        return emailString.split(/[,;\s]+/).map((e) => e.trim()).filter((e) => e.includes("@"));
    }

    async openDiscuss() {
        this.env.services.action.doAction("mail.action_discuss");
    }

    async openChannel(channelId) {
        this.env.services.action.doAction("mail.action_discuss", {
            additionalContext: { active_id: channelId },
        });
    }

    async openCalendar() {
        this.setActivePanel("calendar");
    }

    async openGroupInbox() {
        this.setActivePanel("groupInbox");
        await this.loadGroupInboxMessages();
    }

    async loadGroupInboxMessages() {
        this.groupInboxLoading = true;
        const messages = await this.orm.call(
            "mail.personal.mailbox",
            "get_discuss_inbox_messages",
            []
        );
        this.groupInboxMessages = messages.map((m) => ({
            ...m,
            body: markup(m.body || ""),
        }));
        this.groupInboxLoading = false;
    }

    selectGroupInboxMessage(messageId) {
        this.selectedGroupMessageId = messageId;
    }

    get selectedGroupMessage() {
        return this.groupInboxMessages.find((m) => m.id === this.selectedGroupMessageId) || null;
    }

    async markGroupInboxMessageRead(messageId) {
        await this.orm.call("mail.message", "set_message_done", [[messageId]]);
        this.groupInboxMessages = this.groupInboxMessages.filter((m) => m.id !== messageId);
        if (this.selectedGroupMessageId === messageId) {
            this.selectedGroupMessageId = null;
        }
        this.loadInboxCount();
    }

    async openGroupInboxMessageRecord() {
        const message = this.selectedGroupMessage;
        if (!message || !message.model || !message.res_id) {
            return;
        }
        this.env.services.action.doAction({
            type: "ir.actions.act_window",
            res_model: message.model,
            res_id: message.res_id,
            view_mode: "form",
            views: [[false, "form"]],
            target: "current",
        });
    }

    _patchLocalRsvp(messageId, state) {
        const message = this.messages.find((m) => m.id === messageId);
        if (message) {
            message.calendar_my_rsvp = state;
            message.calendar_rsvp_state = state;
        }
    }

    async acceptEvent(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_accept_event", [[messageId]]);
        this._patchLocalRsvp(messageId, "accepted");
        await this.loadMessages();
    }

    async tentativeEvent(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_tentative_event", [[messageId]]);
        this._patchLocalRsvp(messageId, "tentative");
        await this.loadMessages();
    }

    async declineEvent(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_decline_event", [[messageId]]);
        this._patchLocalRsvp(messageId, "declined");
        await this.loadMessages();
    }

    setFilter(key, value) {
        if (key in this.filters) {
            this.filters[key] = value;
            this.loadMessages();
        }
    }

    async getThread(messageId) {
        return this.orm.call("mail.personal.mailbox", "action_get_thread", [[messageId]]);
    }

    async logActivity(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_log_activity", [[messageId]]);
        this.env.services.action.doAction(action);
    }

    async saveAttachmentsToRecord(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_save_attachments_to_record", [[messageId]]);
        if (action) {
            this.env.services.action.doAction(action);
        }
    }

    async saveAttachmentsToDms(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_save_attachments_to_dms", [[messageId]]);
        if (action) {
            this.env.services.action.doAction(action);
        }
    }

    async saveToKnowledge(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_save_to_knowledge", [[messageId]]);
        if (action) {
            this.env.services.action.doAction(action);
        }
    }

    async timerStart(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_timer_start", [[messageId]]);
        const message = this.messages.find((m) => m.id === messageId);
        if (message) {
            message.timer_active = true;
            message.timer_start = new Date().toISOString();
        }
    }

    async timerStop(messageId) {
        await this.orm.call("mail.personal.mailbox", "action_timer_stop", [[messageId]]);
        const message = this.messages.find((m) => m.id === messageId);
        if (message) {
            message.timer_active = false;
            message.timer_start = false;
        }
        await this.loadMessages();
    }

    async logTimeToTask(messageId) {
        const action = await this.orm.call("mail.personal.mailbox", "action_log_time_to_task", [[messageId]]);
        if (action) {
            this.env.services.action.doAction(action);
        }
        await this.loadMessages();
    }
}

export const mailboxService = {
    dependencies: ["orm", "notification", "action", "dialog"],
    start(env, services) {
        return new MailboxService(env, services);
    },
};

registry.category("services").add("mailbox", mailboxService);
