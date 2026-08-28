# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http
from odoo.http import request
from odoo.tools.translate import _


class UnifiedWorkspaceController(http.Controller):
    """AJAX endpoints for the Unified Workspace frontend."""

    @http.route("/unified_workspace/mailbox/folders", type="json", auth="user")
    def mailbox_folders(self):
        """Return the current user's personal folders with message counts."""
        Folder = request.env["mail.personal.folder"]
        folders = Folder.search([
            ("user_id", "=", request.env.user.id),
        ], order="sequence, name")
        return folders.read(["id", "name", "folder_type", "sequence", "message_count"])

    @http.route("/unified_workspace/mailbox/messages", type="json", auth="user")
    def mailbox_messages(self, folder_id=None, search=None, limit=50, offset=0):
        """Return messages for the given folder with optional full-text search."""
        domain = [("user_id", "=", request.env.user.id)]
        if folder_id:
            domain.append(("folder_id", "=", int(folder_id)))
        if search:
            domain.extend([
                "|", "|", "|",
                ("name", "ilike", search),
                ("email_from", "ilike", search),
                ("email_to", "ilike", search),
                ("body_text", "ilike", search),
            ])
        messages = request.env["mail.personal.mailbox"].search(
            domain,
            limit=int(limit),
            offset=int(offset),
            order="date DESC, id DESC",
        )
        return messages.read([
            "id",
            "name",
            "email_from",
            "email_to",
            "email_cc",
            "date",
            "state",
            "is_starred",
            "body_text",
            "folder_id",
            "partner_id",
            "attachment_ids",
        ])

    @http.route("/unified_workspace/mailbox/message/<int:message_id>", type="json", auth="user")
    def mailbox_message(self, message_id):
        """Return a single mailbox message with full body."""
        message = request.env["mail.personal.mailbox"].browse(message_id)
        if message.user_id != request.env.user:
            return {"error": _("Access denied")}
        return message.read([
            "id",
            "name",
            "email_from",
            "email_to",
            "email_cc",
            "email_bcc",
            "reply_to",
            "date",
            "state",
            "is_starred",
            "body",
            "folder_id",
            "partner_id",
            "attachment_ids",
            "crm_lead_id",
            "project_task_id",
            "calendar_event_id",
        ])[0]

    @http.route("/unified_workspace/mailbox/mark_read", type="json", auth="user")
    def mailbox_mark_read(self, message_ids):
        messages = request.env["mail.personal.mailbox"].browse(message_ids)
        messages.action_mark_read()
        return {"status": "ok"}

    @http.route("/unified_workspace/mailbox/mark_unread", type="json", auth="user")
    def mailbox_mark_unread(self, message_ids):
        messages = request.env["mail.personal.mailbox"].browse(message_ids)
        messages.action_mark_unread()
        return {"status": "ok"}

    @http.route("/unified_workspace/mailbox/toggle_starred", type="json", auth="user")
    def mailbox_toggle_starred(self, message_ids):
        messages = request.env["mail.personal.mailbox"].browse(message_ids)
        messages.action_toggle_starred()
        return {"status": "ok"}

    @http.route("/unified_workspace/mailbox/move_to_trash", type="json", auth="user")
    def mailbox_move_to_trash(self, message_ids):
        messages = request.env["mail.personal.mailbox"].browse(message_ids)
        messages.action_move_to_trash()
        return {"status": "ok"}
