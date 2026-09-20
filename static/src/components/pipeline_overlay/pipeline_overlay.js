/** @odoo-module **/

import { Component, onMounted, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * CRM pipeline overlay for dragging personal emails onto CRM stages.
 *
 * Each column is a crm.stage and shows the opportunities already in it.
 * Dropping an email on a column creates/updates its linked crm.lead and
 * moves it to that stage (mail.personal.mailbox.action_move_to_stage).
 */
export class PipelineOverlay extends Component {
    static template = "unified_workspace.PipelineOverlay";
    static props = {
        close: { type: Function, optional: true },
        onClose: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mailbox = useService("mailbox");
        this.state = useState({
            stages: [],
            leadsByStage: {},
            isLoading: false,
        });
        onMounted(() => this.loadPipeline());
    }

    async loadPipeline() {
        this.state.isLoading = true;
        const stages = await this.orm.searchRead(
            "crm.stage",
            [],
            ["id", "name", "sequence"],
            { order: "sequence, id" }
        );
        const leads = await this.orm.searchRead(
            "crm.lead",
            [["type", "=", "opportunity"]],
            ["id", "name", "partner_id", "stage_id"],
            { order: "create_date DESC", limit: 200 }
        );
        const leadsByStage = {};
        for (const stage of stages) {
            leadsByStage[stage.id] = [];
        }
        for (const lead of leads) {
            const stageId = lead.stage_id?.[0];
            if (stageId && leadsByStage[stageId]) {
                leadsByStage[stageId].push(lead);
            }
        }
        this.state.stages = stages;
        this.state.leadsByStage = leadsByStage;
        this.state.isLoading = false;
    }

    onDragOver(ev) {
        ev.preventDefault();
    }

    async onDrop(ev, stageId) {
        ev.preventDefault();
        const messageId = parseInt(ev.dataTransfer.getData("text/plain"), 10);
        if (!messageId) {
            return;
        }
        await this.mailbox.moveToStage(messageId, stageId);
        await this.loadPipeline();
    }

    onClose() {
        if (this.props.close) {
            this.props.close();
        } else if (this.props.onClose) {
            this.props.onClose();
        }
    }
}
