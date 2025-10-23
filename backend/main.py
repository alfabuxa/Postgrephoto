import exif_utils
import os
import psycopg2
from datetime import datetime
from pathlib import Path

# PostgreSQL connection
conn = psycopg2.connect(
    dbname="photodb",
    user="alf",          
    password="yourpassword",         
    host="localhost"
)
cur = conn.cursor()

# Create table if not exists
cur.execute("""
CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    filename TEXT,
    path TEXT,
    filetype TEXT,
    size_mb REAL,
    modified TIMESTAMP
);
""")
conn.commit()

# Folder to scan
FOLDER_PATH = "/home/rog/Desktop/photos"  # change to your target folder

def scan_folder(folder: str):
    """Scan a folder recursively and yield file info."""
    for root, _, files in os.walk(folder):
        for file in files:
            full_path = os.path.join(root, file)
            try:
                stat = os.stat(full_path)
                yield {
                    "filename": file,
                    "path": full_path,
                    "filetype": Path(file).suffix.lower(),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": datetime.fromtimestamp(stat.st_mtime)
                }
            except (OSError, PermissionError):
                continue

def store_to_db(file_info):
    exif = exif_utils.extract_exif(file_info["path"])
    camera_model = exif.get("Model")
    taken_at = exif.get("DateTimeOriginal")
    if isinstance(taken_at, str):
        try:
            taken_at = datetime.strptime(taken_at, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            taken_at = None
    """Insert one file's metadata into PostgreSQL."""
    cur.execute("""
        INSERT INTO files (filename, path, filetype, size_mb, modified, camera_model, taken_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (path) DO UPDATE SET
            filename = EXCLUDED.filename,
            size_mb = EXCLUDED.size_mb,
            modified = EXCLUDED.modified,
            camera_model = EXCLUDED.camera_model,
            taken_at = EXCLUDED.taken_at;
    """, (
        file_info["filename"],
        file_info["path"],
        file_info["filetype"],
        file_info["size_mb"],
        file_info["modified"],
        camera_model,
        taken_at
    ))

def get_all_db_paths():
    """Fetch all file paths currently in the database."""
    cur.execute("SELECT path FROM files;")
    return {row[0] for row in cur.fetchall()}

def cleanup_removed_files(scanned_paths):
    db_paths = get_all_db_paths()
    stale_paths = db_paths - scanned_paths

    if stale_paths:
        print(f"Removing {len(stale_paths)} stale files from DB...")
        cur.executemany("DELETE FROM files WHERE path = %s;", [(p,) for p in stale_paths])
        conn.commit()
    else:
        print("No stale entries to remove.")



def main():
    count = 0
    scanned_paths = set() 
    for file_info in scan_folder(FOLDER_PATH):
        store_to_db(file_info)
        scanned_paths.add(file_info["path"])
        count += 1
        if count % 100 == 0:
            conn.commit()
            print(f"Indexed {count} files...")

    conn.commit()
    print(f"Scan complete. Total indexed: {count}")

    cleanup_removed_files(scanned_paths)
    for path in list(scanned_paths)[:10]:
        print(path)

if __name__ == "__main__":
    main()

cur.close()
conn.close()
