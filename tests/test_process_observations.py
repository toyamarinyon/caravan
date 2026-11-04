import contextlib
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/caravan/scripts'))
import semantic as s
import rubric


class ProcessObservationTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parents[1]/'output/process-tests'
        self.root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=self.root)
        self.home=Path(self.tmp.name);self.out=self.home/'result'
        stamp=s.datetime.now(s.timezone.utc).isoformat()
        for i in range(3):
            path=self.home/'.codex/sessions'/f'{i}.jsonl'
            path.parent.mkdir(parents=True,exist_ok=True)
            rows=[dict(type='session_meta',payload=dict(id=str(i),cwd='fixture'))]
            for j,role in enumerate(['user','assistant','user','assistant']):
                rows.append(dict(type='response_item',timestamp=stamp,payload=dict(type='message',role=role,
                    content=('SYNTHETIC TEST DIALOGUE ONLY. '*4)+f'{i}-{j}')))
            path.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()):
            self.manifest=s.prepare(self.home,self.out,consent=True)
        self.packets=self.manifest['selected']

    def tearDown(self):
        assert self.home.resolve().is_relative_to(self.root.resolve())
        self.tmp.cleanup()

    def review(self,packet):
        return dict(schema=s.RUBRIC,cache_key=packet['cache_key'],reviewer='SYNTHETIC TEST; not an AI evaluation', purposes=[dict(id='unknown',evidence=[],reason='Synthetic fixture.')],
                    ratings={id:dict(status='uncertain',evidence=[],reason='Synthetic fixture context is insufficient.') for id in s.IDS})

    def observation(self,packet,form='retry'):
        user=next(m['id'] for m in packet['messages'] if m['role']=='user')
        return dict(status='observed',evidence=[user],reason='Synthetic test only; no quality judgment.',
                    forms=[dict(id=form,evidence=[user])])

    def test_form_requires_known_choice_and_human_evidence(self):
        p=self.packets[0];r=self.review(p)
        r['ratings']['recovery_strategy']=self.observation(p)
        s.validate_review(r,p)
        for forms in [[],[dict(id='better',evidence=['m1'])],
                      [dict(id='retry',evidence=['missing'])]]:
            invalid=copy.deepcopy(r);invalid['ratings']['recovery_strategy']['forms']=forms
            with self.assertRaises(ValueError):s.validate_review(invalid,p)
        invalid=copy.deepcopy(r)
        assistant=next(m['id'] for m in p['messages'] if m['role']=='assistant')
        invalid['ratings']['recovery_strategy']['evidence'].append(assistant)
        invalid['ratings']['recovery_strategy']['forms'][0]['evidence']=[assistant]
        with self.assertRaisesRegex(ValueError,'human evidence'):s.validate_review(invalid,p)
        invalid=copy.deepcopy(r);invalid['ratings']['ownership']['status']='not_applicable'
        s.validate_review(invalid,p)
        old=self.review(p);old['schema']='semantic-18-v1'
        with self.assertRaisesRegex(ValueError,'Stale'):s.validate_review(old,p)

    def test_absent_situation_is_not_zero_or_unknown_and_forms_export_without_counts(self):
        reviews=[self.review(p) for p in self.packets]
        reviews[0]['ratings']['recovery_strategy']=self.observation(self.packets[0])
        reviews[0]['ratings']['model_routing']=self.observation(self.packets[0],form='fixed')
        reviews[1]['ratings']['recovery_strategy']=dict(status='not_applicable',evidence=[],reason='No breakdown occurs in this synthetic scene.')
        # The third stays uncertain; denominator must contain only the first.
        s.write(self.out/'reviews.json',reviews)
        with contextlib.redirect_stdout(io.StringIO()):report=s.finalize(self.out,self.out/'reviews.json')
        metric=next(p for p in report['perspectives'] if p['id']=='recovery_strategy')
        self.assertEqual((metric['sessions'],metric['assessed_sessions'],metric['uncertain_sessions'],metric['not_applicable_sessions']),(1,1,1,1))
        self.assertEqual(metric['session_rate'],100)
        form=next(f for f in metric['observed_forms'] if f['id']=='retry')
        self.assertEqual(form['sessions'],1)
        profile=json.loads((self.out/'share-profile.json').read_text(encoding='utf-8'))
        exported=next(m for m in profile['metrics'] if m['id']=='recovery_strategy')
        self.assertEqual(exported['forms'],['retry'])
        self.assertEqual(next(m for m in profile['metrics'] if m['id']=='model_routing')['forms'],['fixed'])
        self.assertEqual(set(exported),{'id','status','session_rate','forms'})
        self.assertEqual(len(profile['metrics']),38)
        self.assertEqual(profile['method'],s.RUBRIC)
        if shutil.which('node'):
            test=Path(__file__).with_name('report_ui.cjs')
            subprocess.run(['node',str(test),str(self.out/'index.html'),str(self.out/'share-profile.json')],check=True,capture_output=True)

    def test_purpose_requires_evidence_and_absent_base_opportunity_is_excluded(self):
        packet=self.packets[0]; review=self.review(packet)
        review['purposes']=[dict(id='routine', evidence=[], reason='Synthetic routine.')]
        with self.assertRaisesRegex(ValueError,'human evidence'): s.validate_review(review,packet)
        user=next(m['id'] for m in packet['messages'] if m['role']=='user')
        review['purposes'][0]['evidence']=[user]
        review['ratings']['ownership']['status']='not_applicable'
        s.validate_review(review,packet)
        review['purposes'].append(dict(id='unknown',evidence=[],reason='Unclear'))
        with self.assertRaisesRegex(ValueError,'stand alone'): s.validate_review(review,packet)

    def test_process_observations_do_not_change_type_or_evidence_gates(self):
        base=[dict(id=p['id'],count=30,sessions=6,assessed_sessions=12) for p in s.base.PERSPECTIVES]
        extra=[dict(id=p['id'],count=999,sessions=12,assessed_sessions=12) for p in rubric.PROCESS+rubric.TOOLING]
        self.assertEqual(s.base.classify(base,50,12),s.base.classify(base+extra,50,12))
        self.assertEqual(s.base.score_styles(base,12),s.base.score_styles(base+extra,12))
        no_base=[dict(p,count=0,sessions=0) for p in base]
        self.assertFalse(s.base.classify(no_base+extra,50,12)['evidence_ready'])

    def test_old_report_keeps_twenty_unassessed_and_old_share_method(self):
        perspectives=[dict(p,count=0,sessions=0,assessed_sessions=1,uncertain_sessions=0,session_rate=0,status='未観測',findings=[])
                      for p in s.base.PERSPECTIVES]
        report=dict(method='semantic-18-v1',days=90,perspectives=perspectives,
                    **s.base.classify(perspectives,2,1))
        before=copy.deepcopy(report)
        view=rubric.display_report(report)
        self.assertEqual(report,before)
        new=[p for p in view['perspectives'] if p.get('not_assessed')]
        self.assertEqual(len(new),20)
        self.assertTrue(all(p['count'] is None and p['session_rate'] is None and p['status']=='未評価' for p in new))
        shared=s.base.make_share(view)
        self.assertEqual(len(shared['metrics']),18)
        self.assertEqual(shared['method'],'semantic-18-v1')


if __name__=='__main__':unittest.main()
