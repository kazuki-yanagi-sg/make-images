import sqlite3
original_connect = sqlite3.connect

def new_connect(database, *args, **kwargs):
    if database == ":memory:":
        database = "file:memdb1?mode=memory&cache=shared"
        kwargs["uri"] = True
    return original_connect(database, *args, **kwargs)

sqlite3.connect = new_connect
