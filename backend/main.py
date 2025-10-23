import exif_utils
import os
import psycopg2
from datetime import datetime
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('indexer.log'),
        logging.StreamHandler()
    ]
)

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
    modified TIMESTAMP,
    camera_model TEXT,
    taken_at TIMESTAMP
);
""")

# Add UNIQUE constraint on path if it doesn't exist
cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS files_path_unique ON files (path);
""")

# Migration: Add missing columns if they don't exist
cur.execute("""
ALTER TABLE files 
ADD COLUMN IF NOT EXISTS camera_model TEXT,
ADD COLUMN IF NOT EXISTS taken_at TIMESTAMP;
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
    """Insert one file's metadata into PostgreSQL."""
    try:
        exif = exif_utils.extract_exif(file_info["path"])
        camera_model = exif.get("Model")
        taken_at = exif.get("DateTimeOriginal")
        if isinstance(taken_at, str):
            try:
                taken_at = datetime.strptime(taken_at, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                taken_at = None
        
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
    except Exception as e:
        logging.error(f"Failed to store file {file_info['path']}: {str(e)}")
        raise

def get_all_db_paths():
    """Fetch all file paths currently in the database."""
    cur.execute("SELECT path FROM files;")
    return {row[0] for row in cur.fetchall()}

def cleanup_removed_files(scanned_paths):
    """Remove files from database that are no longer found in the filesystem."""
    try:
        db_paths = get_all_db_paths()
        stale_paths = db_paths - scanned_paths

        if stale_paths:
            logging.info(f"Removing {len(stale_paths)} stale files from DB...")
            cur.executemany("DELETE FROM files WHERE path = %s;", [(p,) for p in stale_paths])
            conn.commit()
            logging.info(f"Successfully removed {len(stale_paths)} stale files")
        else:
            logging.info("No stale entries to remove.")
    except Exception as e:
        logging.error(f"Failed to cleanup removed files: {str(e)}")
        conn.rollback()
        raise



def main():
    count = 0
    success_count = 0
    error_count = 0
    scanned_paths = set()
    
    try:
        logging.info(f"Starting scan of folder: {FOLDER_PATH}")
        
        for file_info in scan_folder(FOLDER_PATH):
            try:
                store_to_db(file_info)
                scanned_paths.add(file_info["path"])
                success_count += 1
                count += 1
                
                # Commit at consistent checkpoints
                if count % 100 == 0:
                    conn.commit()
                    logging.info(f"Checkpoint: Indexed {count} files (success: {success_count}, errors: {error_count})")
                    
            except Exception as e:
                error_count += 1
                count += 1
                logging.error(f"Failed to process file {file_info['path']}: {str(e)}")
                # Roll back the failed transaction and continue
                conn.rollback()
                continue

        # Final commit for remaining files
        conn.commit()
        logging.info(f"Scan complete. Total processed: {count}, Success: {success_count}, Errors: {error_count}")

        # Cleanup removed files
        cleanup_removed_files(scanned_paths)
        
        # Log sample of indexed paths
        sample_paths = list(scanned_paths)[:10]
        if sample_paths:
            logging.info("Sample indexed paths:")
            for path in sample_paths:
                logging.info(f"  {path}")
                
    except Exception as e:
        logging.error(f"Critical error in main indexing workflow: {str(e)}")
        conn.rollback()
        raise

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Indexer failed with error: {str(e)}")
    finally:
        # Guarantee connections are closed regardless of what happens
        try:
            if cur:
                cur.close()
                logging.info("Database cursor closed")
        except Exception as e:
            logging.error(f"Error closing cursor: {str(e)}")
        
        try:
            if conn:
                conn.close()
                logging.info("Database connection closed")
        except Exception as e:
            logging.error(f"Error closing connection: {str(e)}")
        
        logging.info("Indexer shutdown complete")
