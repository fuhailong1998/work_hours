"""Mainland China working days, including official compensatory working weekends."""
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

DATA=Path(__file__).resolve().parent/'data/holidays'


def available_years():
    """Configured calendar years. Data is published yearly and must be added by hand."""
    return sorted(int(path.stem) for path in DATA.glob('*.json') if path.stem.isdigit())


def annotate_calendar(report, today=None):
    today=today or datetime.now(ZoneInfo('Asia/Shanghai')).date()
    years={date.fromisoformat(row['date']).year for row in report['daily']}
    calendars={}
    for year in years:
        path=DATA/f'{year}.json'
        if path.exists():
            data=json.loads(path.read_text(encoding='utf-8'))
            calendars[year]={item['date']:item for item in data['days']}
    unknown=[]
    for row in report['daily']:
        day=date.fromisoformat(row['date']);entry=calendars.get(day.year,{}).get(row['date'])
        if day.year not in calendars:
            row['calendar']={'known':False,'label':'年度日历未配置','required_hours':None,'missing_hours':None}
            unknown.append(day.year);continue
        working=not entry['isOffDay'] if entry else day.weekday()<5
        label=(entry['name']+('·放假' if entry['isOffDay'] else '·调休补班')) if entry else ('工作日' if working else '周末休息')
        required=Decimal(8 if working else 0)
        missing=max(Decimal(0),required-Decimal(row['hours']['合计'])) if day<=today else Decimal(0)
        row['calendar']={'known':True,'label':label,'working':working,'future':day>today,
                         'required_hours':str(required),'missing_hours':str(missing)}
    report['calendar_info']={'daily_required_hours':8,'unknown_years':sorted(set(unknown)),
                             'available_years':available_years(),
                             'rule':'中国大陆法定节假日及调休；普通工作日 8 小时，未来日期不计缺填'}
    return report
