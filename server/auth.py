import json
import os
import hashlib
import threading
from pathlib import Path

# Always resolve paths relative to this file's location
SERVER_DIR = Path(__file__).resolve().parent
ROOT_DIR = SERVER_DIR.parent

USERS_FILE_SERVER = SERVER_DIR / "users.json"
USERS_FILE_ROOT = ROOT_DIR / "users.json"

users_lock = threading.Lock()
_users_cache = {}


def _save_unlocked():
    """Atomically saves _users_cache to users.json in both server/ and root dirs."""
    for target in [USERS_FILE_SERVER, USERS_FILE_ROOT]:
        temp_file = str(target) + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(_users_cache, f, indent=4)
        os.replace(temp_file, target)  # FIX 1: Atomic rename so disk is updated


def load():
    """Loads the user database from disk into memory."""
    global _users_cache
    with users_lock:
        target = USERS_FILE_SERVER if USERS_FILE_SERVER.exists() else USERS_FILE_ROOT
        if target.exists():
            try:
                with open(target, "r", encoding="utf-8") as f:
                    _users_cache = json.load(f)
            except json.JSONDecodeError:
                _users_cache = {}
        else:
            _users_cache = {}


def hash_password(password):
    """Returns the SHA-256 hash of a password after stripping trailing whitespace/newlines."""
    clean_pass = str(password).strip()  # FIX 4: Strips hidden \n or spaces
    return hashlib.sha256(clean_pass.encode('utf-8')).hexdigest()


def authenticate(username, password):
    """Checks if the username exists and the password matches the hash."""
    clean_user = str(username).strip()
    with users_lock:
        if clean_user not in _users_cache:
            return False
        return _users_cache[clean_user] == hash_password(password)


def register(username, password):
    """Safely adds a new user to the JSON database."""
    global _users_cache
    clean_user = str(username).strip()
    if not clean_user or not password:
        return False, "Username and password cannot be empty."

    with users_lock:
        if clean_user in _users_cache:
            return False, "Username already exists."
            
        _users_cache[clean_user] = hash_password(password)
        _save_unlocked()
        return True, "Registration successful."  # FIX 2: Added explicit success return tuple
