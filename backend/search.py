import psycopg2

# --- PostgreSQL connection setup ---
conn = psycopg2.connect(
    dbname="photodb",
    user="alf",
    password="yourpassword",  # leave blank if using trust auth
    host="localhost"
)
cur = conn.cursor()


def get_valid_float(prompt, min_value=0):
    """Prompt for a valid float input with validation and reprompting."""
    while True:
        try:
            user_input = input(prompt).strip()
            if not user_input:
                print("Error: Input cannot be empty. Please try again.")
                continue
            
            value = float(user_input)
            if value < min_value:
                print(f"Error: Value must be >= {min_value}. Please try again.")
                continue
            
            return value
        except ValueError:
            print("Error: Please enter a valid number. Please try again.")
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return None


def get_non_empty_input(prompt):
    """Prompt for non-empty string input with validation and reprompting."""
    while True:
        try:
            user_input = input(prompt).strip()
            if not user_input:
                print("Error: Input cannot be empty. Please try again.")
                continue
            return user_input
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            return None


def search_by_type(filetype):
    """Find all files matching a given file extension (e.g., '.jpg')."""
    if not filetype:
        print("Error: File extension cannot be empty.")
        return
    
    query = """
        SELECT filename, path, size_mb, modified
        FROM files
        WHERE filetype = %s
        ORDER BY modified DESC;
    """
    try:
        cur.execute(query, (filetype,))
        results = cur.fetchall()
        print(f"\nFound {len(results)} file(s) with type {filetype}:")
        for row in results[:50]:  # show first 50 for readability
            print(f"{row[0]} — {row[1]} — {row[2]} MB — {row[3]}")
    except Exception as e:
        print(f"Error executing search: {e}")


def search_by_keyword(keyword):
    """Search for files where path contains a keyword."""
    if not keyword:
        print("Error: Keyword cannot be empty.")
        return
    
    query = """
        SELECT filename, path, size_mb, modified
        FROM files
        WHERE path ILIKE %s
        ORDER BY modified DESC;
    """
    try:
        cur.execute(query, (f"%{keyword}%",))
        results = cur.fetchall()
        print(f"\nFound {len(results)} file(s) containing '{keyword}':")
        for row in results[:50]:
            print(f"{row[0]} — {row[1]} — {row[2]} MB — {row[3]}")
    except Exception as e:
        print(f"Error executing search: {e}")


def search_large_files(min_size_mb):
    """Find files larger than a specified size."""
    query = """
        SELECT filename, path, size_mb, modified
        FROM files
        WHERE size_mb >= %s
        ORDER BY size_mb DESC;
    """
    try:
        cur.execute(query, (min_size_mb,))
        results = cur.fetchall()
        print(f"\nFound {len(results)} file(s) larger than {min_size_mb} MB:")
        for row in results[:50]:
            print(f"{row[0]} — {row[1]} — {row[2]} MB — {row[3]}")
    except Exception as e:
        print(f"Error executing search: {e}")


# --- Simple interactive CLI ---
def main():
    while True:
        print("\n🔍 PostgreSQL Photo Search")
        print("1. Search by file type (e.g. .jpg)")
        print("2. Search by keyword in path")
        print("3. Search by minimum file size")
        print("4. Exit")

        try:
            choice = input("\nChoose an option (1-4): ").strip()

            if choice == "1":
                ext = get_non_empty_input("Enter file extension (e.g. .jpg): ")
                if ext is not None:  # Check if user didn't cancel
                    search_by_type(ext.lower())
            elif choice == "2":
                kw = get_non_empty_input("Enter keyword to search in path: ")
                if kw is not None:  # Check if user didn't cancel
                    search_by_keyword(kw)
            elif choice == "3":
                size = get_valid_float("Enter minimum file size in MB: ", min_value=0)
                if size is not None:  # Check if user didn't cancel
                    search_large_files(size)
            elif choice == "4":
                print("Goodbye!")
                break  # Break cleanly from the while loop
            else:
                print("Invalid choice. Please select 1-4.")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break  # Break cleanly from the while loop
        except Exception as e:
            print(f"Unexpected error: {e}")
            print("Returning to main menu...")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Critical error: {e}")
    finally:
        # Guarantee connections are closed
        try:
            if cur:
                cur.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass
