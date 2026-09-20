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
 * Provides tokenized To/CC/BCC fields, an HTML editor and a signature
 * selector. Uses the standard mail.compose.message transient model, whose
 * overridden _action_send_mail sends the email, inserts the signature and
 * marks the original message replied or forwarded. No copy is saved to the
 * personal Inbox: Gmail keeps the outgoing mail in its own Sent folder
 * (Chrille 2026-09-07).
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
            signatureType: "auto",
            attachments: this.props.attachments || [],
            draftId: this.props.draftId || null,
            templates: [],
            selectedTemplateId: null,
            showCcBcc: Boolean(this.props.defaultCc?.length || this.props.defaultBcc?.length),
            isSending: false,
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
        // All templates the user can see (own plus shared), the default first.
        const templates = await this.orm.searchRead(
            "mail.personal.template",
            [],
            ["id", "name", "subject", "body", "is_default"],
            { order: "is_default DESC, name" }
        );
        this.state.templates = templates;
        if (templates.length && !this.props.defaultSubject && !this.props.defaultBody) {
            await this._applyTemplate(templates[0]);
        }
    }

    async _applyTemplate(template) {
        if (!template) {
            return;
        }
        this.state.selectedTemplateId = template.id;
        // Placeholders resolve server-side against the first recipient so the
        // whitelist stays in one place and the partner data is never trusted
        // raw in the browser.
        const partnerId = await this._resolveRecipientPartnerId();
        const data = await this.orm.call(
            "mail.personal.template",
            "action_use_template",
            [[template.id]],
            { partner_id: partnerId || false }
        );
        this.state.subject = data.subject || this.state.subject;
        this.state.body = this._mergeTemplateBody(data.body);
        this._setEditorContent(this.state.body);
    }

    _setEditorContent(html) {
        // html_editor (Odoo 18) har ingen setContent. Så här gör fältet
        // själv: skriv editable och lägg ett historiksteg, annars kan
        // användaren inte ångra och ändringen syns inte i editorn.
        if (!this.editor || !this.editor.editable) {
            return;
        }
        this.editor.editable.innerHTML = html || "";
        this.editor.shared?.history?.addStep();
    }

    _mergeTemplateBody(templateBody) {
        const current = this.state.body || "";
        if (!templateBody) {
            return current;
        }
        // I ett svar ligger citatet redan i bodyn. Mallen läggs ovanför
        // citatet i stället för att ersätta hela texten, annars försvinner
        // det citerade så fort användaren byter mall.
        for (const marker of ['<p class="uw_quote_header"', '<div class="uw_quote"']) {
            const idx = current.indexOf(marker);
            if (idx >= 0) {
                return templateBody + current.slice(idx);
            }
        }
        return templateBody;
    }

    async onRecipientsChange(emails) {
        this.state.to = emails;
        await this._renderPendingPlaceholders();
    }

    async _renderPendingPlaceholders() {
        // Mallen kan ha applicerats innan mottagaren fanns, och då står
        // {{ partner.* }} kvar i texten. Här fylls bara de platshållare som
        // är kvar i; allt användaren själv skrivit lämnas orört.
        const body = this.getBody();
        if (!(this.state.subject || "").includes("{{") && !body.includes("{{")) {
            return;
        }
        const partnerId = await this._resolveRecipientPartnerId();
        if (!partnerId) {
            return;
        }
        const data = await this.orm.call(
            "mail.personal.template",
            "render_for_partner",
            [],
            { subject: this.state.subject || "", body: body, partner_id: partnerId }
        );
        this.state.subject = data.subject;
        this.state.body = data.body;
        this._setEditorContent(this.state.body);
    }

    async _resolveRecipientPartnerId() {
        const email = (this.state.to || [])
            .map((e) => e.trim().toLowerCase())
            .find(Boolean);
        if (!email) {
            return false;
        }
        // email_normalized, inte =ilike: i ilike är _ och % jokertecken, så
        // anna_b@firma.se matchade även annaxb@firma.se och fel kontakts
        // uppgifter hamnade i mejlet.
        const partners = await this.orm.searchRead(
            "res.partner",
            [["email_normalized", "=", email]],
            ["id"],
            { limit: 1 }
        );
        return partners.length ? partners[0].id : false;
    }

    async onSelectTemplate(ev) {
        const templateId = parseInt(ev.target.value, 10);
        const template = this.state.templates.find((t) => t.id === templateId);
        if (template) {
            await this._applyTemplate(template);
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
        if (this.state.isSending) {
            return;
        }
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
        this.state.isSending = true;
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
            console.error("[Composer] _doSend error", error);
            const message = error?.message || "Failed to send email.";
            this.notification.add(message, { type: "danger" });
        } finally {
            this.state.isSending = false;
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
        }
        if (this.props.parentMailboxId) {
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
        if (this.props.parentMailboxId) {
            values.parent_id = this.props.parentMailboxId;
        }
        const draftId = await this.mailbox.saveDraft(values);
        this.state.draftId = draftId;
        await this.mailbox.loadMessages();
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
        // Nycklarna i emailToPartner är gemener: slå upp likadant, annars
        // tappas mottagare med versaler i adressen (Magdalena-buggen 2026-09-07).
        const key = (email) => email.trim().toLowerCase();
        const toPartnerIds = this.state.to.map((email) => emailToPartner[key(email)]).filter(Boolean);
        const ccPartnerIds = this.state.cc.map((email) => emailToPartner[key(email)]).filter(Boolean);
        const bccPartnerIds = this.state.bcc.map((email) => emailToPartner[key(email)]).filter(Boolean);
        const allPartnerIds = [...new Set([...toPartnerIds, ...ccPartnerIds, ...bccPartnerIds])];

        // Signaturen infogas server-side vid sändning (_ensure_signature),
        // ovanför citatet. Klientens append byggde på mail.store-uid som
        // saknas här och hamnade dessutom under citatet.
        const body = this.getBody();

        const composerValues = {
            composition_mode: "personal_email",
            subject: this.state.subject,
            body: body,
            partner_ids: [[6, 0, allPartnerIds]],
            email_cc: this.state.cc.join(", "),
            email_bcc: this.state.bcc.join(", "),
            signature_type: this.state.signatureType || "auto",
        };
        // The original message, not the draft, is the parent: sending a saved
        // draft reply must mark the original replied and link the sent copy to
        // it. The draft itself is removed after sending.
        if (this.props.parentMailboxId) {
            composerValues.personal_mailbox_id = this.props.parentMailboxId;
        } else if (this.state.draftId) {
            composerValues.personal_mailbox_id = this.state.draftId;
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

    async _resolveAllPartners(emails) {
        const uniqueEmails = [...new Set(emails.map((e) => e.trim().toLowerCase()).filter(Boolean))];
        const emailToPartner = {};
        const unknownEmails = [];
        for (const email of uniqueEmails) {
            // "_" och "%" är jokertecken i =ilike: utan escaping matchade
            // a_b@x.se även axb@x.se och fel kontakt blev mottagare
            // (granskning 2026-09-20). Träffen jämförs dessutom exakt
            // efteråt, så ett kvarvarande jokertecken inte kan slinka med.
            const pattern = email.replace(/([\\%_])/g, "\\$1");
            const partners = await this.orm.searchRead(
                "res.partner",
                [["email", "=ilike", pattern]],
                ["id", "email"]
            );
            const exact = partners.find(
                (p) => (p.email || "").trim().toLowerCase() === email
            );
            if (exact) {
                emailToPartner[email] = exact.id;
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
