import sqlite3
import tempfile
import unittest
from pathlib import Path
from tools.backup_database import snapshot

class Backup(unittest.TestCase):
    def test_backup_restore_integrity_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            a,b,c=[Path(d)/n for n in ('original.db','backup.db','restored.db')]
            con=sqlite3.connect(a);con.execute('CREATE TABLE sample (value TEXT)');con.execute("INSERT INTO sample VALUES ('test-record')");con.commit();con.close()
            snapshot(a,b);snapshot(b,c)
            con=sqlite3.connect(c)
            try:self.assertEqual(con.execute('SELECT value FROM sample').fetchone()[0],'test-record')
            finally:con.close()
            with self.assertRaises(FileExistsError):snapshot(b,c)

if __name__=='__main__':unittest.main()
