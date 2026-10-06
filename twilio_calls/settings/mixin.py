from features.settings import save_settings, settings_state, values


class SettingsMixin:
    def _values(self):
        return values(self)

    def settings_state(self):
        return settings_state(self)

    def save_settings(self, data):
        return save_settings(self, data)
