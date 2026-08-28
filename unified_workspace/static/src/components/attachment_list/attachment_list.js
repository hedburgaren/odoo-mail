/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * Display a list of ir.attachment records with preview for images and PDFs.
 */
export class AttachmentList extends Component {
    static template = "unified_workspace.AttachmentList";
    static props = {
        attachments: { type: Array },
        linkedRecord: { type: [Array, { value: null }], optional: true },
        onSaveToRecord: { type: Function, optional: true },
    };

    setup() {
        this.state = useState({
            previewAttachment: null,
        });
        this.onOpenPreview = (attachment) => {
            this.state.previewAttachment = attachment;
        };
        this.onClosePreview = () => {
            this.state.previewAttachment = null;
        };
    }

    get hasLinkedRecord() {
        return Boolean(this.props.linkedRecord?.[0]);
    }

    onSaveToRecord() {
        if (this.props.onSaveToRecord) {
            this.props.onSaveToRecord();
        }
    }

    isImage(attachment) {
        return attachment.mimetype?.startsWith("image/");
    }

    isPdf(attachment) {
        return attachment.mimetype === "application/pdf";
    }

    isPreviewable(attachment) {
        return this.isImage(attachment) || this.isPdf(attachment);
    }

    getImageUrl(attachment) {
        if (attachment.datas) {
            return `data:${attachment.mimetype};base64,${attachment.datas}`;
        }
        return `/web/content/${attachment.id}`;
    }

    getDownloadUrl(attachment) {
        return `/web/content/${attachment.id}?download=true`;
    }

    getPreviewUrl(attachment) {
        return `/web/content/${attachment.id}`;
    }
}
