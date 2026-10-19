import json
import os
import hashlib
import threading

USERS_FILE = "users.json"
users_lock = threading.Lock()
_users_cache = {}

def load():
    """Loads the user database from disk into memory."""
    global _users_cache
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                _users_cache = json.load(f)
        except json.JSONDecodeError:
            _users_cache = {}
    else:
        _users_cache = {}

def hash_password(password):
    """Returns the SHA-256 hash of a password."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def authenticate(username, password):
    """Checks if the username exists and the password matches the hash."""
    with users_lock:
        if username not in _users_cache:
            return False
        return _users_cache[username] == hash_password(password)

def register(username, password):
    """Safely adds a new user to the JSON database."""
    global _users_cache
    with users_lock:
        if username in _users_cache:
            return False, "Username already exists."
            
        _users_cache[username] = hash_password(password)
        
        # Safely save to JSON just like metadata
        temp_file = USERS_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(_users_cache, f, indent=4)
        os.replace(temp_file, USERS_FILE)
        
        return True, "Registration successful."
