import unittest
from datetime import date
from work_calendar import annotate_calendar

class CalendarTests(unittest.TestCase):
    def test_holidays_working_weekends_partial_and_future(self):
        rows=[('2026-09-19','0'),('2026-09-20','0'),('2026-09-21','3'),('2026-09-25','0'),('2026-09-30','0'),('2026-10-10','0'),('2030-01-02','0')]
        report={'daily':[{'date':day,'hours':{'合计':hours}} for day,hours in rows]}
        annotate_calendar(report,today=date(2026,9,29))
        actual={r['date']:r['calendar'] for r in report['daily']}
        self.assertEqual(actual['2026-09-19']['missing_hours'],'0')
        self.assertEqual(actual['2026-09-20']['missing_hours'],'8')
        self.assertEqual(actual['2026-09-21']['missing_hours'],'5')
        self.assertEqual(actual['2026-09-25']['missing_hours'],'0')
        self.assertEqual(actual['2026-09-30']['missing_hours'],'0')
        self.assertTrue(actual['2026-10-10']['working'])
        self.assertIsNone(actual['2030-01-02']['missing_hours'])
        self.assertEqual(report['calendar_info']['unknown_years'],[2030])
