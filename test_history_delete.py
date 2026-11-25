from test_client_helpers import browser_client, authenticated_session
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch
from bson import ObjectId

import app as chatbot


class DeleteHistory(unittest.TestCase):
    def test_requires_login_and_deletes_only_selected_users_row(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / 'history.db')
            with patch.object(chatbot, 'LOCAL_DB_FILE', db_path), patch.object(chatbot, 'chat_collection', None):
                chatbot.init_sqlite()
                with closing(sqlite3.connect(db_path)) as connection:
                    connection.executemany(
                        'INSERT INTO chat_history (username, question, answer) VALUES (?, ?, ?)',
                        [('alice', 'câu 1', 'đáp 1'), ('alice', 'câu 2', 'đáp 2'),
                         ('bob', 'câu 3', 'đáp 3')],
                    )
                    connection.commit()
                with browser_client(chatbot.app) as client:
                    self.assertEqual(client.delete('/api/history/s:1').status_code, 401)
                    with client.session_transaction() as session:
                        authenticated_session(chatbot.app, session, 'alice')
                    history = client.get('/api/history').get_json()['history']
                    self.assertEqual([item['id'] for item in history], ['s:1', 's:2'])
                    self.assertEqual(client.delete('/api/history/s:3').status_code, 404)
                    self.assertEqual(client.delete('/api/history/s:invalid').status_code, 404)
                    response = client.delete('/api/history/s:1')
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual([item['id'] for item in client.get('/api/history').get_json()['history']], ['s:2'])
                with closing(sqlite3.connect(db_path)) as connection:
                    self.assertEqual(connection.execute(
                        'SELECT username, question FROM chat_history ORDER BY id').fetchall(),
                        [('alice', 'câu 2'), ('bob', 'câu 3')])

    def test_mongo_deletion_matches_id_and_current_user(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = str(Path(directory) / 'history.db')
            collection = Mock()
            collection.delete_one.return_value.deleted_count = 1
            item_id = ObjectId()
            with patch.object(chatbot, 'LOCAL_DB_FILE', db_path), patch.object(chatbot, 'chat_collection', collection):
                chatbot.init_sqlite()
                self.assertTrue(chatbot.delete_chat_history_item_db('alice', 'm:' + str(item_id)))
                self.assertFalse(chatbot.delete_chat_history_item_db('alice', 'm:invalid'))
            collection.delete_one.assert_called_once_with({'_id': item_id, 'username': 'alice'})


if __name__ == '__main__':
    unittest.main()
