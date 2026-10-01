#!/usr/bin/env python3
"""Deterministic calendar preview. Offline, Pillow only; see README.md."""
import argparse
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ZONE = ZoneInfo('Australia/Melbourne')
COLORS = {'Work': ('#155D9B', '#EAF3FC'), 'Personal': ('#6048A1', '#F1EDFA'),
          'Family': ('#8A4B15', '#FCF1E4')}
INK, MUTED = '#172B3A', '#4D6070'

def stamp(value, zone):
    """Resolve offsetless timestamps, rejecting ambiguous/nonexistent wall times."""
    if 'T' not in value:
        raise ValueError('Timed timestamps require a date and T separator')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.second or dt.microsecond:
        raise ValueError('Sub-minute timestamps are unsupported; provide exact minute precision')
    z = ZoneInfo(zone)
    if dt.tzinfo is None:
        choices = [dt.replace(tzinfo=z, fold=f) for f in (0, 1)]
        valid = [c for c in choices if c.astimezone(timezone.utc).astimezone(z).replace(tzinfo=None) == dt]
        if not valid or len({c.utcoffset() for c in valid}) != 1:
            raise ValueError('Ambiguous or nonexistent local timestamp: ' + value)
        dt = valid[0]
    return dt.astimezone(ZONE)

def load_day(personal, work=None):
    day = date.fromisoformat(personal['targetDate'])
    start = datetime.combine(day, time(), ZONE)
    end = datetime.combine(day + timedelta(days=1), time(), ZONE)
    if start.utcoffset() != end.utcoffset():
        raise ValueError('DST transition target days are explicitly unsupported; choose a regular day')
    fresh = [('Personal / Family', stamp(personal['generatedAt'], personal['generatedAtTimezone']))]
    names = personal['calendarsIncluded']
    if not isinstance(names, list) or not all(isinstance(x, str) for x in names):
        raise ValueError('calendarsIncluded must be a list of names')
    events, all_day = [], []
    for e in personal['events']:
        if not isinstance(e['all_day'], bool) or not isinstance(e['title'], str) or not e['title'].strip():
            raise ValueError('Events require a nonempty title and boolean all_day')
        if e['calendar_name'] not in names:
            raise ValueError('Event calendar is missing from calendarsIncluded')
        ZoneInfo(e['timezone'])
        kind = next((k for k in COLORS if k.lower() in e['calendar_name'].lower()), 'Personal')
        item = {'title': e['title'], 'kind': kind, 'calendar': e['calendar_name']}
        if e['all_day']:
            a, b = date.fromisoformat(e['start_date']), date.fromisoformat(e['end_date'])
            if b < a:
                raise ValueError('All-day end precedes start')
            if a <= day <= b:  # Date-only all-day end is inclusive, floating calendar date.
                all_day.append(item)
        else:
            a, b = stamp(e['start_date'], e['timezone']), stamp(e['end_date'], e['timezone'])
            if b.astimezone(timezone.utc) <= a.astimezone(timezone.utc):
                raise ValueError('Timed events must have positive duration')
            if a < end and b > start:
                item.update(a=max(a, start), b=min(b, end), original_a=a, original_b=b)
                events.append(item)
    if work is not None:
        if work['date'] != day.isoformat():
            raise ValueError('Work feed date does not match targetDate')
        if work.get('all_day'):
            raise ValueError('Nonempty work all_day schema is unsupported; normalize into events first')
        fresh.append(('Work (partial feed)', stamp(work['generated_at'], work['timezone'])))
        for b in work['blocks']:
            a = stamp(day.isoformat() + 'T' + b['start'], work['timezone'])
            z = stamp(day.isoformat() + 'T' + b['end'], work['timezone'])
            if z <= a or a < start or z > end:
                raise ValueError('Work blocks must be positive same-day intervals')
            category = b['category']
            title = {'mantel': 'Mantel work', 'mantel_tbd': 'Mantel invitation · unresolved',
                     'optional_mantel': 'Optional Mantel', 'personal': 'Personal block'}.get(category)
            if title is None:
                raise ValueError('Unknown work category: ' + category)
            events.append(dict(title=title, kind='Personal' if category == 'personal' else 'Work',
                               calendar=category, a=a, b=z, original_a=a, original_b=z))
    events.sort(key=lambda e: (e['a'], e['b'], e['kind'], e['title']))
    all_day.sort(key=lambda e: (e['kind'], e['title']))
    return day, events, all_day, fresh, names

def minute(dt, day):
    return (dt - datetime.combine(day, time(), ZONE)).total_seconds() / 60

def clock(m):
    return '{:02d}:{:02d}'.format(int(m) // 60, int(m) % 60)

def gaps(events, day, lo=540, hi=1050):
    result, cursor = [], lo
    for e in events:
        a, b = max(lo, minute(e['a'], day)), min(hi, minute(e['b'], day))
        if b <= lo or a >= hi:
            continue
        if a > cursor:
            result.append((cursor, a))
        cursor = max(cursor, b)
    if cursor < hi:
        result.append((cursor, hi))
    return result

def render(personal, work, output, mode='test'):
    if mode not in ('test', 'today', 'overview'):
        raise ValueError('Unknown display mode')
    day, events, allday, fresh, names = load_day(personal, work)
    fonts = {s: ImageFont.truetype(str(ROOT / 'Lato-Regular.ttf'), s) for s in (24, 26, 28, 30, 34, 48, 64)}
    bold = {s: ImageFont.truetype(str(ROOT / 'Lato-Bold.ttf'), s) for s in (26, 28, 30, 34, 48, 64)}
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    def wrap(text, width, font):
        lines, line = [], ''
        for char in text.replace('\n', ' '):
            if measure.textlength(line + char, font=font) > width and line:
                split = line.rfind(' ')
                if split > 0:
                    lines.append(line[:split]); line = line[split+1:] + char
                else:
                    lines.append(line); line = char
            else:
                line += char
        return lines + [line]
    def card_height(e, width):
        continuation = 'a' in e and (e['a'] != e['original_a'] or e['b'] != e['original_b'])
        return 62 + 37 * len(wrap(e['title'], width, bold[30])) + (35 if continuation else 0)
    all_heights = [card_height(e, 850) for e in allday]
    top = 398 + sum(h + 14 for h in all_heights) if allday else 450
    lo = min([540] + [minute(e['a'], day) for e in events])
    hi = max([1050] + [minute(e['b'], day) for e in events])
    scale = max(1.3, (sum(card_height(e, 650) + 18 for e in events) + 80) / (hi-lo))
    timeline_bottom = top + (hi-lo)*scale
    placed, previous = [], top - 18
    lanes = []
    for e in events:
        a, b = minute(e['a'], day), minute(e['b'], day)
        lane = next((i for i, end in enumerate(lanes) if end <= a), len(lanes))
        if lane == len(lanes): lanes.append(b)
        else: lanes[lane] = b
        h = card_height(e, 650)
        y = max(top + (a-lo)*scale, previous + 18)
        placed.append((e, a, b, lane, y, h)); previous = y+h
    bottom = max(timeline_bottom, previous) + 65
    windows = gaps(events, day)
    height = int(bottom + 245 + 68*max(1, len(windows)) + 280)
    img = Image.new('RGB', (1080, height), '#F6F8FB'); d = ImageDraw.Draw(img)
    def txt(x, y, value, size=28, color=INK, heavy=False):
        d.text((x, y), value, font=(bold if heavy else fonts)[size], fill=color)
    def box(bounds, fill, radius=18, outline=None):
        d.rounded_rectangle(bounds, radius, fill=fill, outline=outline, width=2)
    banner = {'test': 'TEST PREVIEW · SAMPLE DATA', 'today': 'TODAY · DAILY OVERVIEW', 'overview': 'DAILY OVERVIEW'}[mode]
    box((48, 40, 438, 89), '#172B3A'); txt(66, 51, banner, 24, '#FFFFFF')
    txt(48, 116, day.strftime('%A, %d %B'), 64, heavy=True)
    txt(50, 205, str(day.year) + '  ·  Melbourne  ·  ' + datetime.combine(day, time(), ZONE).strftime('%Z (UTC%z)'), 28, MUTED)
    for i, kind in enumerate(COLORS):
        x = 50 + i*220; color, fill = COLORS[kind]
        d.ellipse((x, 268, x+18, 286), fill=color); txt(x+29, 260, kind, 28, color, True)
    txt(50, 323, 'ALL-DAY CONTEXT', 26, MUTED, True)
    y = 370
    if not allday:
        txt(50, y, 'No all-day items in supplied calendars', 28, MUTED)
    for e, h in zip(allday, all_heights):
        color, fill = COLORS[e['kind']]; box((48, y, 1032, y+h), fill)
        txt(72, y+15, e['kind'] + ' · All day', 26, color, True)
        for j, line in enumerate(wrap(e['title'], 850, bold[30])): txt(72, y+51+j*37, line, 30, heavy=True)
        y += h+14
    txt(50, top-5, 'DAY TIMELINE', 26, MUTED, True)
    top += 55; timeline_bottom += 55; bottom += 55
    # Label geometry moves with the timeline header.
    for m in range(int(lo//60)*60, int(hi)+1, 60):
        if m < lo: continue
        yy = top+(m-lo)*scale
        txt(48, yy-13, clock(m), 26, MUTED)
        d.line((145, yy, 1030, yy), fill='#D9E1E8', width=2)
    if hi % 60:
        yy=top+(hi-lo)*scale; txt(48, yy-13, clock(hi), 26, MUTED)
    lane_width = min(25, 112/max(1, len(lanes)))
    for e, a, b, lane, y, h in placed:
        y += 55; color, fill = COLORS[e['kind']]
        x=150+lane*lane_width; ya=top+(a-lo)*scale; yb=top+(b-lo)*scale
        box((x, ya, x+lane_width-3, max(ya+2, yb)), color, 4)
        d.line((x+lane_width, (ya+yb)/2, 288, y+h/2), fill=color, width=3)
        box((290, y, 1032, y+h), fill, outline=color)
        suffix = ' · continues across midnight' if e['a'] != e['original_a'] or e['b'] != e['original_b'] else ''
        txt(312, y+13, clock(a)+'–'+clock(b)+'  ·  '+e['kind'], 26, color, True)
        # Continuation is a separate label; keep title card height predictable.
        for j,line in enumerate(wrap(e['title'],650,bold[30])): txt(312,y+51+j*37,line,30,heavy=True)
        if suffix: txt(312,y+h-33,'Crosses midnight · shown portion',24,MUTED)
    if not events: txt(290, top+80, 'No timed blocks supplied',34,heavy=True)
    box((48, bottom, 1032, bottom+180+68*max(1,len(windows))), '#FFFFFF')
    txt(72, bottom+25, 'POTENTIAL FOCUS WINDOWS', 30, heavy=True)
    txt(72, bottom+76, 'Partial coverage · availability is not guaranteed.', 28, MUTED)
    txt(72, bottom+114, 'All-day context does not block these windows.', 26, MUTED)
    for i,(a,b) in enumerate(windows):
        txt(72,bottom+164+i*68,clock(a)+'–'+clock(b),34,heavy=True)
        txt(400,bottom+172+i*68,str(int(b-a))+' min  ·  no supplied timed blocks',26,MUTED)
    if not windows: txt(72,bottom+164,'No gaps within 09:00–17:30',30,MUTED)
    foot=bottom+215+68*max(1,len(windows))
    txt(50,foot,'SOURCE SNAPSHOTS · MELBOURNE TIME',26,MUTED,True)
    for i,(label,ts) in enumerate(fresh):
        age=(datetime.combine(day,time(),ZONE)-ts).total_seconds()/3600
        txt(50,foot+44+i*38,label+': '+ts.strftime('%d %b %H:%M')+(' · older than 24h at day start' if age>24 else ''),26,MUTED)
    txt(50,foot+138,'Coverage: '+', '.join(names)+(' + work partial feed' if work else ''),26,MUTED)
    footer = 'Illustrative test export · not real commitments' if mode == 'test' else 'Based on supplied calendar snapshots · partial coverage'
    txt(50,foot+177,footer,26,MUTED)
    img.save(output, 'PNG', optimize=False)
    return {'date':day.isoformat(),'gaps':[[clock(a),clock(b)] for a,b in windows],
            'timed_events':len(events),'all_day_events':len(allday),'size':img.size}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input',type=Path); p.add_argument('--work',type=Path); p.add_argument('--output',type=Path,default=Path('overview.png'))
    p.add_argument('--mode', choices=('test','today','overview'), default='test', help='Explicit label; today requires caller date validation')
    args=p.parse_args()
    try:
        result=render(json.loads(args.input.read_text()),json.loads(args.work.read_text()) if args.work else None,args.output,args.mode)
    except (ValueError,KeyError,TypeError) as e:
        p.exit(2,'Invalid input: '+str(e)+'\n')
    print(json.dumps(result,sort_keys=True))

if __name__ == '__main__': main()
