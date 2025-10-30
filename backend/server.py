from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB connection
conn = psycopg2.connect(
    dbname="photodb",
    user="alf",
    password="yourpassword",
    host="localhost"
)
cur = conn.cursor()

@app.get("/photos")
def get_photos(offset: int = 0, limit: int = 30):
    cur.execute("""
        SELECT id, path 
        FROM files
        WHERE filetype IN ('.jpg', '.jpeg', '.png', '.heic', '.heif', '.dng')
        ORDER BY id
        LIMIT %s OFFSET %s
    """, (limit, offset))
    
    results = cur.fetchall()
    return [{"id": r[0], "path": r[1]} for r in results]
