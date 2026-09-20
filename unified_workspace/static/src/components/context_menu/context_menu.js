/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

/**
 * Floating right-click menu for the Unified Workspace.
 *
 * Positioned with fixed coordinates at the pointer, the same way the native
 * context menus behave in Gmail and Outlook. It closes on an outside click,
 * on Escape, and when the page scrolls or resizes.
 */
export class ContextMenu extends Component {
    static template = "unified_workspace.ContextMenu";
    static props = {
        position: Object,
        items: Array,
        onClose: Function,
    };

    setup() {
        this.menuRef = useRef("menu");
        this.state = useState({
            x: this.props.position.x,
            y: this.props.position.y,
        });
        this._onPointerDown = (ev) => {
            if (!this.menuRef.el?.contains(ev.target)) {
                this.props.onClose();
            }
        };
        this._onKeydown = (ev) => {
            if (ev.key === "Escape") {
                ev.preventDefault();
                ev.stopPropagation();
                this.props.onClose();
            }
        };
        this._onDismiss = () => this.props.onClose();
        onMounted(() => {
            document.addEventListener("pointerdown", this._onPointerDown, true);
            document.addEventListener("keydown", this._onKeydown, true);
            window.addEventListener("scroll", this._onDismiss, true);
            window.addEventListener("resize", this._onDismiss);
            this._clampToViewport();
        });
        onWillUnmount(() => {
            document.removeEventListener("pointerdown", this._onPointerDown, true);
            document.removeEventListener("keydown", this._onKeydown, true);
            window.removeEventListener("scroll", this._onDismiss, true);
            window.removeEventListener("resize", this._onDismiss);
        });
    }

    get menuStyle() {
        return `left: ${this.state.x}px; top: ${this.state.y}px;`;
    }

    /** Keep the menu inside the viewport when the pointer is near an edge. */
    _clampToViewport() {
        const el = this.menuRef.el;
        if (!el) {
            return;
        }
        const margin = 8;
        const rect = el.getBoundingClientRect();
        const maxX = Math.max(margin, window.innerWidth - rect.width - margin);
        const maxY = Math.max(margin, window.innerHeight - rect.height - margin);
        this.state.x = Math.max(margin, Math.min(this.state.x, maxX));
        this.state.y = Math.max(margin, Math.min(this.state.y, maxY));
    }

    onItemClick(item, ev) {
        ev.stopPropagation();
        if (item.action) {
            item.action();
        }
        this.props.onClose();
    }
}
