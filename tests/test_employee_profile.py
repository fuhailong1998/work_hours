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
                self.assertEqual(first['public_project'],'')
                server.write_json(server.PROFILE_FILE,dict(first,public_project='PUBLIC_A'))
                server.write_json(server.REPORT_FILE,{'employee':{'id':'1'},'daily':[]})
                guest=server.deactivate_employee()
                self.assertEqual(guest['id'],'')
                self.assertEqual(server.load(server.PROFILE_FILE,{})['public_project'],'')
                self.assertFalse(server.REPORT_FILE.exists())
                server.deactivate_employee()
                second=server.store_employee(b)
                self.assertEqual(second['public_project'],'')
                self.assertFalse(server.REPORT_FILE.exists())
                again=server.store_employee(a)
                self.assertEqual(again['public_project'],'PUBLIC_A')
                self.assertEqual(server.load(server.REPORT_FILE,{})['employee']['id'],'1')

    def test_default_has_no_hardcoded_identity(self):
        self.assertEqual(server.DEFAULT_PROFILE['id'],'')
        self.assertEqual(server.DEFAULT_PROFILE['employee_code'],'')
        self.assertEqual(server.DEFAULT_PROFILE['public_project'],'')
