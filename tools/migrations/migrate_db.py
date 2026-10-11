import sqlite3
import sys

def migrate():
    print("Connecting to db...")
    conn = sqlite3.connect('instance/school.db')
    try:
        conn.execute('ALTER TABLE school_settings ADD COLUMN primary_color VARCHAR(20) DEFAULT "#0d6efd"')
        print("Added primary_color")
    except sqlite3.OperationalError as e:
        print(f"primary_color error: {e}")
        
    try:
        conn.execute('ALTER TABLE school_settings ADD COLUMN secondary_color VARCHAR(20) DEFAULT "#6c757d"')
        print("Added secondary_color")
    except sqlite3.OperationalError as e:
        print(f"secondary_color error: {e}")
        
    conn.commit()
    conn.close()
    print("Done")

if __name__ == '__main__':
    migrate()
