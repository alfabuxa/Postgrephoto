import os
import psycopg2
from datetime import datetime
from pathlib import Path

# 1️⃣ Connect to PostgreSQL (basic connection)
conn = psycopg2.connect(
    dbname="photodb",
    user="alf",
    password="yourpassword",  # leave blank if using trust auth
    host="localhost"
)
cur = conn.cursor()

# 2️⃣ Make sure the table exists
cur.execute("""
CREATE TABLE IF NOT EXISTS files_simple (
    id SERIAL PRIMARY KEY,
    filename TEXT,
    path TEXT,
    filetype TEXT,
    size_mb REAL,
    modified TIMESTAMP
);
""")
conn.commit()

# 3️⃣ Ask user for folder
folder_path = "/home/rog/Desktop/photos"
if not os.path.exists(folder_path):
    print("❌ Folder not found.")
    exit()

# 4️⃣ Scan everything and store results in a Python list
file_data = []

for root, _, files in os.walk(folder_path):
    for file in files:
        full_path = os.path.join(root, file)
        try:
            stat = os.stat(full_path)
            file_info = (
                file,                                # filename
                full_path,                           # path
                Path(file).suffix.lower(),           # extension
                round(stat.st_size / (1024 * 1024), 2),  # MB
                datetime.fromtimestamp(stat.st_mtime)   # modified time
            )
            file_data.append(file_info)
        except (OSError, PermissionError):
            continue

print(f"Scanned {len(file_data)} files, inserting into database...")

# 5️⃣ Insert every file one by one
for f in file_data:
    cur.execute("""
        INSERT INTO files_simple (filename, path, filetype, size_mb, modified)
        VALUES (%s, %s, %s, %s, %s);
    """, f)

conn.commit()
cur.close()
conn.close()

print("✅ Done! All files inserted.")
