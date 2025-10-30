import exif_utils
import os
import psycopg2
from datetime import datetime
from pathlib import Path
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('indexer.log'),
        logging.StreamHandler()
    ]
)

def initialize_database():
    """Initialize database connection and ensure database exists."""
    try:
        # First, try to connect to the specific database
        logging.info("Attempting to connect to photodb database...")
        conn = psycopg2.connect(
            dbname="photodb",
            user="alf",          
            password="yourpassword",         
            host="localhost"
        )
        logging.info("Successfully connected to photodb database")
        return conn
    except psycopg2.OperationalError as e:
        if "does not exist" in str(e).lower():
            logging.info("photodb database doesn't exist, creating it...")
            # Connect to default postgres database to create our database
            admin_conn = psycopg2.connect(
                dbname="postgres",
                user="alf",
                password="yourpassword",
                host="localhost"
            )
            admin_conn.autocommit = True
            admin_cur = admin_conn.cursor()
            
            try:
                admin_cur.execute("CREATE DATABASE photodb;")
                logging.info("Successfully created photodb database")
            except psycopg2.Error as create_error:
                if "already exists" in str(create_error).lower():
                    logging.info("Database already exists, continuing...")
                else:
                    raise
            finally:
                admin_cur.close()
                admin_conn.close()
            
            # Now connect to the newly created database
            conn = psycopg2.connect(
                dbname="photodb",
                user="alf",
                password="yourpassword",
                host="localhost"
            )
            logging.info("Connected to newly created photodb database")
            return conn
        else:
            raise

# Initialize database connection with performance tracking
db_init_start = time.time()
conn = initialize_database()
cur = conn.cursor()
db_init_time = time.time() - db_init_start
logging.info(f"Database initialization took {db_init_time:.3f} seconds")

# Create schema with performance tracking
schema_start = time.time()
logging.info("Setting up database schema...")

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
schema_time = time.time() - schema_start
logging.info(f"Database schema setup took {schema_time:.3f} seconds")

# Check existing database statistics
def log_database_stats():
    """Log current database statistics for performance baseline."""
    try:
        cur.execute("SELECT COUNT(*) FROM files;")
        result = cur.fetchone()
        file_count = result[0] if result else 0
        
        cur.execute("SELECT pg_size_pretty(pg_total_relation_size('files'));")
        result = cur.fetchone()
        table_size = result[0] if result else "Unknown"
        
        cur.execute("SELECT COUNT(DISTINCT filetype) FROM files;")
        result = cur.fetchone()
        unique_types = result[0] if result else 0
        
        logging.info(f"=== DATABASE STATISTICS ===")
        logging.info(f"Existing files in database: {file_count:,}")
        logging.info(f"Table size: {table_size}")
        logging.info(f"Unique file types: {unique_types}")
        
        if file_count > 0:
            cur.execute("SELECT MIN(modified), MAX(modified) FROM files WHERE modified IS NOT NULL;")
            date_range = cur.fetchone()
            if date_range and date_range[0] and date_range[1]:
                logging.info(f"Date range: {date_range[0]} to {date_range[1]}")
        
    except Exception as e:
        logging.warning(f"Could not retrieve database statistics: {e}")

log_database_stats()

# Folder to scan
FOLDER_PATH = "/mnt/data_smb/Photos"  # change to your target folder

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

def store_to_db(file_info, performance_stats):
    """Insert one file's metadata into PostgreSQL."""
    try:
        # Track EXIF extraction time
        exif_start = time.time()
        exif = exif_utils.extract_exif(file_info["path"])
        exif_time = time.time() - exif_start
        performance_stats['total_exif_time'] += exif_time
        
        camera_model = exif.get("Model")
        taken_at = exif.get("DateTimeOriginal")
        if isinstance(taken_at, str):
            try:
                taken_at = datetime.strptime(taken_at, "%Y:%m:%d %H:%M:%S")
            except ValueError:
                taken_at = None
        
        # Track database operation time
        db_start = time.time()
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
        db_time = time.time() - db_start
        performance_stats['total_db_time'] += db_time
        
        # Track slowest operations for debugging
        if exif_time > performance_stats['slowest_exif_time']:
            performance_stats['slowest_exif_time'] = exif_time
            performance_stats['slowest_exif_file'] = file_info['path']
        
        if db_time > performance_stats['slowest_db_time']:
            performance_stats['slowest_db_time'] = db_time
            performance_stats['slowest_db_file'] = file_info['path']
            
    except Exception as e:
        logging.error(f"Failed to store file {file_info['path']}: {str(e)}")
        raise

def get_all_db_paths():
    """Fetch all file paths currently in the database."""
    query_start = time.time()
    cur.execute("SELECT path FROM files;")
    result = {row[0] for row in cur.fetchall()}
    query_time = time.time() - query_start
    logging.info(f"Retrieved {len(result)} existing paths from database in {query_time:.3f}s")
    return result

def cleanup_removed_files(scanned_paths):
    """Remove files from database that are no longer found in the filesystem."""
    try:
        db_paths = get_all_db_paths()
        stale_paths = db_paths - scanned_paths

        if stale_paths:
            logging.info(f"Removing {len(stale_paths)} stale files from DB...")
            delete_start = time.time()
            cur.executemany("DELETE FROM files WHERE path = %s;", [(p,) for p in stale_paths])
            conn.commit()
            delete_time = time.time() - delete_start
            logging.info(f"Successfully removed {len(stale_paths)} stale files in {delete_time:.3f}s")
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
    
    # Initialize performance tracking
    performance_stats = {
        'total_exif_time': 0.0,
        'total_db_time': 0.0,
        'total_scan_time': 0.0,
        'slowest_exif_time': 0.0,
        'slowest_exif_file': '',
        'slowest_db_time': 0.0,
        'slowest_db_file': '',
        'commit_times': []
    }
    
    main_start_time = time.time()
    
    try:
        logging.info(f"Starting scan of folder: {FOLDER_PATH}")
        scan_start_time = time.time()
        
        for file_info in scan_folder(FOLDER_PATH):
            try:
                store_to_db(file_info, performance_stats)
                scanned_paths.add(file_info["path"])
                success_count += 1
                count += 1
                
                # Commit at consistent checkpoints with timing
                if count % 100 == 0:
                    commit_start = time.time()
                    conn.commit()
                    commit_time = time.time() - commit_start
                    performance_stats['commit_times'].append(commit_time)
                    
                    # Calculate averages for checkpoint logging
                    avg_exif_time = performance_stats['total_exif_time'] / success_count if success_count > 0 else 0
                    avg_db_time = performance_stats['total_db_time'] / success_count if success_count > 0 else 0
                    
                    logging.info(f"Checkpoint: Indexed {count} files (success: {success_count}, errors: {error_count})")
                    logging.info(f"  Avg EXIF time: {avg_exif_time*1000:.2f}ms, Avg DB time: {avg_db_time*1000:.2f}ms, Commit time: {commit_time*1000:.2f}ms")
                    
            except Exception as e:
                error_count += 1
                count += 1
                logging.error(f"Failed to process file {file_info['path']}: {str(e)}")
                # Roll back the failed transaction and continue
                conn.rollback()
                continue

        performance_stats['total_scan_time'] = time.time() - scan_start_time

        # Final commit with timing
        final_commit_start = time.time()
        conn.commit()
        final_commit_time = time.time() - final_commit_start
        performance_stats['commit_times'].append(final_commit_time)
        
        total_time = time.time() - main_start_time
        
        # Log comprehensive performance statistics
        logging.info(f"Scan complete. Total processed: {count}, Success: {success_count}, Errors: {error_count}")
        logging.info(f"=== PERFORMANCE STATISTICS ===")
        logging.info(f"Total execution time: {total_time:.3f}s")
        logging.info(f"Total scan time: {performance_stats['total_scan_time']:.3f}s")
        logging.info(f"Total EXIF extraction time: {performance_stats['total_exif_time']:.3f}s")
        logging.info(f"Total database operation time: {performance_stats['total_db_time']:.3f}s")
        
        if success_count > 0:
            logging.info(f"Average EXIF time per file: {(performance_stats['total_exif_time']/success_count)*1000:.2f}ms")
            logging.info(f"Average DB time per file: {(performance_stats['total_db_time']/success_count)*1000:.2f}ms")
            logging.info(f"Processing rate: {success_count/total_time:.1f} files/sec")
        
        if performance_stats['commit_times']:
            avg_commit_time = sum(performance_stats['commit_times']) / len(performance_stats['commit_times'])
            max_commit_time = max(performance_stats['commit_times'])
            logging.info(f"Average commit time: {avg_commit_time*1000:.2f}ms, Max commit time: {max_commit_time*1000:.2f}ms")
        
        logging.info(f"Slowest EXIF extraction: {performance_stats['slowest_exif_time']*1000:.2f}ms ({performance_stats['slowest_exif_file']})")
        logging.info(f"Slowest DB operation: {performance_stats['slowest_db_time']*1000:.2f}ms ({performance_stats['slowest_db_file']})")

        # Cleanup removed files
        cleanup_start = time.time()
        cleanup_removed_files(scanned_paths)
        cleanup_time = time.time() - cleanup_start
        logging.info(f"Cleanup took {cleanup_time:.3f}s")
        
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
