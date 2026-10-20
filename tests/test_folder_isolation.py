import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


class FolderIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.env = patch.dict(os.environ, {'AXEL_DATA_DIR': cls.temp.name, 'AXEL_REQUIRE_DATA_DIR': '1', 'AXEL_DISABLE_LEGACY_MIGRATION': '1'})
        cls.env.start()
        sys.modules.pop('axel_ghl21', None)
        cls.module = importlib.import_module('axel_ghl21')
        cls.module.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.client = self.module.app.test_client()
        self.original = {'label': 'Antiga', 'location_id': 'old-location', **self.config('old-location')}
        self.module.save_subaccounts({'antiga': self.original})
        self.network = patch('requests.sessions.Session.request', side_effect=AssertionError('Real GHL calls are forbidden'))
        self.mock_network = self.network.start()
        self.addCleanup(self.network.stop)

    @staticmethod
    def config(location):
        return {key: f'https://example.test/locations/{location}/folders' for key in ('folder_create_url', 'folder_list_url', 'folder_delete_url')}

    def save(self, **data):
        return self.client.post('/api/save-subaccount', json=data)

    def test_new_account_discards_stale_folder_fields(self):
        response = self.save(label='Nova', location_id='new-location', **self.config('old-location'))
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertTrue(result['needs_folder_endpoints'])
        for field in self.config('old-location'):
            self.assertEqual(result['subaccount'][field], '')
        stored = self.module.load_subaccounts()
        self.assertEqual(stored['antiga'], self.original)
        self.assertFalse(stored['nova']['folder_endpoints_configured'])
        self.assertEqual(self.module.load_creds()['location_id'], 'new-location')
        self.assertEqual(self.module.load_creds()['folder_list_url'], '')

    def test_metadata_save_preserves_existing_account_endpoints(self):
        response = self.save(label='Antiga', location_id='old-location', **self.config('other-location'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.module.load_subaccounts()['antiga'], self.original)

    def test_changing_existing_location_resets_its_folder_configuration(self):
        response = self.save(label='Antiga', location_id='new-location')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['subaccount']['folder_list_url'], '')
        self.assertTrue(response.get_json()['needs_folder_endpoints'])

    def test_explicit_endpoint_save_rejects_another_location(self):
        self.save(label='Nova', location_id='new-location')
        before = self.module.load_subaccounts()
        response = self.save(label='Nova', location_id='new-location', save_endpoints=True, **self.config('old-location'))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['ok'])
        self.assertEqual(self.module.load_subaccounts(), before)

    def test_explicit_valid_endpoints_complete_only_their_own_account(self):
        self.save(label='Nova', location_id='new-location')
        response = self.save(label='Nova', location_id='new-location', save_endpoints=True, **self.config('new-location'))
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertFalse(result['needs_folder_endpoints'])
        self.assertTrue(result['subaccount']['folder_endpoints_configured'])
        self.assertEqual(self.module.load_subaccounts()['antiga'], self.original)

    def test_pending_folder_operations_never_reach_ghl(self):
        self.save(label='Nova', location_id='new-location')
        payload = {'location_id': 'new-location', 'auth_token': 'fake-token', 'token_id': 'fake-id', 'name': 'Folder', 'folder_id': 'folder', 'id': 'template', **self.config('new-location')}
        for route in ('list-folders', 'create-folder', 'delete-folder', 'move-template'):
            with self.subTest(route=route):
                response = self.client.post('/api/' + route, json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn('endpoints', response.get_json()['msg'])
        self.mock_network.assert_not_called()

    def test_foreign_folder_request_rejected_before_network(self):
        payload = {'location_id': 'old-location', 'auth_token': 'fake-token', 'token_id': 'fake-id', **self.config('new-location')}
        response = self.client.post('/api/list-folders', json=payload)
        self.assertEqual(response.status_code, 400)
        self.mock_network.assert_not_called()

    def test_placeholder_urls_and_legacy_records_remain_usable(self):
        cfg = self.config('{location_id}')
        self.assertEqual(self.module.folder_config_issue(cfg, 'new-location', self.module.load_subaccounts()), '')
        response = self.save(label='Nova', location_id='new-location', save_endpoints=True, **cfg)
        self.assertEqual(response.status_code, 200)
        legacy_cfg = self.module.folder_config_from_request({'location_id': 'old-location', **self.config('old-location')})
        self.assertEqual(legacy_cfg['folder_list_url'], self.original['folder_list_url'])

    def test_query_location_mismatch_is_rejected(self):
        cfg = self.config('new-location')
        cfg['folder_list_url'] = 'https://example.test/folders?altId=old-location'
        self.assertIn('outro Location ID', self.module.folder_config_issue(cfg, 'new-location', self.module.load_subaccounts()))

    def test_switching_saved_account_restores_only_its_own_configuration(self):
        self.save(label='Nova', location_id='new-location')
        response = self.client.post('/api/set-active-subaccount', json={'key': 'antiga'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.module.load_creds()['folder_list_url'], self.original['folder_list_url'])
        response = self.client.post('/api/set-active-subaccount', json={'key': 'nova'})
        self.assertEqual(response.status_code, 200)
        creds = self.module.load_creds()
        self.assertEqual(creds['last_subaccount'], 'nova')
        self.assertEqual(creds['location_id'], 'new-location')
        self.assertEqual(creds['folder_list_url'], '')


if __name__ == '__main__':
    unittest.main()
