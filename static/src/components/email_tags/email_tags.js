/** @odoo-module **/

import { Component, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Tokenized email input component.
 *
 * Displays email addresses as removable tags and lets the user add new ones
 * by typing a comma, semicolon, space or pressing Enter.
 */
export class EmailTags extends Component {
    static template = "unified_workspace.EmailTags";
    static props = {
        emails: { type: Array, optional: true },
        placeholder: { type: String, optional: true },
        onChange: { type: Function, optional: true },
    };

    setup() {
        this.inputRef = useRef("input");
        this.orm = useService("orm");
        this.state = useState({
            emails: this.props.emails ? [...this.props.emails] : [],
            suggestions: [],
            isLoading: false,
            selectedIndex: 0,
        });
    }

    get value() {
        return [...this.state.emails];
    }

    addEmail(raw) {
        const emails = raw.split(/[,;\s]+/).map((e) => e.trim()).filter(Boolean);
        for (const email of emails) {
            if (!EMAIL_RE.test(email)) {
                continue;
            }
            if (!this.state.emails.includes(email)) {
                this.state.emails.push(email);
            }
        }
        this.notify();
    }

    removeEmail(email) {
        this.state.emails = this.state.emails.filter((e) => e !== email);
        this.notify();
    }

    notify() {
        if (this.props.onChange) {
            this.props.onChange([...this.state.emails]);
        }
    }

    onContainerClick() {
        this.inputRef.el?.focus();
    }

    async fetchSuggestions(query) {
        const trimmed = query.trim();
        if (trimmed.length < 2) {
            this.state.suggestions = [];
            return;
        }
        this.state.isLoading = true;
        try {
            const partners = await this.orm.searchRead(
                "res.partner",
                ["|", ["name", "ilike", trimmed], ["email", "ilike", trimmed]],
                ["display_name", "email"],
                { limit: 5 }
            );
            this.state.suggestions = partners
                .filter((p) => p.email && EMAIL_RE.test(p.email) && !this.state.emails.includes(p.email))
                .map((p) => ({ id: p.id, name: p.display_name || p.name, email: p.email }));
            this.state.selectedIndex = 0;
        } finally {
            this.state.isLoading = false;
        }
    }

    onInputKeydown(ev) {
        if (this.state.suggestions.length) {
            if (ev.key === "ArrowDown") {
                ev.preventDefault();
                this.state.selectedIndex = (this.state.selectedIndex + 1) % this.state.suggestions.length;
                return;
            } else if (ev.key === "ArrowUp") {
                ev.preventDefault();
                this.state.selectedIndex = (this.state.selectedIndex - 1 + this.state.suggestions.length) % this.state.suggestions.length;
                return;
            } else if (ev.key === "Enter") {
                ev.preventDefault();
                const suggestion = this.state.suggestions[this.state.selectedIndex];
                if (suggestion) {
                    this.addEmail(suggestion.email);
                    ev.target.value = "";
                    this.state.suggestions = [];
                }
                return;
            } else if (ev.key === "Escape") {
                this.state.suggestions = [];
                return;
            }
        }
        if (ev.key === "Enter" || ev.key === "," || ev.key === ";") {
            ev.preventDefault();
            this.addEmail(ev.target.value);
            ev.target.value = "";
            this.state.suggestions = [];
        } else if (ev.key === "Backspace" && !ev.target.value && this.state.emails.length) {
            this.removeEmail(this.state.emails[this.state.emails.length - 1]);
        }
    }

    onInputBlur(ev) {
        if (ev.target.value) {
            this.addEmail(ev.target.value);
            ev.target.value = "";
        }
        this.state.suggestions = [];
    }

    onInput(ev) {
        this.fetchSuggestions(ev.target.value);
    }

    selectSuggestion(suggestion) {
        this.addEmail(suggestion.email);
        this.inputRef.el.value = "";
        this.inputRef.el.focus();
        this.state.suggestions = [];
    }

    onPaste(ev) {
        ev.preventDefault();
        const text = ev.clipboardData.getData("text");
        this.addEmail(text);
    }
}
