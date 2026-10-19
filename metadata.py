import json
import os
import threading
from datetime import datetime

METADATA_FILE = "metadata.json"
metadata_lock = threading.Lock()

_metatdata_cache = {}

def load():
    """Loads the JSON file into the memory at the server start up"""
    global _metadata_cache
    with metadata_lock:
        if os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE,"r") as f:
                    _metadata_cache = json.load(f)
                print("[*] Loaded metadata.json.")
            except json.JSONDecodeError:
                _metadata_cache = {}
            
        else:
            _metadata_cache = {}
        
def list_all():
    with metadata_lock:
        return _metadata_cache.copy()

def get(name):
    """Returns a safe copy of a specific file's metadata."""
    with metadata_lock:
        return _metadata_cache.get(name, {}).copy() if name in _metadata_cache else None

def count_download(name):
    """Safely increments the download counter for a file."""
    global _metadata_cache
    with metadata_lock:
        if name in _metadata_cache:
            _metadata_cache[name]["downloads"] = _metadata_cache[name].get("downloads", 0) + 1
            
            # Safely save to JSON
            temp_meta = METADATA_FILE + ".tmp"
            with open(temp_meta, "w") as f:
                json.dump(_metadata_cache, f, indent=4)
            os.replace(temp_meta, METADATA_FILE)
            return True
        return False        

def add_or_update(temp_filepath, final_filepath, owner, size, sha256_hex):
    """Handles the owner check, physical file swap, and metadata update under one lock."""
    name=os.path.basename(final_filepath)
    
    global _metadata_cache
    
    with metadata_lock:
        # 1. Owner Check
        if name in _metadata_cache:
            if _metadata_cache[name].get("owner") != owner:
                return False, "ERROR: You are not the owner of this file."
                
        # 2. Rename (Swap) the physical file
        try:
            os.replace(temp_filepath, final_filepath)
        except OSError as e:
            return False, f"ERROR: File system error - {e}"
            
        # 3. Update the metadata dictionary
        downloads = _metadata_cache.get(name, {}).get("downloads", 0)
        
        _metadata_cache[name] = {
            "owner": owner,
            "size": size,
            "sha256": sha256_hex,
            "uploaded": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "downloads": downloads
        }
        
        # 4. Safely save to JSON
        temp_meta = METADATA_FILE + ".tmp"
        with open(temp_meta, "w") as f:
            json.dump(_metadata_cache, f, indent=4)
        os.replace(temp_meta, METADATA_FILE)
        
        return True, "SUCCESS: File received and verified by server."
