# credential_manager.py
import json
import os
from .constants import CREDENTIALS_FILE


DEFAULT_CREDENTIALS = {
    "NEO4J_URI": "",
    "NEO4J_USERNAME": "",
    "NEO4J_PASSWORD": "",
    "INSTAGRAM_USERNAME": "",
    "INSTAGRAM_USER_AGENT": "",
    "GEMINI_API_KEY": "",
    # OrcaRouter Cyber Inference (API-key authentication, same store as the
    # rest of the project's secrets).
    "ORCAROUTER_API_KEY": "",
    "ORCAROUTER_MODEL": "",
    "ORCAROUTER_EMBEDDING_MODEL": "",
    "LLM_PROVIDER": "",
}


def credentials_path():
    """Path of the existing credential file.

    ``OSINTGRAPH_CREDENTIALS_FILE`` lets tests and packaging point at an
    isolated file; production behaviour is unchanged.
    """
    return os.environ.get("OSINTGRAPH_CREDENTIALS_FILE") or CREDENTIALS_FILE


class CredentialManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CredentialManager, cls).__new__(cls)
            cls._instance._load_or_initialize()

        return cls._instance

    def _load_or_initialize(self):
        path = credentials_path()
        if not os.path.exists(path):
            self.credentials = dict(DEFAULT_CREDENTIALS)
            self._save()
        else:
            with open(path, "r") as f:
                self.credentials = json.load(f)
            # Credentials files written by older versions gain the newer keys
            # without losing what the user already stored.
            missing = {k: v for k, v in DEFAULT_CREDENTIALS.items() if k not in self.credentials}
            if missing:
                self.credentials.update(missing)
                self._save()

    def reset(self, keys=None):
        """Reset all credentials or specific keys."""
        if keys is None:
            for k in self.credentials:
                self.credentials[k] = ""
        else:
            for k in keys:
                if k in self.credentials:
                    self.credentials[k] = ""
        self._save()

    def _save(self):
        path = credentials_path()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.credentials, f, indent=4)
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Filesystems without POSIX permissions must not break setup.
            pass

    def get(self, key):
        return self.credentials.get(key, "")

    def set(self, key, value):
        self.credentials[key] = value
        self._save()


_credential_manager_instance = CredentialManager()

def get_credential_manager():
    return _credential_manager_instance
