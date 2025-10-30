from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import psycopg2, mimetypes, urllib.parse, os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        SELECT DISTINCT ON (path) id, path
        FROM files
        ORDER BY path, id
        LIMIT %s OFFSET %s
    """, (limit, offset))
    results = cur.fetchall()
    return [{"id": r[0], "path": r[1]} for r in results]

@app.get("/file")
def get_file(path: str):
    decoded = urllib.parse.unquote(path)
    print("REQUESTED ->", decoded)

    if not os.path.exists(decoded):
        print("❌ Not found:", decoded)
        return Response(status_code=404)

    mime, _ = mimetypes.guess_type(decoded)
    return FileResponse(decoded, media_type=mime or "application/octet-stream")
