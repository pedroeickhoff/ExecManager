# db.py
import pymysql
import threading

_DB_CFG = dict(
    host="127.0.0.1",
    user="execenv",
    password="execenvpwd",
    database="execenv",
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
)

_local = threading.local()

def get_conn():
    conn = getattr(_local, "conn", None)
    if conn is None or not conn.open:
        conn = pymysql.connect(**_DB_CFG)
        _local.conn = conn
    return conn

def query(sql, args=None):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
        return cur.fetchall()

def execute(sql, args=None):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, args or ())
    return True

def executemany(sql, seq):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.executemany(sql, seq or [])
    return True
