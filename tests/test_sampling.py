import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'skills/caravan/scripts'))
import sampling
import semantic


def session(key, source='codex', month='2026-09', project='p', lengths=(200,800,100,800,200,800)):
    return dict(key=key,source=source,project=project,date=month+'-15T00:00:00+00:00',fingerprint=key,
                messages=[dict(id=f'm{i}',role='user' if i%2==0 else 'assistant',text='x'*n,
                               date=month+'-15T00:00:00+00:00') for i,n in enumerate(lengths)])


class SamplingTests(unittest.TestCase):
    def test_sources_months_and_projects_are_nested_rounds(self):
        rows=[session(f'{s}-{m}-{p}',s,m,p) for s in semantic.SOURCES
              for m in ('2026-08','2026-09','2026-10') for p in ('a','b','c','d')]
        selected=sampling.ordered_sessions(rows)[:12]
        self.assertEqual(len({r['key'] for r in selected}),12)
        for source in semantic.SOURCES:
            source_rows=[r for r in selected if r['source']==source]
            self.assertEqual(len(source_rows),12 // len(semantic.SOURCES))
            self.assertEqual({r['date'][:7] for r in source_rows},{'2026-08','2026-09','2026-10'})
        self.assertEqual(sampling.ordered_sessions(rows),sampling.ordered_sessions(list(reversed(rows))))
        self.assertNotEqual([s['key'] for s in selected],
                            [s['key'] for s in sampling.ordered_sessions(rows,'other')[:12]])

    def test_no_fixed_metadata_reservation_and_followup_preserved(self):
        row=session('long',lengths=(4000,4000,4000,4000,4000,4000))
        packet=sampling.window(row,2000,semantic.RUBRIC)
        self.assertEqual(semantic.packet_size(packet),2000)
        self.assertGreater(sum(len(m['text']) for m in packet['messages']),1400)
        self.assertTrue(packet['quality']['has_human_followup'])
        ids=[int(m['id'][1:]) for m in packet['messages']]
        self.assertEqual(ids,list(range(ids[0],ids[0]+len(ids))))
        self.assertTrue(all(m['truncated'] for m in packet['messages']))

    def test_unused_short_window_budget_moves_to_long_window(self):
        rows=[session('short',lengths=(30,30,30)),session('long',lengths=(4000,)*6)]
        packets=sampling.pack(rows,6000,semantic.RUBRIC)
        self.assertLessEqual(sum(map(semantic.packet_size,packets)),6000)
        self.assertEqual(semantic.packet_size(packets[1]),4000)
        self.assertTrue(all(not m['truncated'] for m in packets[0]['messages']))

    def test_middle_window_keeps_preceding_assistant_context(self):
        row=session('context',lengths=(50,)*20)
        packets=[sampling.window(row,2000,semantic.RUBRIC,str(i)) for i in range(10)]
        middle=[p for p in packets if p['messages'][0]['id']!='m0']
        self.assertTrue(middle)
        for p in middle:
            self.assertEqual(p['messages'][0]['role'],'assistant')
            self.assertTrue(p['quality']['has_human_followup'])

    def test_many_budgets_and_counts_never_exceed_limit(self):
        for count in (1,3,6,12,16,24):
            for per_window in (600,1000,1500,2000):
                rows=[session(str(i),lengths=(35,1300,90,700,2400,90)) for i in range(count)]
                packets=sampling.pack(rows,count*per_window,semantic.RUBRIC)
                self.assertLessEqual(sum(map(semantic.packet_size,packets)),count*per_window)
                self.assertEqual(len(packets),count)
                self.assertTrue(all(m['text'] for p in packets for m in p['messages']))

    def test_cache_tracks_content_not_unused_capacity(self):
        row=session('short',lengths=(30,30,30))
        self.assertEqual(sampling.window(row,2000,semantic.RUBRIC)['cache_key'],
                         sampling.window(row,4000,semantic.RUBRIC)['cache_key'])
        self.assertNotEqual(sampling.window(row,2000,semantic.RUBRIC)['cache_key'],
                            sampling.window(row,2000,'changed-rubric')['cache_key'])

    def test_coverage_contains_no_identifiers_or_text(self):
        rows=[session('PRIVATE_SESSION',project='PRIVATE_PROJECT')]
        packets=sampling.pack(rows,2000,semantic.RUBRIC)
        result=sampling.coverage(rows,rows,packets,2000)
        self.assertNotIn('PRIVATE',str(result))
        self.assertEqual(result['max_dimension_ratings'],38)
        self.assertEqual(result['months'][0]['selected'],1)


if __name__=='__main__':unittest.main()

class MultiSceneTests(unittest.TestCase):
    def test_separated_scenes_are_one_bounded_packet(self):
        row=session('two-scenes',lengths=(100,)*30)
        packet=sampling.window(row,2000,semantic.RUBRIC)
        groups={m['scene'] for m in packet['messages']}
        self.assertEqual(groups,{1,2})
        indices=[[int(m['id'][1:]) for m in packet['messages'] if m['scene']==scene] for scene in sorted(groups)]
        self.assertGreater(indices[1][0]-indices[0][-1],1)
        self.assertLessEqual(semantic.packet_size(packet),2000)
        self.assertTrue(all(m['text'] for m in packet['messages']))
        self.assertEqual(len(sampling.pack([row],2000,semantic.RUBRIC)),1)
