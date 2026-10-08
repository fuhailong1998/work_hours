#!/usr/bin/env python3
"""Read the current OA user's personal hours report over HTTP."""
import argparse
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
from urllib.parse import urlsplit

from html.parser import HTMLParser
from oa_http import get_session
from work_calendar import annotate_calendar

REPORT = "https://i.thundersoft.com/ThunderSoft/proj/working/PrjWorkingReport2.jsp"



class ReportTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.stack = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.stack.append({'rows': [], 'row': None, 'cell': None})
        elif self.stack:
            table = self.stack[-1]
            if tag == 'tr': table['row'] = []
            if tag in ('td','th'): table['cell'] = []

    def handle_data(self, data):
        self.text.append(data)
        if self.stack and self.stack[-1]['cell'] is not None:
            self.stack[-1]['cell'].append(data)

    def handle_endtag(self, tag):
        if not self.stack: return
        table = self.stack[-1]
        if tag in ('td','th') and table['cell'] is not None:
            if table['row'] is not None: table['row'].append(''.join(table['cell']).strip())
            table['cell'] = None
        elif tag == 'tr' and table['row'] is not None:
            table['rows'].append(table['row']);table['row'] = None
        elif tag == 'table':
            self.tables.append(self.stack.pop()['rows'])


def query_report(client, start, end, project, expected_employee=None):
    if start > end or (end-start).days > 366:
        raise ValueError("请选择不超过一年的有效日期范围")
    client = client if hasattr(client, 'identity') else get_session()
    identity = client.identity()
    if expected_employee and identity['id'] != str(expected_employee):
        raise ValueError("OA 当前账号与工作台账号不一致，请切回正确账号")
    response = client.request('GET', urlsplit(REPORT).path,
                              params={'resSDate':start.isoformat(),'resEDate':end.isoformat()})
    parser = ReportTables();parser.feed(response.text)
    if f'{start.isoformat()}至{end.isoformat()}人员工时报表' not in ''.join(parser.text):
        raise ValueError('报表日期与查询范围不一致，或 OA 会话已失效')
    matches = [rows for rows in parser.tables if rows and rows[0] and rows[0][0] == '项目名称']
    if len(matches) != 1:
        raise ValueError('OA 工时报表结构发生变化')
    result = parse_report(matches[0],start,end,project)
    result.update(queried_at=datetime.now().astimezone().isoformat(), source=response.url,
                  employee=identity, identity_scope='verified OA HTTP session user')
    return annotate_calendar(result)


def parse_report(rows, start, end, project):
    if not rows or not rows[0] or rows[0][0] != "项目名称" or rows[0][-1] != "合计":
        raise ValueError("Unexpected report header; not a valid hours report")
    header = rows[0]
    if len(set(header)) != len(header):
        raise ValueError("Duplicate project headers require manual resolution")
    daily = []
    total = None
    seen = set()
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError("Report column count changed")
        values = [Decimal(x) for x in row[1:]]
        if not all(x.is_finite() for x in values):
            raise ValueError("Non-finite hours")
        if sum(values[:-1], Decimal(0)) != values[-1]:
            raise ValueError("Daily project sum does not match total")
        if row[0] == "合计":
            if total is not None:
                raise ValueError("Duplicate totals row")
            total = values
            continue
        day = date.fromisoformat(row[0])
        if not start <= day <= end or day in seen:
            raise ValueError("Out-of-range or duplicate date")
        seen.add(day)
        daily.append({"date": row[0], "hours": dict(zip(header[1:], map(str, values)))})
    if len(seen) != (end - start).days + 1 or total is None:
        raise ValueError("Report is incomplete")
    for i, name in enumerate(header[1:]):
        if sum((Decimal(r["hours"][name]) for r in daily), Decimal(0)) != total[i]:
            raise ValueError("Report column total mismatch")
    candidates = [{"date": r["date"], "hours": r["hours"][project]}
                  for r in daily if project in r["hours"] and Decimal(r["hours"][project]) > 0]
    return {"start_date": start.isoformat(), "end_date": end.isoformat(),
            "public_project": project, "public_project_present": project in header,
            "project_totals": dict(zip(header[1:], map(str, total))),
            "daily": daily, "public_hours_candidates": candidates,
            "pending_adjustments_checked": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--public-project", required=True,
                        help="The current employee's confirmed public-hours project")
    parser.add_argument("--output", default=".local/oa/hours.json")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("start must not be later than end")
    result = query_report(get_session(), args.start, args.end, args.public_project)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding='utf-8')
    path.chmod(0o600)
    print(json.dumps({k: v for k, v in result.items() if k != "daily"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
