import contextlib
import copy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/caravan/scripts'))
import execution as e
import semantic as s


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.stamp=(self.now-timedelta(minutes=1)).isoformat()
        self.cutoff=self.now-timedelta(days=90)

    def collector(self,source='codex'):
        return e.Collector(source,self.cutoff,self.now)

    def feed(self,c,kind,**payload):
        c.feed(dict(timestamp=self.stamp,type=kind,payload=payload))

    def test_direct_calls_and_opaque_wrappers_do_not_expose_content_or_claim_success(self):
        c=self.collector()
        self.feed(c,'turn_context',model='gpt-6.1',effort='high',cwd='PRIVATE_PATH')
        self.feed(c,'response_item',type='function_call',name='mcp__private__read',call_id='private-call',arguments='SECRET_ARGUMENT')
        self.feed(c,'response_item',type='function_call_output',call_id='private-call',output='SECRET_RESULT')
        self.feed(c,'response_item',type='custom_tool_call',name='exec',call_id='wrapper',input='mcp__secret__read(); spawn_agent(); SECRET_CODE')
        self.feed(c,'response_item',type='function_call',name='spawn_agent',call_id='child')
        record=c.finish();events=record['events']
        self.assertEqual([(x['feature'],x['phase']) for x in events],
                         [('model','recorded'),('effort','recorded'),('mcp','requested'),('mcp','returned'),('opaque_tool','requested'),('delegation','requested')])
        encoded=json.dumps(record)
        for secret in ['PRIVATE_PATH','private-call','mcp__private','SECRET','spawn_agent','success']:
            self.assertNotIn(secret,encoded)
        self.assertTrue(all(x['actor']=='agent' for x in events[2:]))

    def test_claude_skill_results_dedup_and_sidechains(self):
        c=self.collector('claude')
        row=dict(type='assistant',timestamp=self.stamp,message=dict(model='private-deployment',content=[
            dict(type='tool_use',name='Skill',id='s1',input=dict(skill='private-skill',args='SECRET')),
            dict(type='tool_use',name='Agent',id='a1',input=dict(prompt='SECRET'))]))
        c.feed(row);c.feed(row);c.feed(dict(row,isSidechain=True))
        c.feed(dict(type='user',timestamp=self.stamp,message=dict(content=[
            dict(type='tool_result',tool_use_id='s1',is_error=True,content='SECRET'),
            dict(type='tool_result',tool_use_id='unknown',content='SECRET')])))
        record=c.finish()
        self.assertEqual(len(record['events']),4)
        self.assertEqual(record['events'][-1]['phase'],'error')
        self.assertEqual(record['events'][0]['value'],'custom-or-unknown')
        self.assertNotIn('private',json.dumps(record))
        self.assertNotIn('SECRET',json.dumps(record))

    def test_dates_unsupported_source_and_retention_cap(self):
        c=self.collector()
        for stamp in [(self.cutoff-timedelta(seconds=1)).isoformat(),(self.now+timedelta(seconds=1)).isoformat()]:
            c.feed(dict(timestamp=stamp,type='turn_context',payload=dict(model='gpt-6.1')))
        self.assertFalse(c.events)
        for i in range(e.LIMIT+10):
            self.feed(c,'response_item',type='function_call',name='exec',call_id=str(i))
        self.assertEqual(len(c.events),e.LIMIT)
        self.assertEqual(c.finish()['omitted_events'],10)
        unsupported=self.collector('antigravity')
        self.feed(unsupported,'turn_context',model='gpt-6.1',text='Skill MCP spawn_agent')
        self.assertEqual(unsupported.finish()['status'],'unsupported')
        self.assertEqual(unsupported.events,[])

    def test_excerpt_budget_and_temporal_scope(self):
        c=self.collector()
        self.feed(c,'turn_context',model='gpt-6.1',effort='high')
        start=(self.now-timedelta(seconds=30)).isoformat()
        for i in range(20):
            c.feed(dict(timestamp=start,type='response_item',payload=dict(type='function_call',name='exec',call_id=str(i))))
        future=(self.now+timedelta(seconds=1)).isoformat()
        record=c.finish()
        record['events'].append(dict(id='future',date=future,feature='model',phase='recorded',value='gpt-7'))
        subset=e.excerpt(record,start,self.now.isoformat(),600)
        self.assertLessEqual(e.size(subset),600)
        self.assertLessEqual(len(subset['events']),6)
        self.assertNotIn('future',[x['id'] for x in subset['events']])
        self.assertTrue(any(x['scope']=='prior_context' for x in subset['events']))
        session=dict(key='fixture',source='codex',fingerprint='fixture',execution=record,messages=[
            dict(id='m'+str(i),role=role,date=start,text='SYNTHETIC '*200)
            for i,role in enumerate(['user','assistant','user','assistant'])])
        for budget in [600,1000,2000]:
            packet=s.window(session,budget)
            self.assertLessEqual(s.packet_size(packet),budget)
            self.assertEqual({m['role'] for m in packet['messages']},{'user','assistant'})

    def test_tooling_observation_requires_human_evidence_even_with_events(self):
        packet=dict(cache_key='fixture',messages=[dict(id='m1',role='user'),dict(id='m2',role='assistant')],
                    execution=dict(events=[dict(id='e1')]))
        review=dict(schema=s.RUBRIC,cache_key='fixture',reviewer='SYNTHETIC TEST', purposes=[dict(id='unknown',evidence=[],reason='Synthetic fixture.')],
                    ratings={d:dict(status='uncertain',evidence=[],reason='Synthetic context insufficient.') for d in s.IDS})
        rating=dict(status='observed',evidence=['m1'],reason='Synthetic instruction explicitly chooses a model.',
                    forms=[dict(id='fixed',evidence=['m1'])],event_evidence=['e1'])
        review['ratings']['model_routing']=rating
        s.validate_review(review,packet)
        invalid=copy.deepcopy(review);invalid['ratings']['model_routing']['evidence']=[]
        with self.assertRaisesRegex(ValueError,'human evidence'):s.validate_review(invalid,packet)
        invalid=copy.deepcopy(review);invalid['ratings']['model_routing']['event_evidence']=['missing']
        with self.assertRaisesRegex(ValueError,'event reference'):s.validate_review(invalid,packet)
        invalid=copy.deepcopy(review);invalid['ratings']['ownership']['event_evidence']=['e1']
        with self.assertRaisesRegex(ValueError,'event reference'):s.validate_review(invalid,packet)

    def test_audit_consent_exclusion_archive_dedup_and_metadata_cache_invalidation(self):
        root=Path(__file__).resolve().parents[1]/'output/execution-tests'
        root.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            home=Path(directory);out=home/'result'
            with patch.object(s,'source_files',side_effect=AssertionError('must not read')):
                with self.assertRaisesRegex(ValueError,'Consent'):s.scan_execution(home,out)
            rows=[dict(type='session_meta',payload=dict(id='same',cwd='fixture')),
                  dict(type='turn_context',timestamp=self.stamp,payload=dict(model='gpt-6.1',effort='high'))]
            for i,role in enumerate(['user','assistant','user','assistant']):
                rows.append(dict(type='response_item',timestamp=self.stamp,payload=dict(type='message',role=role,content='SYNTHETIC PRIVATE BODY '*10+str(i))))
            for folder in ['sessions','archived_sessions']:
                path=home/'.codex'/folder/'fixture.jsonl';path.parent.mkdir(parents=True)
                path.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                audit=s.scan_execution(home,out,consent=True)
                first=s.prepare(home,out,consent=True)
                rows[1]['payload']['effort']='low'
                path.write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
                # Use one canonical file to test metadata-only changes to the cache key.
                (home/'.codex/sessions/fixture.jsonl').write_text(path.read_text(encoding='utf-8'),encoding='utf-8')
                second=s.prepare(home,out,consent=True)
                excluded=s.scan_execution(home,out,consent=True,exclude_project='fixture')
            self.assertEqual(audit['sessions'],1)
            self.assertEqual(excluded['sessions'],0)
            self.assertNotIn('PRIVATE BODY',json.dumps(audit))
            self.assertNotEqual(first['selected'][0]['cache_key'],second['selected'][0]['cache_key'])
            assert home.resolve().is_relative_to(root.resolve())


if __name__=='__main__':unittest.main()
