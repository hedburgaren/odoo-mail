/** @odoo-module **/

import { Component, onWillUnmount, useEffect, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { ContactCard } from "@unified_workspace/components/contact_card/contact_card";
import { AttachmentList } from "@unified_workspace/components/attachment_list/attachment_list";
import { ThreadPanel } from "@unified_workspace/components/thread_panel/thread_panel";

/**
 * Reading pane component for the Unified Workspace.
 */
export class ReadingPane extends Component {
    static template = "unified_workspace.ReadingPane";
    static components = { ContactCard, AttachmentList, ThreadPanel };
    static props = [];

    setup() {
        this.mailbox = useState(useService("mailbox"));
        this.state = useState({
            threadMessages: [],
            elapsedSeconds: 0,
        });
        this.timerInterval = null;
        useEffect(() => {
            this.loadThread();
            this._startTimerInterval();
            return () => this._stopTimerInterval();
        }, () => [this.mailbox.selectedMessageId]);
        onWillUnmount(() => this._stopTimerInterval());
    }

    async loadThread() {
        const messageId = this.mailbox.selectedMessageId;
        if (!messageId) {
            this.state.threadMessages = [];
            return;
        }
        this.state.threadMessages = await this.mailbox.getThread(messageId);
    }

    _startTimerInterval() {
        this._stopTimerInterval();
        this.state.elapsedSeconds = 0;
        if (this.message?.timer_active) {
            this.timerInterval = setInterval(() => {
                this.state.elapsedSeconds = this._computeActiveElapsed();
            }, 1000);
        }
    }

    _stopTimerInterval() {
        if (this.timerInterval) {
            clearInterval(this.timerInterval);
            this.timerInterval = null;
        }
    }

    _computeActiveElapsed() {
        if (!this.message?.timer_start) {
            return 0;
        }
        const start = new Date(this.message.timer_start).getTime();
        return Math.floor((Date.now() - start) / 1000);
    }

    get message() {
        return this.mailbox.messages.find((m) => m.id === this.mailbox.selectedMessageId);
    }

    formatDateTime(dateString) {
        if (!dateString) {
            return "";
        }
        return formatDateTime(deserializeDateTime(dateString), { format: "MMM d, yyyy HH:mm" });
    }

    onReply() {
        this.mailbox.reply(this.message.id);
    }

    onReplyAll() {
        this.mailbox.reply(this.message.id, "reply_all");
    }

    onForward() {
        this.mailbox.forward(this.message.id);
    }

    onToggleStar() {
        this.mailbox.toggleStarred(this.message.id);
    }

    onToggleImportant() {
        this.mailbox.toggleImportant(this.message.id);
    }

    onTrash() {
        this.mailbox.moveToTrash(this.message.id);
    }

    onCreateLead() {
        this.mailbox.createLead(this.message.id);
    }

    onCreateTask() {
        this.mailbox.createTask(this.message.id);
    }

    onBookMeeting() {
        this.mailbox.bookMeeting(this.message.id);
    }

    onLogActivity() {
        this.mailbox.logActivity(this.message.id);
    }

    onSaveAttachments() {
        this.mailbox.saveAttachmentsToRecord(this.message.id);
    }

    onSaveAttachmentsToDms() {
        this.mailbox.saveAttachmentsToDms(this.message.id);
    }

    onSaveToKnowledge() {
        this.mailbox.saveToKnowledge(this.message.id);
    }

    onViewContact() {
        if (this.message.partner_id) {
            this.mailbox.env.services.action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: this.message.partner_id[0],
                view_mode: "form",
                target: "current",
            });
        }
    }

    get hasCalendarEvent() {
        return Boolean(this.message?.calendar_event_id?.[0]);
    }

    get calendarEvent() {
        return this.message?.calendar_event || {};
    }

    get linkedRecord() {
        const message = this.message;
        if (!message) {
            return null;
        }
        return message.crm_lead_id || message.project_task_id || message.partner_id || null;
    }

    get isDraft() {
        return this.message?.state === "draft";
    }

    onEditDraft() {
        this.mailbox.openDraftComposer(this.message.id);
    }

    get hasTask() {
        return Boolean(this.message?.project_task_id?.[0]);
    }

    get totalElapsedSeconds() {
        const base = (this.message?.timer_duration || 0) * 3600;
        const active = this.message?.timer_active ? this.state.elapsedSeconds : 0;
        return Math.floor(base + active);
    }

    formatElapsed(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = seconds % 60;
        return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    }

    onTimerStart() {
        this.mailbox.timerStart(this.message.id);
    }

    onTimerStop() {
        this.mailbox.timerStop(this.message.id);
    }

    onLogTime() {
        this.mailbox.logTimeToTask(this.message.id);
    }

    formatEventDate(dateString) {
        if (!dateString) {
            return "";
        }
        return formatDateTime(deserializeDateTime(dateString), { format: "MMM d, yyyy HH:mm" });
    }

    onAcceptEvent() {
        this.mailbox.acceptEvent(this.message.id);
    }

    onTentativeEvent() {
        this.mailbox.tentativeEvent(this.message.id);
    }

    onDeclineEvent() {
        this.mailbox.declineEvent(this.message.id);
    }
}
