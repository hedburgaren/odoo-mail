/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

/**
 * Datetime picker for scheduling an email to be sent later.
 */
export class ScheduleSender extends Component {
    static template = "unified_workspace.ScheduleSender";
    static props = {
        close: { type: Function },
        onSchedule: { type: Function, optional: true },
    };

    setup() {
        this.onConfirm = this.onConfirm.bind(this);
        this.onCancel = this.onCancel.bind(this);
        const now = new Date();
        now.setMinutes(now.getMinutes() + 30);
        const iso = this._toLocalIso(now);
        this.state = useState({
            scheduledDate: iso,
        });
    }

    _toLocalIso(date) {
        const pad = (n) => n.toString().padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    onConfirm = () => {
        const value = new Date(this.state.scheduledDate);
        if (isNaN(value.getTime()) || value <= new Date()) {
            return;
        }
        if (this.props.onSchedule) {
            this.props.onSchedule(value.toISOString());
        }
        this.props.close();
    }

    onCancel = () => {
        if (this.props.onSchedule) {
            this.props.onSchedule(null);
        }
        this.props.close();
    }
}
