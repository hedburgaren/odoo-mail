/** @odoo-module **/

import { Component, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { View } from "@web/views/view";

/**
 * Inline calendar view inside the Unified Workspace main area.
 */
export class CalendarPanel extends Component {
    static template = "unified_workspace.CalendarPanel";
    static components = { View };
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.viewProps = {};
        onWillStart(async () => {
            const result = await this.action.loadAction("calendar.action_calendar_event");
            const calendarView = result.views.find((v) => v[1] === "calendar");
            const searchView = result.views.find((v) => v[1] === "search");
            this.viewProps = {
                resModel: result.res_model,
                type: "calendar",
                viewId: calendarView ? calendarView[0] : false,
                views: [
                    [calendarView ? calendarView[0] : false, "calendar"],
                    [searchView ? searchView[0] : false, "search"],
                ],
                display: { controlPanel: {} },
                context: {},
            };
        });
    }
}
