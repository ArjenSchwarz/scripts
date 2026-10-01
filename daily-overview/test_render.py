import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from render import ROOT, load_day, gaps, render, stamp

class RendererTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads((ROOT/'sample-input.json').read_text())
        self.w = json.loads((ROOT/'work-feed.json').read_text())

    def test_sample_and_determinism(self):
        with tempfile.TemporaryDirectory() as t:
            a,b = Path(t)/'a.png',Path(t)/'b.png'
            result = render(self.p,self.w,a)
            render(self.p,self.w,b)
            self.assertEqual(result['gaps'],[['09:00','10:00'],['12:00','15:00'],['15:25','17:30']])
            self.assertEqual((result['timed_events'],result['all_day_events']),(3,1))
            self.assertEqual(hashlib.sha256(a.read_bytes()).digest(),hashlib.sha256(b.read_bytes()).digest())
            with Image.open(a) as im: im.verify()

    def test_empty_and_all_day_only(self):
        for events in ([],[self.p['events'][2]]):
            self.p['events']=events
            day,timed,all_day,*_=load_day(self.p)
            self.assertEqual(gaps(timed,day),[(540,1050)])
            with tempfile.TemporaryDirectory() as t:
                render(self.p,None,Path(t)/'empty.png')

    def test_inclusive_all_day_end(self):
        self.p['events']=[self.p['events'][2]]
        self.p['events'][0]['start_date']='2026-10-01'
        self.assertEqual(len(load_day(self.p)[2]),1)

    def test_overlap_union(self):
        e=copy.deepcopy(self.p['events'][0]); e['start_date']='2026-10-02T10:30:00'; e['end_date']='2026-10-02T13:00:00'
        self.p['events'].append(e)
        day,events,*_=load_day(self.p,self.w)
        self.assertEqual(gaps(events,day),[(540,600),(780,900),(925,1050)])

    def test_midnight_clip_and_long_title(self):
        e=self.p['events'][0]; e['start_date']='2026-10-01T23:00:00'; e['end_date']='2026-10-02T01:00:00'
        e['title']='A long calendar title with full detail ' * 12
        self.p['events']=[e]
        day,events,*_=load_day(self.p)
        self.assertEqual(events[0]['a'].hour,0)
        with tempfile.TemporaryDirectory() as t: render(self.p,None,Path(t)/'night.png')

    def test_offsets_and_named_zones(self):
        self.assertEqual(stamp('2026-10-02T10:00:00','Australia/Sydney'),stamp('2026-10-02T00:00:00Z','UTC'))

    def test_dst_and_invalid_rejected(self):
        for value in ('2026-10-04T02:30:00','2026-04-05T02:30:00','2026-10-02T10:00:01'):
            with self.assertRaises(ValueError): stamp(value,'Australia/Melbourne')
        self.p['targetDate']='2026-10-04'
        with self.assertRaises(ValueError): load_day(self.p)
        self.p['targetDate']='2026-10-02'
        self.p['events'][0]['end_date']=self.p['events'][0]['start_date']
        with self.assertRaises(ValueError): load_day(self.p)
        self.w['date']='2026-10-03'
        with self.assertRaises(ValueError): load_day(self.p,self.w)

if __name__=='__main__': unittest.main()
