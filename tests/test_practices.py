import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/caravan/scripts'))
import practices as p
import portrait
import backup
import diagnose
import test_portrait
import test_developer_report
from test_distribution import temporary_workspace


def example(packet, featured=True):
    return dict(schema=p.SCHEMA, cache_key=p.cache_key(packet), reviewer='SYNTHETIC FIXTURE ONLY',
        status='case', reason='架空例。同じ条件で比較させ、不明点を消さずに候補を絞る組み合わせ。', featured=featured, portability='portable',
        case=dict(title='比較の条件をそろえてから、案を選ぶ', stage='request',
            situation=dict(text='架空例：複数の案から、どれを採用するか考えている。', refs=['m1']),
            human_action=dict(text='本人は、同じ条件で案を比較するよう依頼した。', refs=['m1']),
            ai_role=dict(text='条件をそろえた比較表を作る役割を求められた。', refs=['m1']),
            response=dict(status='assistant_report', text='AIは比較表を作ったと報告した。本人の採用判断はまだない。', refs=['m2']),
            limitation='比較表の内容や採用後の結果は、この架空例にはない。',
            question='条件がぶつかったとき、どれを優先すると決めましたか？',
            try_next='同じ時間と費用の条件で案を比較し、まだ分からない点も並べて。',
            collaboration=dict(
                pattern=dict(text='架空例：AIに条件をそろえて比較させ、不明点を残したまま候補を絞るよう頼んだ。',refs=['m1']),
                boundary=dict(text='架空例：比較する条件は本人が指定し、分からない点を埋めずに整理するようAIに求めた。',refs=['m1'])),
            decision=dict(kind='sequence',condition=dict(status='context',text='架空例：候補を絞る前に費用条件をそろえる場面。',refs=['m1']),
                alternative=dict(status='unknown',text='別の案を選ぶ条件は、この架空例にはない。',refs=[]),
                steps=[dict(text='同じ費用条件で比較するよう頼む。',refs=['m1']),dict(text='不明点を残して候補を絞るよう頼む。',refs=['m1'])])))


class PracticeTests(unittest.TestCase):
    def test_authorship_chronology_and_stale_evidence(self):
        packet=test_portrait.PortraitTests().packet(); review=example(packet);p.validate(review,packet)
        for change in [lambda r:r['case']['human_action'].update(refs=['m2']),
                       lambda r:r['case']['response'].update(status='user_report'),
                       lambda r:r['case']['response'].update(refs=['m1']),
                       lambda r:r['case']['situation'].update(refs=['missing']),
                       lambda r:r['case']['response'].update(status='not_visible'),
                       lambda r:r['case'].update(stage='personality')]:
            bad=copy.deepcopy(review);change(bad)
            with self.assertRaises(ValueError):p.validate(bad,packet)
        changed=copy.deepcopy(packet);changed['messages'][0]['text']='Changed text'
        with self.assertRaisesRegex(ValueError,'Stale'):p.validate(review,changed)
        # A user's later self-report is allowed, but is never promoted to verified effectiveness.
        packet['messages'].append(dict(id='m3',role='user',text='Synthetic self-report'))
        review['cache_key']=p.cache_key(packet);review['case']['response'].update(status='user_report',refs=['m3'])
        p.validate(review,packet)

    def test_connected_case_cannot_cross_an_omitted_scene(self):
        packet=test_portrait.PortraitTests().packet()
        packet['messages'][0]['scene']=1; packet['messages'][1]['scene']=2
        review=example(packet)
        with self.assertRaisesRegex(ValueError,'separated scenes'): p.validate(review,packet)
        packet['messages'][1]['scene']=1; review=example(packet)
        review['case']['decision']['steps'][0]['refs']=['missing']
        with self.assertRaises(ValueError): p.validate(review,packet)

    def test_selection_revision_invalidates_cache_but_preserves_saved_results(self):
        packet=test_portrait.PortraitTests().packet(); review=example(packet)
        # A change in editorial/selection rules cannot silently reuse an old review.
        old_definition=copy.deepcopy(p.DEFINITION)
        old_definition.pop('selection_revision')
        review['cache_key']=portrait.digest([old_definition,packet])
        with self.assertRaisesRegex(ValueError,'Stale'):p.validate(review,packet)
        # Saved results are observations, not a claim of review under the newest rules.
        report=dict(sessions=1,sample_key='synthetic')
        saved=dict(schema='practice-v2',sample_key='synthetic',generated_at='2026-11-03',
            reviewed_sessions=1,items=[dict(session='saved',featured=True,case=review['case'])])
        del saved['items'][0]['case']['collaboration']
        before=copy.deepcopy(saved)
        p.validate_saved(saved,report)
        self.assertEqual(saved,before)

    def test_missing_context_can_produce_no_case(self):
        packet=test_portrait.PortraitTests().packet();review=example(packet)
        review.update(status='insufficient',case=None,featured=False,portability='unsupported',reason='Triggering image is not present.')
        p.validate(review,packet)
        review['featured']=True
        with self.assertRaises(ValueError):p.validate(review,packet)
        report=dict(sessions=1,sample_key='synthetic')
        saved=dict(schema=p.SCHEMA,sample_key='synthetic',generated_at='2026-11-03',reviewed_sessions=1,items=[])
        p.validate_saved(saved,report)
        saved['sample_key']=None;report['sample_key']=None
        with self.assertRaises(ValueError):p.validate_saved(saved,report)

    def test_full_workflow_preserves_type_dates_share_and_private_roundtrip(self):
        with temporary_workspace() as directory,contextlib.redirect_stdout(io.StringIO()):
            output=Path(directory);packet=test_portrait.PortraitTests().packet();report=test_developer_report.DeveloperReportTests().report()
            report.update(sessions=1,sample_key=portrait.sample_key([packet]))
            portrait.write(output/'report.json',report)
            portrait.write(output/'manifest.json',dict(schema=report['method'],selected=[packet]))
            original=copy.deepcopy(report);share=diagnose.make_share(report)
            with self.assertRaises(ValueError):p.prepare(output)
            self.assertEqual(len(p.prepare(output,True)),1)
            with self.assertRaisesRegex(ValueError,'Missing'):p.finalize(output)
            reviews=output/'reviews.json';portrait.write(reviews,[example(packet)])
            result=p.finalize(output,reviews)
            self.assertEqual({k:v for k,v in result.items() if k!='practices'},original)
            self.assertEqual(diagnose.make_share(result),share)
            self.assertNotIn('比較の条件',json.dumps(share,ensure_ascii=False))
            self.assertEqual(p.prepare(output,True),[])
            value=backup.bundle(result);self.assertEqual(backup.validate(value)['report'],result)
            self.assertEqual(backup.read(output/'before-practices.backup.json')['report'],original)
            html=(output/'index.html').read_text(encoding='utf-8')
            self.assertIn('比較の条件',html)
            self.assertNotIn('比較の条件',(output/'developer.html').read_text(encoding='utf-8'))
            for change in [lambda v:v['report']['practices'].update(sample_key='another'),
                           lambda v:v['report']['practices'].update(reviewed_sessions=2),
                           lambda v:v['report']['practices']['items'][0]['case']['decision'].update(kind='generic')]:
                bad=copy.deepcopy(value);change(bad)
                with self.assertRaises(ValueError):backup.validate(bad)
            # Explicit exclusions override reuse of an old matching sample.
            portrait.write(output/'excluded-sessions.json',['sample:'+packet['session']])
            with self.assertRaisesRegex(ValueError,'excluded'):p.prepare(output,True)

    def test_duplicate_unselected_and_missing_reviews_do_not_mutate_report(self):
        with temporary_workspace() as directory:
            output=Path(directory);packet=test_portrait.PortraitTests().packet();report=test_developer_report.DeveloperReportTests().report()
            report.update(sessions=1,sample_key=portrait.sample_key([packet]))
            portrait.write(output/'report.json',report)
            portrait.write(output/'manifest.json',dict(schema=report['method'],selected=[packet]))
            original=(output/'report.json').read_bytes()
            for reviews in [[example(packet)]*2,[example(test_portrait.PortraitTests().packet(9))],[]]:
                portrait.write(output/'reviews.json',reviews)
                with self.assertRaises(ValueError):p.finalize(output,output/'reviews.json')
                self.assertEqual((output/'report.json').read_bytes(),original)

    def test_no_quota_and_legacy_backup_compatibility(self):
        packet=test_portrait.PortraitTests().packet(); review=example(packet)
        report=dict(sessions=3,sample_key='synthetic')
        value=dict(schema=p.SCHEMA,sample_key='synthetic',generated_at='2026-11-03',reviewed_sessions=3,
            items=[dict(session=str(i),featured=i==0,case=copy.deepcopy(review['case'])) for i in range(3)])
        p.validate_saved(value,report)  # One featured case among three is valid.
        value['items'][0]['featured']=False;p.validate_saved(value,report)  # Zero is also valid.
        legacy=copy.deepcopy(value);legacy['schema']='practice-v1'
        for item in legacy['items']:
            item['featured']=True;del item['case']['decision'];del item['case']['collaboration']
        p.validate_saved(legacy,report)
        legacy['items'][0]['featured']=False
        with self.assertRaises(ValueError):p.validate_saved(legacy,report)

    def test_generic_corrections_and_invented_alternatives_cannot_be_featured(self):
        packet=test_portrait.PortraitTests().packet();good=example(packet)
        generic=copy.deepcopy(good);generic['case']['decision']['kind']='generic'
        with self.assertRaisesRegex(ValueError,'Generic'):p.validate(generic,packet)
        generic.update(featured=False,portability='generic');p.validate(generic,packet)
        for change in [lambda d:d.update(steps=[]),
                       lambda d:d['steps'][0].update(refs=['m2']),
                       lambda d:d['condition'].update(status='stated',refs=['m2']),
                       lambda d:d['alternative'].update(status='observed'),
                       lambda d:d.update(kind='tradeoff'),
                       lambda d:d.update(kind='conditional')]:
            bad=copy.deepcopy(good);change(bad['case']['decision'])
            with self.assertRaises(ValueError):p.validate(bad,packet)
        tradeoff=copy.deepcopy(good);d=tradeoff['case']['decision'];d.update(kind='tradeoff')
        d['condition'].update(status='stated');d['alternative'].update(status='observed',refs=['m1'])
        p.validate(tradeoff,packet)

    def test_separate_collaboration_and_portability_gate(self):
        packet=test_portrait.PortraitTests().packet();good=example(packet)
        for change in [lambda r:r['case'].pop('collaboration'),
                       lambda r:r['case'].update(collaboration=None),
                       lambda r:r.update(portability='scene_bound'),
                       lambda r:r.update(portability='generic'),
                       lambda r:r.update(portability='unsupported'),
                       lambda r:r['case']['collaboration']['pattern'].update(refs=['m2']),
                       lambda r:r['case']['collaboration']['boundary'].update(refs=['missing']),
                       lambda r:r['case']['collaboration']['pattern'].update(refs=[]),
                       lambda r:r['case']['collaboration']['pattern'].update(text='x'*241)]:
            bad=copy.deepcopy(good);change(bad)
            with self.assertRaises(ValueError):p.validate(bad,packet)
        # A real human reference outside the grounded scene is also insufficient.
        packet['messages'].append(dict(id='m3',role='user',text='SYNTHETIC unrelated task'))
        good['cache_key']=p.cache_key(packet)
        bad=copy.deepcopy(good);bad['case']['collaboration']['boundary']['refs']=['m3']
        with self.assertRaisesRegex(ValueError,'already grounded'):p.validate(bad,packet)
        # Scene-only observations remain available without inventing an abstraction.
        good.update(featured=False,portability='scene_bound');good['case']['collaboration']=None
        p.validate(good,packet)

    def test_v2_cache_is_not_reused_as_v3_and_legacy_render_is_unchanged(self):
        with temporary_workspace() as directory,contextlib.redirect_stdout(io.StringIO()):
            output=Path(directory);packet=test_portrait.PortraitTests().packet()
            report=test_developer_report.DeveloperReportTests().report()
            report.update(sessions=1,sample_key=portrait.sample_key([packet]))
            old=example(packet);old['schema']='practice-v2';old.pop('portability');old['case'].pop('collaboration')
            # Even a mistakenly copied current hash cannot upgrade an old review.
            portrait.write(output/'cache'/('practice-'+p.cache_key(packet)+'.json'),old)
            report['practices']=dict(schema='practice-v2',sample_key=report['sample_key'],generated_at='2026-11-03',
                reviewed_sessions=1,items=[dict(session=packet['session'],featured=True,case=old['case'])])
            portrait.write(output/'report.json',report)
            portrait.write(output/'manifest.json',dict(schema=report['method'],selected=[packet]))
            before=copy.deepcopy(report)
            self.assertEqual(len(p.prepare(output,True)),1)
            with self.assertRaises(ValueError):p.finalize(output)
            self.assertEqual(portrait.read(output/'report.json'),before)
            portrait.write(output/'legacy.backup.json',backup.bundle(report))
            backup.restore(output/'legacy.backup.json',output,replace=True)
            self.assertEqual(portrait.read(output/'report.json'),before)
            self.assertNotIn('collaboration',report['practices']['items'][0]['case'])


if __name__=='__main__':unittest.main()
