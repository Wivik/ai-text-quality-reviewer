import sqlite3
from sqlite3.dbapi2 import Error
from datetime import datetime

## open the database connection
def get_db_connection(settings_file):
    conn = sqlite3.connect(settings_file)
    conn.row_factory = sqlite3.Row
    return conn

def run_db_change_query(settings_file, query, values):
    conn = get_db_connection(settings_file)
    try:
        conn.execute(query, values)
        conn.commit()
        conn.close()
        return
    except sqlite3.IntegrityError:
        return sqlite3.IntegrityError
    except sqlite3.Error as er:
        print(er)
        return er
    finally:
        if conn:
            conn.close()

def run_db_select_one_query(settings_file, query, values):
    conn = get_db_connection(settings_file)
    results = conn.execute(query, values).fetchone()
    conn.close()
    return results

def run_db_select_all_query(settings_file, query, values):
    conn = get_db_connection(settings_file)
    results = conn.execute(query, values).fetchall()
    conn.close()
    return results


def create_settings_database(settings_file):
    conn = None
    try:
        conn = sqlite3.connect(settings_file)
        c = conn.cursor()
        # Create the saves table
        c.execute('''
            CREATE TABLE "settings" (
                "key"	TEXT UNIQUE,
                "value"	TEXT,
                PRIMARY KEY("key")
            )
        ''')
        c.execute('''
            CREATE TABLE "prompts" (
                "id"	INTEGER,
                "request"	TEXT,
                "output"	TEXT,
                PRIMARY KEY("id" AUTOINCREMENT)
            )
        ''')



        conn.commit()
    except Error as e:
        print(e)
    finally:
        conn.close()

# def create_character(settings_file, character_name, gender):
#     now = datetime.utcnow()
#     iso8601 = now.isoformat()
#     date_create = iso8601
#     date_update = iso8601
#     ret = run_db_change_query(settings_file, 'INSERT INTO saves (name, gender, date_create, date_update) VALUES(?, ?, ?, ?)', (character_name, gender, date_create, date_update))
#     if ret is None:
#         return
#     else:
#         return ret

def get_all_prompts(settings_file):
    ret = run_db_select_all_query(settings_file, 'SELECT * FROM prompts ORDER BY ID DESC', '')
    if ret is None:
        return
    else:
        return ret

def get_setting(settings_file, settings_key, default_value):
    ret = run_db_select_one_query(settings_file, 'SELECT value FROM settings WHERE key = ?', (settings_key,))
    if ret is None:
        return default_value
    else:
        return ret['value']

def register_setting(settings_file, settings_key, settings_value):
    ret = run_db_change_query(settings_file, 'INSERT OR REPLACE INTO settings (key, value) VALUES(?, ?)', (settings_key, settings_value))
    if ret is None:
        return
    else:
        return ret

def insert_prompt(settings_file, prompt, result):
    print(prompt)
    print(result)
    ret = run_db_change_query(settings_file, 'INSERT INTO prompts (request, output) VALUES(?, ?)', (prompt, result))
    if ret is None:
        return
    else:
        return ret

def get_latest_prompt(settings_file):
    ret = run_db_select_one_query(settings_file, 'SELECT * FROM prompts ORDER BY id DESC LIMIT 1', '')
    if ret is None:
        return default_value
    else:
        return ret

def get_prompt(settings_file, prompt_id):
    ret = run_db_select_one_query(settings_file, 'SELECT * FROM prompts WHERE id = ?', (prompt_id,))
    if ret is None:
        return default_value
    else:
        return ret
