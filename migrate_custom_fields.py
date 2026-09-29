import sqlite3
import sys

def migrate():
    print("Connecting to db...")
    conn = sqlite3.connect('instance/school.db')
    try:
        conn.execute('ALTER TABLE students ADD COLUMN custom_fields_data TEXT')
        print("Added custom_fields_data to students")
    except sqlite3.OperationalError as e:
        print(f"students error: {e}")
        
    try:
        conn.execute('ALTER TABLE teachers ADD COLUMN custom_fields_data TEXT')
        print("Added custom_fields_data to teachers")
    except sqlite3.OperationalError as e:
        print(f"teachers error: {e}")
        
    conn.commit()
    conn.close()
    print("Done")

if __name__ == '__main__':
    migrate()
