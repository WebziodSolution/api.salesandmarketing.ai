from django.apps import AppConfig


class AuthAppConfig(AppConfig):
    name = 'auth_app'

    def ready(self):
        # Monkey-patch Django Oracle max length to allow exactly matching long columns without MD5 hashes
        from django.db.backends.oracle.operations import DatabaseOperations
        DatabaseOperations.max_name_length = lambda self: 128
