/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Drag-and-drop file uploader for email attachments.
 *
 * Reads files as base64 and creates ir.attachment records via the ORM.
 */
export class AttachmentUploader extends Component {
    static template = "unified_workspace.AttachmentUploader";
    static props = {
        attachments: { type: Array, optional: true },
        onChange: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            attachments: this.props.attachments ? [...this.props.attachments] : [],
            isDragOver: false,
        });
    }

    get value() {
        return [...this.state.attachments];
    }

    onDragOver() {
        this.state.isDragOver = true;
    }

    onDragLeave() {
        this.state.isDragOver = false;
    }

    async onDrop(ev) {
        this.state.isDragOver = false;
        const files = ev.dataTransfer?.files;
        if (files?.length) {
            await this.uploadFiles(files);
        }
    }

    async onFileSelect(ev) {
        const files = ev.target.files;
        if (files?.length) {
            await this.uploadFiles(files);
        }
        ev.target.value = "";
    }

    async uploadFiles(files) {
        for (const file of files) {
            try {
                const attachment = await this._uploadFile(file);
                this.state.attachments.push(attachment);
            } catch (error) {
                this.notification.add(`Failed to upload ${file.name}.`, { type: "danger" });
            }
        }
        this.notify();
    }

    async _uploadFile(file) {
        const data = await this._readFileAsBase64(file);
        const [attachmentId] = await this.orm.create("ir.attachment", [{
            name: file.name,
            datas: data,
            mimetype: file.type || "application/octet-stream",
            res_model: "mail.compose.message",
            res_id: 0,
        }]);
        return {
            id: attachmentId,
            name: file.name,
            mimetype: file.type || "application/octet-stream",
            datas: data,
        };
    }

    _readFileAsBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = reader.result.split(",")[1];
                resolve(result);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    removeAttachment(attachmentId) {
        this.state.attachments = this.state.attachments.filter((a) => a.id !== attachmentId);
        this.notify();
    }

    notify() {
        if (this.props.onChange) {
            this.props.onChange([...this.state.attachments]);
        }
    }
}
