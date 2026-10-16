import json
import os
import threading
from datetime import datetime

METADATA_FILE = "metadata.json"
metadata_lock = threading.Lock()

def add_or_update_metadata(filename, owner, size, sha256_hex):
    with metadata_lock:
        data = {}
        if os.path.exists(METADATA_FILE):
            try:
                with open(METADATA_FILE, "r") as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                # Fallback if file is somehow empty or corrupted
                data = {}

        # Check if file already exists to preserve download count if overwritten
        downloads = 0
        if filename in data:
            downloads = data[filename].get("downloads", 0)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data[filename] = {
            "owner": owner,
            "size": size,
            "sha256": sha256_hex,
            "uploaded": current_time,
            "downloads": downloads
        }

        # Safe atomic write using a temporary file and os.replace
        temp_file = METADATA_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, METADATA_FILE)
