# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

{
    "name": "Unified Workspace",
    "version": "18.0.1.1.0",
    "category": "Productivity/Discuss",
    "summary": "Extend Discuss into a unified communication hub with personal email, calendar and tasks.",
    "description": """
Unified Workspace
=================

Extends Odoo Discuss into a communication hub that brings personal email,
calendar, chat and tasks into one place.

Features
--------

* Personal email inbox per user (IMAP) routed into Discuss.
* Folder structure: Inbox, Sent, Drafts, Trash and custom folders.
* Conversation threads grouped by Message-ID and parent.
* Full composer with To/CC/BCC, attachments and signatures.
* One-click CRM actions: create lead, log to lead, create task, book meeting.
* Contact card with pipeline and activities in the reading pane.
* Calendar and chat accessible from the same sidebar.
* Search and filters across all folders.

The module reuses existing Odoo infrastructure (fetchmail, mail.message,
mail.thread, web_editor) and never duplicates it.
    """,
    "author": "ARC Gruppen",
    "website": "https://arcgruppen.se",
    "depends": [
        "mail",
        "crm",
        "calendar",
        "project",
        "hr_timesheet",
        "web_editor",
        "html_editor",
        "dms",
        "document_page",
    ],
    "data": [
        "security/unified_workspace_security.xml",
        "security/ir.model.access.csv",
        "data/mail_personal_folder_data.xml",
        "data/mail_personal_scheduled_message_cron.xml",
        "data/mail_personal_archive_cron.xml",
        "views/mail_personal_folder_views.xml",
        "views/mail_personal_mailbox_views.xml",
        "views/mail_personal_template_views.xml",
        "views/res_users_views.xml",
        "views/res_config_settings_views.xml",
        "views/unified_workspace_client_action.xml",
        "views/res_partner_views.xml",
        "views/unified_workspace_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "unified_workspace/static/src/services/mailbox_service.js",
            "unified_workspace/static/src/components/**/*.js",
            "unified_workspace/static/src/components/**/*.xml",
            "unified_workspace/static/src/components/**/*.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
