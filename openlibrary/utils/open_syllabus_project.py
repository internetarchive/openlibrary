import os
import json
import sqlite3
import gzip


# Define the SQLite database file path
# Usually placed in root OL directory
db_file = 'osp_totals.db'


# Function to get the total based on OLID
def get_total_by_olid(olid: str) -> int | None:
    """
    Retrieves the total number of times a book with the given Open Library ID (OLID) has been assigned in syllabi
    from the Open Syllabus Project database.

    :param olid: The Open Library ID (OLID) of the book to retrieve the total for. (eg `/works/OL123W` or `OL123W`)

    Raises:
        Exception: If there is an error querying the database.
    """

    olid_int = olid.replace("/works/", "").replace("OL", "").replace("W", "")
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()

        # Query the database for the total based on OLID
        cursor.execute("SELECT total FROM data WHERE olid = ?", (olid_int,))
        result = cursor.fetchone()

        if result:
            return result[0]

    except Exception as e:
        print(f"Error querying the database: {e}")
    finally:
        conn.close()
    return None


def generate_osp_db(input_directory: str) -> None:
    """
    This function generates an SQLite database from a directory of .json.gz files.
    The database contains data extracted from the JSON files, including the OLID and total fields.
    The function excludes lines where the 'total' is less than one.
    The function creates an index on the OLID column for faster querying.

    Args:
        input_directory (str): The directory containing the .json.gz files.

    Returns:
        None
    """

    # Initialize a list to store the data
    data = []

    # Create an SQLite database and table
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # Drop the table if it exists so we only have fresh data
    cursor.execute('DROP TABLE IF EXISTS data;')
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS data (
            olid INTEGER PRIMARY KEY,
            total INTEGER
        )
    '''
    )

    i = 0
    # Iterate through the files in the input directory
    for filename in os.listdir(input_directory):
        print(i)
        i += 1
        if filename.endswith(".json.gz"):
            with gzip.open(os.path.join(input_directory, filename), "rt") as file:
                for line in file:
                    try:
                        # Parse the JSON data
                        json_data = json.loads(line)

                        # Extract the 'ol_id' and 'total' fields
                        ol_id = int(
                            json_data["ol_id"].replace("/works/OL", "").replace("W", "")
                        )
                        total = json_data["total"]

                        # Exclude lines where the 'total' is less than one
                        if total >= 1:
                            data.append((ol_id, total))
                    except Exception as e:
                        print(f"Error processing {filename}: {e}")

    # Insert the filtered data into the SQLite database
    cursor.executemany("INSERT INTO data (olid, total) VALUES (?, ?)", data)

    # Commit changes, sort the olid column in ascending order, and close the database connection
    cursor.execute("CREATE INDEX IF NOT EXISTS olid_index ON data (olid)")
    conn.commit()
    conn.close()

    print(f'SQLite database created successfully: {db_file}')
