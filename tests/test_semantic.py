import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'skills/caravan/scripts'
sys.path.insert(0,str(SCRIPTS))
import semantic as s

class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.root=SCRIPTS.parents[2]/'output'/'semantic-tests'
        self.root.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=self.root)
        self.home=Path(self.tmp.name);self.out=self.home/'result'

    def tearDown(self):
        assert self.home.resolve().is_relative_to(self.root.resolve())
        self.tmp.cleanup()

    def fixture(self,n=3):
        stamp=s.datetime.now(s.timezone.utc).isoformat()
        for i in range(n):
            path=self.home/'.codex/sessions'/f'{i}.jsonl';path.parent.mkdir(parents=True,exist_ok=True)
            rows=[dict(type='session_meta',payload=dict(id=str(i),cwd='project'+str(i%3)))]
            for j,role in enumerate(['user','assistant','user','assistant','user']):
                rows.append(dict(type='response_item',timestamp=stamp,payload=dict(type='message',role=role,
                    content=[dict(type='output_text' if role=='assistant' else 'input_text',text=('この文章はテスト用の長い会話です。'*100)+str(j))])))
            path.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows),encoding='utf-8')

    def prepare(self,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return s.prepare(self.home,self.out,consent=True,**kwargs)

    def review(self,packet):
        return dict(schema=s.RUBRIC,cache_key=packet['cache_key'],reviewer='test fixture, not a real model review', purposes=[dict(id='unknown',evidence=[],reason='Synthetic fixture.')],
            ratings={id:dict(status='not_observed',evidence=[],reason='Test-only synthetic review') for id in s.IDS})

    def test_consent_precedes_read_and_write(self):
        with self.assertRaisesRegex(ValueError,'Consent required'):
            s.prepare(self.home,self.out)
        self.assertFalse(self.out.exists())

    def test_structured_answers_keep_question_ownership_and_visible_omissions(self):
        text=json.dumps([dict(questionItemId='q1',question='AI PROVIDED WORDING',answer='SELECTED ANSWER')])
        items=s.attributed_messages('user',text)
        self.assertEqual(items,[('assistant','AI PROVIDED WORDING','structured_question'),
                                ('user','SELECTED ANSWER','structured_answer')])
        self.assertEqual(s.attributed_messages('user','<send_user_message_question_reply>\n'+text+'\n</send_user_message_question_reply>'),items)
        self.assertEqual(s.attributed_messages('assistant',text),[('assistant',text,'message')])
        self.assertEqual(s.attributed_messages('user','{"answer":"ordinary JSON"}')[0][2],'message')
        masked=s.redact('code:\n```secret code```\n> quoted instructions\nhttps://example.org/a C:/private/file\ntoken=privatevalue')
        self.assertIn('[code omitted]',masked);self.assertIn('[quoted text omitted]',masked)
        self.assertIn('https://example.org/a',masked);self.assertIn('[local path]',masked)
        for value in ('secret code','quoted instructions','privatevalue','C:/private'):self.assertNotIn(value,masked)

    def test_any_source_packet_exclusion_and_structured_transcript(self):
        self.fixture(3);initial=self.prepare();key=initial['selected'][0]['session']
        current=self.prepare(exclude_sessions=['sample:'+key])
        self.assertEqual(len(current['selected']),2)
        self.assertNotIn(key,[p['session'] for p in current['selected']])
        path=self.home/'.codex/sessions/0.jsonl'
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        rows[1]['payload']['content'][0]['text']='<send_user_message_question_reply>\n'+json.dumps([dict(questionItemId='q1',question='AI question',answer='Human answer')])+'\n</send_user_message_question_reply>'
        path.write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
        now=s.datetime.now(s.timezone.utc)
        parsed=s.transcript(path,'codex',now-s.timedelta(days=1),now,s.Counter())
        self.assertEqual([(m['role'],m['origin']) for m in parsed['messages'][:2]],
                         [('assistant','structured_question'),('user','structured_answer')])
        with self.assertRaises(ValueError):self.prepare(exclude_sessions=['sample:invalid'])

    def test_bounded_deterministic_sampling_and_cache(self):
        self.fixture(18);m=self.prepare()
        self.assertEqual(len(m['selected']),12)
        self.assertLessEqual(m['read_chars'],24000)
        self.assertTrue(all(len(p['messages'])<=5 for p in m['selected']))
        self.assertTrue(all(any(x['role']=='assistant' for x in p['messages']) for p in m['selected']))
        for p in m['selected']: s.write(self.out/'cache'/f"{p['cache_key']}.json",self.review(p))
        again=self.prepare()
        self.assertEqual(again['cache_hits'],12)
        self.assertEqual(again['new_read_chars'],0)
        self.assertEqual([p['cache_key'] for p in m['selected']],[p['cache_key'] for p in again['selected']])
        short=self.prepare(max_chars=2000)
        self.assertLessEqual(short['read_chars'],2000)

    def test_changed_transcript_invalidates_review(self):
        self.fixture(1);m=self.prepare();packet=m['selected'][0]
        s.write(self.out/'cache'/f"{packet['cache_key']}.json",self.review(packet))
        path=self.home/'.codex/sessions/0.jsonl'
        text=path.read_text(encoding='utf-8');path.write_text(text.replace('長い会話','新しい会話'),encoding='utf-8')
        again=self.prepare();self.assertEqual(again['cache_hits'],0)
        with self.assertRaisesRegex(ValueError,'Stale'):
            s.validate_review(self.review(packet),again['selected'][0])

    def mixed_fixture(self,n=1):
        self.fixture(24)
        # More Codex project strata than the whole light budget reproduces the old starvation.
        for i,path in enumerate(sorted((self.home/'.codex/sessions').glob('*.jsonl'))):
            rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            rows[0]['payload']['cwd']='many-projects-'+str(i)
            path.write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
        stamp=s.datetime.now(s.timezone.utc).isoformat()
        for i in range(n):
            claude=self.home/'.claude/projects'/f'project-{i}'/f'{i}.jsonl'
            ag=self.home/'.gemini/antigravity-cli/brain'/f'ag-{i}'/'.system_generated/logs/transcript.jsonl'
            claude.parent.mkdir(parents=True);ag.parent.mkdir(parents=True)
            kroot=self.home/s.kimi.DESKTOP_HOME
            kpath=kroot/'sessions/workspace'/f'conv-{i}'/'agents/main/wire.jsonl'
            kpath.parent.mkdir(parents=True)
            with (kroot/'session_index.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(dict(sessionId=f'conv-{i}',workDir='kimi-project'))+'\n')
            crows=[];arows=[];krows=[dict(type='metadata',protocol_version='1.5')]
            for j,role in enumerate(['user','assistant','user','assistant']):
                text='SYNTHETIC TEST ONLY. '*12+str(j)
                kmeta=(dict(source='input',origin=dict(kind='user'),userMessageId=str(j)) if role=='user'
                       else dict(source='llm',finish=dict(finishReason='completed'),messageId=str(j)))
                krows.append(dict(type='agent.message.appended',kind='event',
                                  time=int(s.base.parse_time(stamp).timestamp()*1000),
                                  message=dict(message=dict(role=role,content=[dict(type='text',text=text)]),meta=kmeta)))
                crows.append(dict(type=role,timestamp=stamp,sessionId=str(i),cwd='claude-project',message=dict(role=role,content=text)))
                arows.append(dict(step_index=j,type='USER_INPUT' if role=='user' else 'PLANNER_RESPONSE',
                                  source='USER_EXPLICIT' if role=='user' else 'MODEL',status='DONE',created_at=stamp,
                                  content='<USER_REQUEST>'+text+'</USER_REQUEST>' if role=='user' else text))
            claude.write_text('\n'.join(json.dumps(row) for row in crows),encoding='utf-8')
            ag.write_text('\n'.join(json.dumps(row) for row in arows),encoding='utf-8')
            kpath.write_text('\n'.join(json.dumps(row) for row in krows),encoding='utf-8')

    def test_all_sources_survive_many_projects_in_all_modes(self):
        self.mixed_fixture()
        for mode,(limit,budget) in s.MODES.items():
            m=self.prepare(mode=mode)
            counts=s.Counter(p['source'] for p in m['selected'])
            self.assertEqual(counts,{'codex':limit-3,'claude':1,'antigravity':1,'kimi':1})
            self.assertLessEqual(m['read_chars'],budget)
            self.assertEqual({row['source'] for row in m['source_coverage'] if row['selected_sessions']},set(s.SOURCES))
            self.assertEqual(m['sampler'],s.SAMPLER)
        short=self.prepare(max_chars=2400)
        self.assertEqual({p['source'] for p in short['selected']},set(s.SOURCES))
        self.assertLessEqual(short['read_chars'],2400)
        original=(self.out/'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'every eligible agent'):self.prepare(max_chars=1000)
        self.assertEqual((self.out/'manifest.json').read_bytes(),original)

    def test_equal_source_rounds_cache_and_exclusion_coverage(self):
        self.mixed_fixture(5)
        m=self.prepare(mode='light')
        counts=s.Counter(p['source'] for p in m['selected'])
        self.assertEqual(set(counts),set(s.SOURCES))
        self.assertEqual(sorted(counts.values()),[1,1,2,2])
        for p in m['selected']:s.write(self.out/'cache'/f"{p['cache_key']}.json",self.review(p))
        again=self.prepare(mode='light')
        self.assertEqual(again['cache_hits'],6)
        self.assertEqual(again['selected'],m['selected'])
        excluded=self.prepare(mode='light',exclude_project='claude-project')
        row=next(row for row in excluded['source_coverage'] if row['source']=='claude')
        self.assertEqual((row['available_sessions'],row['excluded_project_sessions'],row['eligible_sessions'],row['selected_sessions']),(5,5,0,0))
        self.assertIn('除外',row['reason'])

    def test_short_source_is_reported_and_never_given_fake_reviews(self):
        self.mixed_fixture()
        path=next((self.home/'.claude/projects').rglob('*.jsonl'))
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        rows=[row for row in rows if row['type']=='assistant']+[dict(rows[0],message=dict(content='短い質問'))]
        path.write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
        m=self.prepare(mode='light')
        row=next(row for row in m['source_coverage'] if row['source']=='claude')
        self.assertEqual((row['available_sessions'],row['eligible_sessions'],row['selected_sessions']),(1,1,1))
        for p in m['selected']:s.write(self.out/'cache'/f"{p['cache_key']}.json",self.review(p))
        with contextlib.redirect_stdout(io.StringIO()):report=s.finalize(self.out)
        self.assertEqual(report['sampling']['source_coverage'],m['source_coverage'])

    def test_invalid_evidence_and_missing_reviews_fail_closed(self):
        self.fixture(1);m=self.prepare();p=m['selected'][0];review=self.review(p)
        review['ratings']['execution']=dict(status='observed',evidence=['unknown'],reason='test')
        with self.assertRaises(ValueError):s.validate_review(review,p)
        review['ratings']['execution']['evidence']=[next(x['id'] for x in p['messages'] if x['role']=='assistant')]
        with self.assertRaisesRegex(ValueError,'human evidence'):s.validate_review(review,p)
        with self.assertRaisesRegex(ValueError,'Missing review'):s.finalize(self.out)
        self.assertFalse((self.out/'report.json').exists())

    def test_unknown_is_not_a_zero_and_no_raw_excerpt_in_report(self):
        self.fixture(1);m=self.prepare();p=m['selected'][0];review=self.review(p)
        review['ratings']['execution']=dict(status='uncertain',evidence=[],reason='Context missing')
        s.write(self.out/'reviews.json',[review])
        with contextlib.redirect_stdout(io.StringIO()):r=s.finalize(self.out,self.out/'reviews.json')
        metric=next(p for p in r['perspectives'] if p['id']=='execution')
        self.assertIsNone(metric['session_rate']);self.assertEqual(metric['uncertain_sessions'],1)
        self.assertNotIn('この文章はテスト用',json.dumps(r,ensure_ascii=False))
        self.assertEqual(r['method'],s.RUBRIC)

    def test_repeated_finalize_updates_only_fixed_html(self):
        self.fixture(1);packet=self.prepare()['selected'][0]
        s.write(self.out/'reviews.json',[self.review(packet)])
        with contextlib.redirect_stdout(io.StringIO()):s.finalize(self.out,self.out/'reviews.json')
        target=self.out/'index.html'
        target.write_text('old preview',encoding='utf-8')
        console=io.StringIO()
        with contextlib.redirect_stdout(console):s.finalize(self.out)
        self.assertEqual({p.name for p in self.out.glob('*.html')},{'index.html','developer.html'})
        self.assertIn(str(target.resolve()),console.getvalue())
        self.assertNotEqual(target.read_text(encoding='utf-8'),'old preview')
        self.assertIn('rendered_at',target.read_text(encoding='utf-8'))

if __name__=='__main__':unittest.main()
