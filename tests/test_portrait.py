import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/caravan/scripts'))
import portrait as p
import semantic as s


class PortraitTests(unittest.TestCase):
    def packet(self,i=0):
        return dict(cache_key='synthetic-'+str(i),session='session-'+str(i),messages=[
            dict(id='m1',role='user',text='SYNTHETIC TEST, NOT USER HISTORY'),dict(id='m2',role='assistant',text='SYNTHETIC RESPONSE')])

    def review(self,packet,status='left'):
        return dict(schema=p.SCHEMA,cache_key=p.cache_key(packet),reviewer='SYNTHETIC FIXTURE ONLY',
                    axes={a['id']:dict(status=status,evidence=['m1'] if status in ('left','right','both') else [],
                        reason='Synthetic choice for threshold testing.',dimensions=[a['dimensions'][0]]) for a in p.AXES},
                    tones={t['id']:dict(status='not_observed',evidence=[],reason='No tone observation in this synthetic fixture.') for t in p.TONES},discoveries=[])

    def test_all_sixteen_codes_are_reachable_without_ranking(self):
        self.assertEqual(len({t['code'] for t in p.catalog()}),16)
        for item in p.catalog():
            packets=[self.packet(i) for i in range(3)];reviews=[self.review(x) for x in packets]
            for r in reviews:
                for a,code in zip(p.AXES,item['code']):r['axes'][a['id']]['status']='left' if code==a['left']['code'] else 'right'
            result=p.aggregate(packets,reviews)['classification']
            self.assertEqual(result['type_code'],item['code'])
            self.assertEqual(result['candidate_codes'],[item['code']])

    def test_absence_is_not_opposite_mixed_and_insufficient_are_preserved(self):
        packets=[self.packet(i) for i in range(3)]
        absent=p.aggregate(packets,[self.review(x,'not_observed') for x in packets])
        self.assertIsNone(absent['classification']['profile'])
        self.assertEqual(absent['classification']['type_code'],'????')
        self.assertTrue(all(a['left_percent'] is None for a in absent['axes']))
        mixed=p.aggregate(packets,[self.review(x,'both') for x in packets])
        self.assertTrue(all(a['left_percent']==50 for a in mixed['axes']))
        self.assertEqual(len(mixed['classification']['candidate_codes']),16)
        self.assertIsNone(mixed['classification']['profile'])
        small=p.aggregate(packets[:2],[self.review(x) for x in packets[:2]])
        self.assertEqual(small['classification']['type_code'],'????')

    def test_no_opportunity_does_not_cast_a_vote(self):
        packets=[self.packet(i) for i in range(4)]
        reviews=[self.review(x, 'not_applicable' if i==0 else 'left') for i,x in enumerate(packets)]
        p.validate(reviews[0],packets[0])
        result=p.aggregate(packets,reviews)
        self.assertTrue(all(a['observed_sessions']==3 and a['state']=='left' for a in result['axes']))
        self.assertTrue(all(a['counts']['not_applicable']==1 for a in result['axes']))

    def test_tone_and_discoveries_need_human_refs_and_never_change_type(self):
        packet=self.packet();r=self.review(packet)
        note=dict(key='preserve_branch',title='Synthetic note',observation='Private paraphrase to test export boundaries.',
                  question='Synthetic question?',evidence=['m1'],relation='specific_variant',dimensions=['task_partitioning'])
        before=p.aggregate([packet],[r])['classification']
        r['discoveries']=[note];r['tones']['direct']=dict(status='observed',evidence=['m1'],reason='Synthetic direct request.')
        r['tones']['polite']=dict(status='observed',evidence=['m1'],reason='Synthetic polite phrasing can coexist.')
        p.validate(r,packet)
        self.assertEqual(before,p.aggregate([packet],[r])['classification'])
        for modify in [lambda x:x['axes']['framing'].update(evidence=['m2']),
                       lambda x:x['tones']['direct'].update(evidence=['m2']),
                       lambda x:x['discoveries'][0].update(evidence=['m2']),
                       lambda x:x.update(discoveries=[note,note,note]),
                       lambda x:x['discoveries'][0].update(dimensions=[]),
                       lambda x:x['axes']['framing'].update(dimensions=['unknown']),
                       lambda x:x['tones']['direct'].update(evidence=['missing'])]:
            bad=copy.deepcopy(r);modify(bad)
            with self.assertRaises(ValueError):p.validate(bad,packet)
        with self.assertRaisesRegex(ValueError,'Stale'):p.validate(r,self.packet(1))

    def test_boundary_is_inclusive_and_excludes_unknown_votes(self):
        packets=[self.packet(i) for i in range(24)]
        reviews=[self.review(x,'right' if i<13 else 'left' if i<20 else 'uncertain') for i,x in enumerate(packets)]
        result=p.aggregate(packets,reviews)
        self.assertTrue(all(a['observed_sessions']==20 and a['state']=='right' for a in result['axes']))
        reviews[12]=self.review(packets[12],'left')
        self.assertTrue(all(a['state']=='mixed' for a in p.aggregate(packets,reviews)['axes']))
        with self.assertRaises(ValueError):p.aggregate(packets,reviews[:-1])

    def test_structured_choice_does_not_prove_authored_tone(self):
        packet=self.packet();packet['messages'][0]['origin']='structured_answer'
        review=self.review(packet)
        p.validate(review,packet)  # A human choice can still support an axis.
        review['tones']['direct']=dict(status='observed',evidence=['m1'],reason='Copied wording')
        with self.assertRaisesRegex(ValueError,'human-authored'):p.validate(review,packet)

    def test_leave_one_out_uses_saved_rules_and_does_not_change_result(self):
        packets=[self.packet(i) for i in range(5)]
        result=p.aggregate(packets,[self.review(x,'left' if i<3 else 'right') for i,x in enumerate(packets)])
        original=copy.deepcopy(result)
        checks=p.material_checks(result)
        self.assertTrue(all(v==dict(changed=2,tested=5,states=['left','mixed']) for v in checks.values()))
        self.assertEqual(result,original)
        result['rules']=dict(result['rules'],min_sessions=5)
        self.assertTrue(all(v['changed']==5 and v['states']==['insufficient'] for v in p.material_checks(result).values()))
        del result['rules'];self.assertEqual(p.material_checks(result),{})

    def test_discoveries_group_only_by_authored_key_and_keep_evidence(self):
        packets=[self.packet(i) for i in range(2)];reviews=[self.review(x) for x in packets]
        for r in reviews:r['discoveries']=[dict(key='same_pattern',title='Same',observation='Observed synthetic condition.',
            question='When?',evidence=['m1'],relation='uncovered',dimensions=[])]
        notes=p.aggregate(packets,reviews)['discoveries']
        self.assertEqual(len(notes),1)
        self.assertEqual(len(notes[0]['findings']),2)
        self.assertEqual({f['session'] for f in notes[0]['findings']},{x['session'] for x in packets})

    def test_purpose_subsets_keep_one_vote_per_session_and_unknown_out_of_sensitivity(self):
        from test_developer_report import DeveloperReportTests
        packets=[self.packet(i) for i in range(5)]
        reviews=[self.review(packet,'right' if i==0 else 'left') for i,packet in enumerate(packets)]
        purposes=['routine','production','production','production','unknown']
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            out=Path(directory); report=DeveloperReportTests().report()
            report['sample_key']=p.sample_key(packets); report['purpose_summary']=[]
            p.write(out/'report.json',report); p.write(out/'manifest.json',dict(schema=s.RUBRIC,selected=packets))
            for packet,purpose in zip(packets,purposes):
                semantic_review=dict(schema=s.RUBRIC,cache_key=packet['cache_key'],reviewer='Synthetic',
                    purposes=[dict(id=purpose,evidence=[] if purpose=='unknown' else ['m1'],reason='Synthetic')],
                    ratings={id:dict(status='uncertain',evidence=[],reason='Synthetic') for id in s.IDS})
                p.write(out/'cache'/(packet['cache_key']+'.json'),semantic_review)
            p.write(out/'portrait-reviews.json',reviews)
            result=p.finalize(out,out/'portrait-reviews.json')['portrait']['purpose_context']
            self.assertEqual(result['retained_sessions'],3)
            self.assertTrue(all(a['state']=='left' and a['observed_sessions']==3 for a in result['excluding_routine_only_and_unknown']))
            self.assertTrue(all(a['state']=='insufficient' for a in result['groups']['routine']))

    def test_finalize_preserves_base_date_reuses_cache_and_rejects_stale_sample(self):
        root=Path(__file__).resolve().parents[1]/'output/portrait-tests';root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            out=Path(directory)
            # A fully rendered baseline fixture, with synthetic review provenance.
            from test_developer_report import DeveloperReportTests
            report=DeveloperReportTests().report();packets=[self.packet(i) for i in range(3)]
            report['sample_key']=p.sample_key(packets)
            p.write(out/'report.json',report);p.write(out/'manifest.json',dict(schema=s.RUBRIC,selected=packets))
            with self.assertRaisesRegex(ValueError,'Consent'):p.prepare(out)
            with contextlib.redirect_stdout(io.StringIO()):pending=p.prepare(out,consent=True)
            self.assertEqual(len(pending),3)
            with self.assertRaisesRegex(ValueError,'Missing'):p.finalize(out)
            reviews=[self.review(x) for x in packets]
            reviews[0]['discoveries']=[dict(key='test_note',title='<script>PRIVATE_NOTE</script>',observation='Private observation.',
                question='Private question?',evidence=['m1'],relation='uncovered',dimensions=[])]
            p.write(out/'reviews.json',reviews)
            with contextlib.redirect_stdout(io.StringIO()):
                current=p.finalize(out,out/'reviews.json');self.assertEqual(p.prepare(out,True),[])
            self.assertEqual(current['generated_at'],report['generated_at'])
            shared=(out/'share-profile.json').read_text(encoding='utf-8')
            self.assertIn(p.SCHEMA,shared)
            for secret in ['PRIVATE_NOTE','Private question','Private observation','tones','discoveries']:
                self.assertNotIn(secret,shared)
                self.assertNotIn(secret,(out/'developer.html').read_text(encoding='utf-8'))
            self.assertNotIn('<script>PRIVATE_NOTE</script>',(out/'index.html').read_text(encoding='utf-8'))
            import shutil,subprocess
            if shutil.which('node'):
                subprocess.run(['node',str(Path(__file__).with_name('report_ui.cjs')),str(out/'index.html'),str(out/'share-profile.json')],check=True,capture_output=True)
            p.write(out/'manifest.json',dict(schema=s.RUBRIC,selected=[self.packet(99)]))
            with self.assertRaisesRegex(ValueError,'matching'):p.prepare(out,True)
            assert out.resolve().is_relative_to(root.resolve())


if __name__=='__main__':unittest.main()
