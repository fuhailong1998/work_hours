import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server

class EmployeeProfileTests(unittest.TestCase):
    def test_new_employee_does_not_inherit_previous_configuration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(server,'LOCAL',root),patch.object(server,'PROFILE_FILE',root/'profile.json'),patch.object(server,'REPORT_FILE',root/'hours.json'):
                a={'id':'1','name':'甲','employee_code':'A','department':'研发'}
                b={'id':'2','name':'乙','employee_code':'B','department':'产品'}
                first=server.store_employee(a)
                self.assertEqual(first['public_project'],'OS_AIOS_2026')
                server.write_json(server.PROFILE_FILE,dict(first,public_project='PUBLIC_A'))
                server.write_json(server.REPORT_FILE,{'employee':{'id':'1'},'daily':[]})
                guest=server.deactivate_employee()
                self.assertEqual(guest['id'],'')
                self.assertEqual(server.load(server.PROFILE_FILE,{})['public_project'],'OS_AIOS_2026')
                self.assertFalse(server.REPORT_FILE.exists())
                server.deactivate_employee()
                second=server.store_employee(b)
                self.assertEqual(second['public_project'],'OS_AIOS_2026')
                self.assertFalse(server.REPORT_FILE.exists())
                again=server.store_employee(a)
                self.assertEqual(again['public_project'],'PUBLIC_A')
                self.assertEqual(server.load(server.REPORT_FILE,{})['employee']['id'],'1')

    def test_default_has_no_hardcoded_identity(self):
        self.assertEqual(server.DEFAULT_PROFILE['id'],'')
        self.assertEqual(server.DEFAULT_PROFILE['employee_code'],'')
        self.assertEqual(server.DEFAULT_PROFILE['public_project'],'OS_AIOS_2026')

    def test_existing_empty_profile_uses_default_and_preserves_custom_project(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profile.json'
            server.write_json(path,dict(server.DEFAULT_PROFILE,public_project=''))
            self.assertEqual(server.load(path,server.DEFAULT_PROFILE)['public_project'],'OS_AIOS_2026')
            server.write_json(path,dict(server.DEFAULT_PROFILE,public_project='CUSTOM'))
            self.assertEqual(server.load(path,server.DEFAULT_PROFILE)['public_project'],'CUSTOM')


class PublicProjectSetupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        for name, path in [('LOCAL', self.root), ('PROFILE_FILE', self.root/'profile.json'),
                           ('REPORT_FILE', self.root/'hours.json')]:
            patcher = patch.object(server, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.employee = {'id': '1', 'name': '甲', 'employee_code': 'A', 'department': '研发'}

    def test_confirmation_and_edits_persist_per_employee(self):
        first = server.store_employee(self.employee)
        self.assertFalse(first['public_project_confirmed'])
        saved = server.save_public_project('  PUBLIC_A  ')
        self.assertTrue(saved['public_project_confirmed'])
        self.assertEqual(saved['public_project'], 'PUBLIC_A')
        self.assertEqual(server.load(server.PROFILE_FILE, {}), saved)
        self.assertEqual(server.load(self.root/'employees/1/profile.json', {}), saved)
        server.deactivate_employee()
        self.assertEqual(server.store_employee(self.employee), saved)
        other = server.store_employee(dict(self.employee, id='2', name='乙'))
        self.assertFalse(other['public_project_confirmed'])
        self.assertEqual(other['public_project'], 'OS_AIOS_2026')
        server.store_employee(self.employee)
        edited = server.save_public_project('PUBLIC_B')
        server.deactivate_employee()
        self.assertEqual(server.store_employee(self.employee), edited)

    def test_legacy_project_is_preserved_until_confirmation(self):
        server.write_json(server.PROFILE_FILE, dict(self.employee, public_project='EXISTING'))
        restored = server.store_employee(self.employee)
        self.assertEqual(restored['public_project'], 'EXISTING')
        self.assertFalse(restored['public_project_confirmed'])
        self.assertTrue(server.save_public_project('EXISTING')['public_project_confirmed'])

    def test_invalid_names_do_not_confirm_or_replace_profile(self):
        original = server.store_employee(self.employee)
        for name in ['', '  ', 'a'*181, None, 123, []]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                server.save_public_project(name)
            self.assertEqual(server.load(server.PROFILE_FILE, {}), original)

    def test_guest_cannot_save_a_project(self):
        with self.assertRaises(server.OAAuthRequired):
            server.save_public_project('PUBLIC')
        self.assertFalse(server.PROFILE_FILE.exists())
