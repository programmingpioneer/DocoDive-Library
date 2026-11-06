"""Small transaction boundary shared by security and account lifecycle services."""

from contextlib import contextmanager


class Store:
    def __init__(self, mysql):
        self.mysql = mysql

    @contextmanager
    def transaction(self):
        connection = self.mysql.connection
        connection.start_transaction()
        cursor = connection.cursor()
        try:
            yield cursor
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()

    def query(self, sql, args=(), one=False):
        cursor = self.mysql.connection.cursor()
        try:
            cursor.execute(sql, args)
            return cursor.fetchone() if one else cursor.fetchall()
        finally:
            cursor.close()
