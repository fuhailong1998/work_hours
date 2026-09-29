import copy
from datetime import date
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from query_hours import parse_report
from server import report_id, validate_plan
import server
from oa_draft import expand_rows


class PlanValidationTests(unittest.TestCase):
    def setUp(self):
        self.profile = {"id": "test-user", "name": "测试用户", "employee_code": "T1", "public_project": "PUBLIC"}
        self.report = parse_report([
            ["项目名称", "PUBLIC", "PROJECT", "合计"],
            ["2026-09-20", "0", "8", "8"],  # Worked Sunday must remain in report.
            ["2026-09-21", "8", "0", "8"],
            ["合计", "8", "8", "16"],
        ], date(2026, 9, 20), date(2026, 9, 21), "PUBLIC")
        self.body = {"report_id": report_id(self.report), "target_project": "PROJECT",
                     "reason": "测试本地计划", "rows": [{"date": "2026-09-21", "hours": "4"}]}

    def test_only_public_hours_are_candidates(self):
        self.assertEqual(self.report["public_hours_candidates"], [{"date": "2026-09-21", "hours": "8"}])
        self.assertEqual(self.report["daily"][0]["hours"]["PROJECT"], "8")

    def test_non_public_source_and_public_destination(self):
        body=dict(self.body,source_project='PROJECT',target_project='PUBLIC',rows=[{'date':'2026-09-20','hours':'6'}])
        plan=validate_plan(body,self.report,self.profile)
        self.assertEqual(plan['source_project'],'PROJECT')
        self.assertEqual(plan['adjustments'][0]['source_project'],'PROJECT')
        self.assertEqual(expand_rows(plan)[0]['project'],'PROJECT')
        self.assertEqual(expand_rows(plan)[1]['project'],'PUBLIC')
        for patch in [dict(source_project='UNKNOWN'),dict(target_project='PROJECT'),dict(rows=[{'date':'2026-09-20','hours':'9'}]),dict(rows=[{'date':'2026-09-21','hours':'1'}])]:
            with self.assertRaises(ValueError):validate_plan(dict(body,**patch),self.report,self.profile)

    def test_multiple_sources_rounding_and_balance(self):
        report=parse_report([['项目名称','PUBLIC','PROJECT','合计'],['2026-09-21','3','5','8'],['合计','3','5','8']],date(2026,9,21),date(2026,9,21),'PUBLIC')
        body=dict(self.body,report_id=report_id(report),source_projects=['PUBLIC','PROJECT'],target_project='DEST',rows=[{'date':'2026-09-21','hours':'1.01'}])
        plan=validate_plan(body,report,self.profile)
        self.assertEqual({r['source_project']:r['hours'] for r in plan['source_withdrawals']},{'PUBLIC':'0.38','PROJECT':'0.63'})
        rows=expand_rows(plan)
        from decimal import Decimal
        self.assertEqual(sum(Decimal(r['hours']) for r in rows if r['direction']=='0'),Decimal('1.01'))
        for change in [dict(source_projects=[]),dict(target_project='PUBLIC'),dict(rows=[{'date':'2026-09-21','hours':'8.01'}])]:
            with self.assertRaises(ValueError):validate_plan(dict(body,**change),report,self.profile)

    def test_partial_transfer_preserves_amount(self):
        plan = validate_plan(self.body, self.report, self.profile)
        self.assertEqual(plan["total_hours"], "4")
        self.assertFalse(plan["oa_submitted"])
        self.assertFalse(plan["oa_project_id_resolved"])

    def test_reject_excess_invalid_or_negative_hours(self):
        for value in ["8.01", "0", "-1", "NaN", "Infinity", "abc"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                body = copy.deepcopy(self.body)
                body["rows"][0]["hours"] = value
                validate_plan(body, self.report, self.profile)

    def test_reject_non_public_date(self):
        self.body["rows"][0]["date"] = "2026-09-20"
        with self.assertRaises(ValueError):
            validate_plan(self.body, self.report, self.profile)

    def test_reject_duplicates(self):
        self.body["rows"] *= 2
        with self.assertRaises(ValueError):
            validate_plan(self.body, self.report, self.profile)

    def test_reject_stale_report(self):
        self.body["report_id"] = "old-snapshot"
        with self.assertRaises(ValueError):
            validate_plan(self.body, self.report, self.profile)

    def test_reject_profile_change(self):
        self.profile["public_project"] = "SOMEONE_ELSES_PUBLIC"
        with self.assertRaises(ValueError):
            validate_plan(self.body, self.report, self.profile)

    def test_reject_same_source_target(self):
        self.body["target_project"] = "PUBLIC"
        with self.assertRaises(ValueError):
            validate_plan(self.body, self.report, self.profile)

    def test_report_missing_dates_and_mismatched_totals(self):
        bad = [
            [["项目名称", "PUBLIC", "合计"], ["2026-09-20", "8", "8"], ["合计", "8", "8"]],
            [["项目名称", "PUBLIC", "合计"], ["2026-09-20", "8", "9"], ["合计", "8", "9"]],
        ]
        for rows in bad:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                parse_report(rows, date(2026, 9, 20), date(2026, 9, 21), "PUBLIC")

    def test_draft_expansion_balances_each_exact_date(self):
        plan = validate_plan(self.body, self.report, self.profile)
        rows = expand_rows(plan)
        self.assertEqual([(r["direction"], r["project"], r["hours"]) for r in rows],
                         [("0", "PUBLIC", "4"), ("1", "PROJECT", "4")])
        self.assertEqual({r["day"] for r in rows}, {"2026-09-21"})

    def test_multiple_targets_balance_and_order(self):
        self.body.pop("target_project")
        self.body["rows"] = [
            {"date": "2026-09-21", "hours": "3.25", "target_project": "SECOND"},
            {"date": "2026-09-21", "hours": "4.75", "target_project": "PROJECT"},
        ]
        plan = validate_plan(self.body, self.report, self.profile)
        self.assertEqual(plan["total_hours"], "8.00")
        self.assertEqual(plan["target_projects"], ["PROJECT", "SECOND"])
        self.assertEqual([(r["direction"], r["project"], r["hours"]) for r in expand_rows(plan)],
                         [("0", "PUBLIC", "8.00"), ("1", "PROJECT", "4.75"), ("1", "SECOND", "3.25")])
        self.body["rows"].reverse()
        self.assertEqual(server.draft_key(plan), server.draft_key(validate_plan(self.body, self.report, self.profile)))
        self.body["rows"][0]["hours"] = "4.76"
        with self.assertRaisesRegex(ValueError, "分配合计"):
            validate_plan(self.body, self.report, self.profile)

    def test_multiple_dates_keep_independent_balances(self):
        self.report["public_hours_candidates"].append({"date": "2026-09-22", "hours": "2"})
        self.body["report_id"] = report_id(self.report)
        self.body["rows"].extend([
            {"date": "2026-09-21", "hours": "4", "target_project": "SECOND"},
            {"date": "2026-09-22", "hours": "2", "target_project": "SECOND"},
        ])
        rows = expand_rows(validate_plan(self.body, self.report, self.profile))
        self.assertEqual([(r["day"], r["hours"]) for r in rows if r["direction"] == "0"],
                         [("2026-09-21", "8"), ("2026-09-22", "2")])
        self.body["rows"][-1]["hours"] = "3"
        with self.assertRaises(ValueError):
            validate_plan(self.body, self.report, self.profile)

    def test_draft_reuses_saved_result_and_blocks_uncertain_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            server.write_json(root / "profile.json", self.profile)
            server.write_json(root / "report.json", self.report)
            with patch.object(server, "LOCAL", root), patch.object(server, "PROFILE_FILE", root / "profile.json"), \
                 patch.object(server, "REPORT_FILE", root / "report.json"), \
                 patch.object(server, "query_report", return_value=self.report), \
                 patch.object(server, "create_draft") as create:
                result = {"request_id": "123", "url": "https://i.thundersoft.com/#/123", "oa_saved": True, "oa_submitted": False}
                def success(cdp, plan, before_save, saved, **kwargs):
                    before_save(); saved(result); return result
                create.side_effect = success
                self.assertEqual(server.make_draft(self.body, "local"), result)
                self.assertEqual(server.make_draft(self.body, "local"), result)
                self.assertEqual(create.call_count, 1)
                self.body["reason"] = "不同计划"
                def unknown(cdp, plan, before_save, saved, **kwargs):
                    before_save(); raise TimeoutError("save timeout")
                create.side_effect = unknown
                with self.assertRaisesRegex(ValueError, "保存结果尚未确认"):
                    server.make_draft(self.body, "local")
                with self.assertRaisesRegex(ValueError, "不会重复创建"):
                    server.make_draft(self.body, "local")
                self.assertEqual(create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
