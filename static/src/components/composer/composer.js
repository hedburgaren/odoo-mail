/** @odoo-module **/

import { Component, useEffect, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Wysiwyg } from "@html_editor/wysiwyg";
import { EmailTags } from "@unified_workspace/components/email_tags/email_tags";
import { AttachmentUploader } from "@unified_workspace/components/attachment_uploader/attachment_uploader";
import { ContactCreator } from "@unified_workspace/components/contact_creator/contact_creator";
import { RecordPicker } from "@unified_workspace/components/record_picker/record_picker";
import { ScheduleSender } from "@unified_workspace/components/schedule_sender/schedule_sender";

/**
 * Composer component for personal emails.
 *
 * Provides tokenized To/CC/BCC fields, an HTML editor and signature handling.
 * Uses the standard mail.compose.message transient model so that sent copies
 * are saved to the personal Inbox as read via the overridden _action_send_mail.
 */
export class Composer extends Component {
    static template = "unified_workspace.Composer";
    static components = { Wysiwyg, EmailTags, AttachmentUploader, ContactCreator, RecordPicker, ScheduleSender };
    static props = {
        close: { type: Function, optional: true },
        onClose: { type: Function, optional: true },
        defaultTo: { type: Array, optional: true },
        defaultCc: { type: Array, optional: true },
        defaultBcc: { type: Array, optional: true },
        defaultSubject: { type: String, optional: true },
        defaultBody: { type: String, optional: true },
        attachments: { type: Array, optional: true },
        draftId: { type: Number, optional: true },
        parentMailboxId: { type: Number, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mailbox = useService("mailbox");
        this.rootRef = useRef("root");
        this.state = useState({
            to: this.props.defaultTo || [],
            cc: this.props.defaultCc || [],
            bcc: this.props.defaultBcc || [],
            subject: this.props.defaultSubject || "",
            body: this.props.defaultBody || "",
            signatureType: "internal",
            attachments: this.props.attachments || [],
            draftId: this.props.draftId || null,
            templates: [],
            selectedTemplateId: null,
            showCcBcc: Boolean(this.props.defaultCc?.length || this.props.defaultBcc?.length),
        });
        this.editor = null;
        this._loadTemplates();
        useEffect(() => {
            const el = this.rootRef.el;
            if (!el) {
                return;
            }
            const handler = (ev) => {
                if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
                    ev.preventDefault();
                    this.onSend();
                }
            };
            el.addEventListener("keydown", handler);
            return () => el.removeEventListener("keydown", handler);
        });
    }

    async _loadTemplates() {
        const templates = await this.orm.searchRead(
            "mail.personal.template",
            [["is_default", "=", true]],
            ["id", "name", "subject", "body"]
        );
        this.state.templates = templates;
        if (templates.length && !this.props.defaultSubject && !this.props.defaultBody) {
            this._applyTemplate(templates[0]);
        }
    }

    _applyTemplate(template) {
        if (!template) {
            return;
        }
        this.state.selectedTemplateId = template.id;
        this.state.subject = template.subject || this.state.subject;
        this.state.body = template.body || this.state.body;
        if (this.editor) {
            this.editor.setContent(this.state.body);
        }
    }

    onSelectTemplate(ev) {
        const templateId = parseInt(ev.target.value, 10);
        const template = this.state.templates.find((t) => t.id === templateId);
        if (template) {
            this._applyTemplate(template);
        }
    }

    get editorConfig() {
        return {
            content: this.state.body,
            toolbar: true,
        };
    }

    onEditorLoad(editor) {
        this.editor = editor;
    }

    getBody() {
        let body = "";
        if (this.editor) {
            body = this.editor.getContent();
        }
        return body || this.state.body || "";
    }

    async onSend() {
        await this._doSend();
    }

    async onSendAndLog() {
        const target = await this._pickRecord();
        if (!target) {
            return;
        }
        await this._doSend({ logTo: target });
    }

    async onScheduleSend() {
        const scheduledDate = await this._pickScheduleDate();
        if (!scheduledDate) {
            return;
        }
        await this._doScheduleSend(scheduledDate);
    }

    async _doSend(options = {}) {
        try {
            const composerValues = await this._buildComposerValues(options);
            if (!composerValues) {
                return;
            }
            const composerId = await this._createComposer(composerValues);
            await this.orm.call("mail.compose.message", "action_send_mail", [[composerId]]);
            await this._cleanupAfterSend();
            this.notification.add("Email sent.", { type: "success" });
            this._close();
        } catch (error) {
            console.error(error);
            const message = error?.message || "Failed to send email.";
            this.notification.add(message, { type: "danger" });
        }
    }

    async _doScheduleSend(scheduledDate) {
        const composerValues = await this._buildComposerValues();
        if (!composerValues) {
            return;
        }
        const values = {
            user_id: this.env.services["mail.store"]?.self?.userId,
            subject: composerValues.subject,
            body: composerValues.body,
            email_cc: composerValues.email_cc,
            email_bcc: composerValues.email_bcc,
            partner_ids: composerValues.partner_ids,
            attachment_ids: [[6, 0, this.state.attachments.map((a) => a.id)]],
            scheduled_date: scheduledDate,
            log_to_model: composerValues.log_to_model || false,
            log_to_res_id: composerValues.log_to_res_id || 0,
        };
        if (this.state.draftId) {
            values.draft_id = this.state.draftId;
        } else if (this.props.parentMailboxId) {
            values.parent_mailbox_id = this.props.parentMailboxId;
        }
        await this.orm.create("mail.personal.scheduled.message", [values]);
        this.notification.add("Email scheduled.", { type: "success" });
        this._close();
    }

    async onSaveDraft() {
        const values = {
            draft_id: this.state.draftId,
            subject: this.state.subject,
            email_to: this.state.to.join(", "),
            email_cc: this.state.cc.join(", "),
            email_bcc: this.state.bcc.join(", "),
            body: this.getBody(),
            attachment_ids: [[6, 0, this.state.attachments.map((a) => a.id)]],
        };
        if (this.props.parentMailboxId && !this.state.draftId) {
            values.parent_id = this.props.parentMailboxId;
        }
        const draftId = await this.mailbox.saveDraft(values);
        this.state.draftId = draftId;
        this.notification.add("Draft saved.", { type: "success" });
    }

    onDiscard() {
        this._close();
    }

    _close() {
        if (this.props.close) {
            this.props.close();
        } else if (this.props.onClose) {
            this.props.onClose();
        }
    }

    async _buildComposerValues(options = {}) {
        const allEmails = [...new Set([
            ...this.state.to,
            ...this.state.cc,
            ...this.state.bcc,
        ])];
        const emailToPartner = await this._resolveAllPartners(allEmails);
        if (!emailToPartner) {
            return null;
        }
        const toPartnerIds = this.state.to.map((email) => emailToPartner[email]).filter(Boolean);
        const ccPartnerIds = this.state.cc.map((email) => emailToPartner[email]).filter(Boolean);
        const bccPartnerIds = this.state.bcc.map((email) => emailToPartner[email]).filter(Boolean);
        const allPartnerIds = [...new Set([...toPartnerIds, ...ccPartnerIds, ...bccPartnerIds])];

        let body = this.getBody();
        const signature = await this._getSignature();
        if (signature && !body.includes(signature)) {
            body += "<br/>" + signature;
        }

        const composerValues = {
            composition_mode: "personal_email",
            subject: this.state.subject,
            body: body,
            partner_ids: [[6, 0, allPartnerIds]],
            email_cc: this.state.cc.join(", "),
            email_bcc: this.state.bcc.join(", "),
        };
        if (this.state.draftId) {
            composerValues.personal_mailbox_id = this.state.draftId;
        } else if (this.props.parentMailboxId) {
            composerValues.personal_mailbox_id = this.props.parentMailboxId;
        }
        if (options.logTo) {
            composerValues.log_to_model = options.logTo.model;
            composerValues.log_to_res_id = options.logTo.res_id;
        }
        return composerValues;
    }

    async _createComposer(composerValues) {
        const composer = await this.orm.create("mail.compose.message", [composerValues]);
        const composerId = Array.isArray(composer) ? composer[0] : composer;
        if (this.state.attachments.length) {
            await this.orm.write("mail.compose.message", [composerId], {
                attachment_ids: [[6, 0, this.state.attachments.map((a) => a.id)]],
            });
        }
        return composerId;
    }

    async _cleanupAfterSend() {
        if (this.state.draftId) {
            await this.orm.unlink("mail.personal.mailbox", [this.state.draftId]);
        }
    }

    _pickRecord() {
        return new Promise((resolve) => {
            this.env.services.dialog.add(RecordPicker, { onSelect: resolve }, {
                title: "Log to record",
                size: "md",
            });
        });
    }

    _pickScheduleDate() {
        return new Promise((resolve) => {
            this.env.services.dialog.add(ScheduleSender, { onSchedule: resolve }, {
                title: "Schedule send",
                size: "sm",
            });
        });
    }

    async _getSignature() {
        const uid = this.env.services["mail.store"]?.self?.userId;
        if (!uid) {
            return "";
        }
        const users = await this.orm.searchRead(
            "res.users",
            [["id", "=", uid]],
            ["email_signature", "email_signature_external", "use_external_signature"]
        );
        if (!users.length) {
            return "";
        }
        const user = users[0];
        if (this.state.signatureType === "external") {
            return user.email_signature_external || user.email_signature || "";
        }
        return user.email_signature || "";
    }

    async _resolveAllPartners(emails) {
        const uniqueEmails = [...new Set(emails.map((e) => e.trim().toLowerCase()).filter(Boolean))];
        const emailToPartner = {};
        const unknownEmails = [];
        for (const email of uniqueEmails) {
            const partners = await this.orm.searchRead(
                "res.partner",
                [["email", "=ilike", email]],
                ["id"]
            );
            if (partners.length) {
                emailToPartner[email] = partners[0].id;
            } else {
                unknownEmails.push(email);
            }
        }
        for (const email of unknownEmails) {
            const partnerId = await this._createContactFromEmail(email);
            if (!partnerId) {
                this.notification.add(
                    `A contact is required to send to ${email}.`,
                    { type: "warning" }
                );
                return null;
            }
            emailToPartner[email] = partnerId;
        }
        return emailToPartner;
    }

    _createContactFromEmail(email) {
        return new Promise((resolve) => {
            this.env.services.dialog.add(ContactCreator, { email, onCreate: resolve }, {
                title: "Create Contact",
                size: "md",
            });
        });
    }

}
