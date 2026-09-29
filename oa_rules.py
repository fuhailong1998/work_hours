"""Save-time rules observed on workflow 110092, for formal-employee detail_1 only.

These rules prepare routing fields for a draft. They never submit an approval.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def apply_save_rules(main, rows, today=None):
    today=today or datetime.now(ZoneInfo('Asia/Shanghai')).date()
    cycle=today.year*12+today.month-1+(today.day>=25)
    month=lambda n:f'{n//12:04d}-{n%12+1:02d}'
    current=month(cycle);previous={month(cycle-1),month(cycle-2)}
    # Match OA's own getlasWeek calculation (Sunday=0).
    cutoff=today-timedelta(days=(today.weekday()+1)%7+6)
    managers=[];copies=[];ams=[];bus=[];bds=[];groups=[];pmos=[]
    monthflag=weekflag=ifwlw=amsp=bdsp=busp=iot_cross=False
    def add(out,v):
        for item in v.split(','):
            if item and item not in out:out.append(item)
    def put(field,val):main['field'+field]={'value':val}
    for row in rows:
        get=lambda fid:str(row.get('field'+fid,{}).get('value',''))
        incoming=get('60578')=='1';bg=get('60588');project=get('61126')
        public_out=project.startswith('OS_') and not incoming
        add(copies if public_out else managers,get('60585'))
        rowmonth=get('60607') in previous
        rowweek=get('60607')==current and get('60580')<cutoff.isoformat()
        monthflag|=rowmonth;weekflag|=rowweek
        ifwlw|=bg!='23' and weekflag
        if rowmonth and bg in ('261','264','581'):add(groups,{'261':'1','264':'2','581':'3'}[bg])
        if bg=='30' and rowmonth and not public_out:
            add(ams,get('71074'));amsp=True
        if bg=='261' and rowmonth:add(bds,get('71088'))
        if ((rowweek and bg not in ('23','261')) or (rowmonth and bg not in ('30','23'))) and not public_out:
            add(bus,get('60969'))
        bdsp|=rowmonth and get('71085') in ('2621','2121','2122','2123','2124','2125')
        busp|=rowmonth and bg in ('261','264','581')
        if bg=='23' and incoming:
            iot_cross|=get('69951')!='23'
            add(pmos,get('70142'))
        row['field122708']={'value':'0' if incoming and bg=='30' and get('122710') in ('5','6') else '1'}
    put('80554',','.join(managers));put('80555',','.join(v for v in copies if v not in managers))
    for fid,vals in [('71063',ams),('71064',bus),('71065',[v for v in bds if v!='2150']),('71072',groups),('70143',pmos)]:put(fid,','.join(vals))
    for fid,flag in [('71045',monthflag and bool(groups)),('71046',weekflag),('71073',amsp),
                     ('71060',(ifwlw or busp) and bool(bus)),('71062',bdsp),('69938',iot_cross),('70025',bool(pmos))]:put(fid,'0' if flag else '')
    bgs={str(row.get('field60588',{}).get('value','')) for row in rows}
    for fid,bg in [('60967','30'),('60965','23')]:put(fid,bg if bg in bgs else '0')
    put('60968','0');put('60966','0')
