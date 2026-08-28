# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Remove Sent/Drafts/Trash system folders; keep messages in Inbox.

    Existing messages in Sent are kept as read, Drafts as draft state and
    Trash is archived. The obsolete folders are then removed.
    """
    # Map obsolete folder types to mailbox state.
    mapping = {
        "sent": "read",
        "drafts": "draft",
        "trash": "archived",
    }

    for folder_type, state in mapping.items():
        cr.execute(
            """
            SELECT id, user_id
              FROM mail_personal_folder
             WHERE folder_type = %s
            """,
            (folder_type,),
        )
        folders = cr.fetchall()
        if not folders:
            continue

        folder_ids = [f[0] for f in folders]
        _logger.info(
            "Migrating %d %(type)s folders to state %(state)s",
            len(folder_ids),
            {"type": folder_type, "state": state},
        )

        cr.execute(
            """
            UPDATE mail_personal_mailbox
               SET state = %s
             WHERE folder_id = ANY(%s)
            """,
            (state, folder_ids),
        )

        # Move affected messages to the user's Inbox folder.
        cr.execute(
            """
            UPDATE mail_personal_mailbox m
               SET folder_id = i.id
              FROM mail_personal_folder i
             WHERE m.folder_id = ANY(%s)
               AND i.folder_type = 'inbox'
               AND i.user_id = m.user_id
            """,
            (folder_ids,),
        )

        # Delete obsolete folders.
        cr.execute(
            """
            DELETE FROM mail_personal_folder
             WHERE id = ANY(%s)
            """,
            (folder_ids,),
        )
