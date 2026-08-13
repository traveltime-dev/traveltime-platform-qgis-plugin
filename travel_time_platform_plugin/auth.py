from qgis.core import QgsApplication


def set_app_id_and_api_key(app_id, api_key):
    manager = QgsApplication.instance().authManager()

    ok1 = manager.storeAuthSetting("TTP_APP_ID", app_id, True)
    ok2 = manager.storeAuthSetting("TTP_API_KEY", api_key, True)

    if not (ok1 and ok2):
        # Storing fails if the authentication database is unavailable, typically
        # because the user dismissed the QGIS master password prompt. Raise rather
        # than assert, so it still surfaces under `python -O`.
        raise RuntimeError(
            "Could not store the TravelTime credentials in the QGIS "
            "authentication database."
        )


def get_app_id_and_api_key():
    manager = QgsApplication.instance().authManager()

    app_id = manager.authSetting("TTP_APP_ID", None, True)
    api_key = manager.authSetting("TTP_API_KEY", None, True)

    return app_id, api_key
