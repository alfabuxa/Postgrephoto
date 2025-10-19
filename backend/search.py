import psycopg2

# --- PostgreSQL connection setup ---
conn = psycopg2.connect(
    dbname="photodb",
    user="alf",
    password="yourpassword",  # leave blank if using trust auth
    host="localhost"
)
cur = conn.cursor()


def search_by_type(filetype):
    """Find all files matching a given file extension (e.g., '.jpg')."""
    query = """
        SELECT filename, path, size_mb, modified
        FROM files
        WHERE filetype = %s
        ORDER BY modified DESC;
    """
    cur.execute(query, (filetype,))
    results = cur.fetchall()
    print(f"\nFound {len(results)} file(s) with type {filetype}:")
    for row in results[:50]:  # show first 50 for readability
        print(f"{row[0]} — {row[1]} — {row[2]} MB — {row[3]}")


def search_by_keyword(keyword):
    """Search for files where path contains a keyword."""
    query = """
        SELECT filename, path, size_mb, modified
        FROM files
        WHERE path ILIKE %s
        ORDER BY modified DESC;
    """
    cur.execute(query, (f"%{keyword}%",))
    results = cur.fetchall()
    print(f"\nFound {len(results)} file(s) containing '{keyword}':")
    for row in results[:50]:
        print(f"{row[0]} — {row[1]} — {row[2]} MB — {row[3]}")


def search_large_files(min_size_mb):
    """Find files larger than a specified size."""
    query = """
        SELECT filename, path, size_mb, modified
        FROM files
        WHERE size_mb >= %s
        ORDER BY size_mb DESC;
    """
    cur.execute(query, (min_size_mb,))
    results = cur.fetchall()
    print(f"\nFound {len(results)} file(s) larger than {min_size_mb} MB:")
    for row in results[:50]:
        print(f"{row[0]} — {row[1]} — {row[2]} MB — {row[3]}")


# --- Simple interactive CLI ---
def main():
    print("\n🔍 PostgreSQL Photo Search")
    print("1. Search by file type (e.g. .jpg)")
    print("2. Search by keyword in path")
    print("3. Search by minimum file size")
    print("4. Exit")

    choice = input("\nChoose an option (1-4): ").strip()

    if choice == "1":
        ext = input("Enter file extension (e.g. .jpg): ").strip().lower()
        search_by_type(ext)
    elif choice == "2":
        kw = input("Enter keyword to search in path: ").strip()
        search_by_keyword(kw)
    elif choice == "3":
        size = float(input("Enter minimum file size in MB: ").strip())
        search_large_files(size)
    elif choice == "4":
        print("Goodbye!")
        return
    else:
        print("Invalid choice.")

    # Loop again
    main()


if __name__ == "__main__":
    main()
    cur.close()
    conn.close()
