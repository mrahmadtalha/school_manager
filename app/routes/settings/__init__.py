"""settings routes (split into focused sub-modules; every name is re-exported here)."""

from app.routes.settings.school import (  # noqa: F401
    _node_service_url,
    bridge_access_required,
    get_whatsapp_service_status,
    set_language,
    school_settings,
    assign_missing_admission_numbers,
    school_settings_grading,
    school_settings_custom_fields,
    run_backup_now,
    download_backup,
    QUEUE_VIEW_LIMIT,
    _queue_redirect,
)
from app.routes.settings.automation import (  # noqa: F401
    automation_panel,
    brand_logo,
    whatsapp_status,
    whatsapp_qr,
    whatsapp_integration,
    whatsapp_test_message,
    whatsapp_pending_messages,
    whatsapp_update_status,
    whatsapp_authorize_send,
)

import requests  # noqa: F401  (tests patch app.routes.settings.requests.post)
