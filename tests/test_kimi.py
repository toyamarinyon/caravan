"""Synthetic Wire 1.5 cases; no personal conversation fixtures."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/caravan/scripts'))
import semantic as s
import kimi


class KimiTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'output/kimi-tests'
        root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.home = Path(self.tmp.name)
        self.out = self.home / 'output'
        self.now = s.datetime.now(s.timezone.utc)
        self.stamp = int((self.now - s.timedelta(minutes=1)).timestamp() * 1000)

    def tearDown(self):
        self.tmp.cleanup()

    def row(self, role, key, **overrides):
        message = dict(role=role, content=[dict(type='text', text=('架空の旅行案について、予算と移動時間を比べて説明してください。' * 3) + key)], toolCalls=[])
        meta = (dict(source='input', origin=dict(kind='user'), userMessageId=key) if role == 'user'
                else dict(source='llm', finish=dict(finishReason='completed'), messageId=key))
        return dict(type='agent.message.appended', kind='event', time=self.stamp,
                    message=dict(message=message, meta=meta), **overrides)

    def fixture(self, sid='conv-example', rows=None):
        root = self.home / kimi.DESKTOP_HOME
        path = root / 'sessions/workspace' / sid / 'agents/main/wire.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        if rows is None:
            rows = [self.row('user', 'u1'), self.row('assistant', 'a1'),
                    self.row('user', 'u2'), self.row('assistant', 'a2')]
        self.write_rows(path, rows)
        with (root / 'session_index.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(sessionId=sid, sessionDir=str(path.parents[2]), workDir='C:/Synthetic Trip')) + '\n')
        return path, rows

    def write_rows(self, path, rows, version='1.5'):
        path.write_text('\n'.join(json.dumps(r) for r in [dict(type='metadata', protocol_version=version)] + rows), encoding='utf-8')

    def prepare(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return s.prepare(self.home, self.out, consent=True, **kwargs)

    def test_canonical_roles_exclude_injections_thinking_tools_and_replays(self):
        path, rows = self.fixture()
        rows[1]['message']['message']['content'].append(dict(type='think', think='SECRET_THINKING'))
        injection = self.row('user', 'injected')
        injection['message']['meta']['origin']['kind'] = 'injection'
        tool_call = self.row('assistant', 'tool-call')
        tool_call['message']['meta']['finish']['finishReason'] = 'tool_calls'
        malformed = self.row('assistant', 'bad-meta'); malformed['message']['meta'] = []
        replay = dict(rows[0], time=self.stamp + 100)
        rows += [injection, tool_call, malformed, replay, self.row('tool', 'tool-result'),
                 self.row('user', 'subagent', agentId='child'),
                 dict(type='turn.prompt', input='DUPLICATE_PROMPT', time=self.stamp),
                 dict(type='context.append_message', message=dict(role='user', content='AUTO_CONTEXT')),
                 [], dict(type='agent.message.appended', kind='event', message=[])]
        self.write_rows(path, rows)
        stats = s.Counter()
        result = s.transcript(path, 'kimi', self.now-s.timedelta(days=1), self.now, stats,
                              dict(id='conv-example', project='C:/Synthetic Trip'))
        self.assertEqual([m['role'] for m in result['messages']], ['user','assistant','user','assistant'])
        self.assertEqual(result['execution']['status'], 'unsupported')
        for text in ('SECRET_THINKING','injected','tool-call','tool-result','subagent','DUPLICATE_PROMPT','AUTO_CONTEXT'):
            self.assertNotIn(text, json.dumps(result))
        self.assertEqual(stats['malformed_lines'], 1)

    def test_discovery_excludes_title_and_child_and_honors_exclusions(self):
        path, _ = self.fixture()
        self.fixture('ctitle-generated')
        child = path.parent.parent / 'child/wire.jsonl'; child.parent.mkdir()
        child.write_bytes(path.read_bytes())
        manifest = self.prepare()
        self.assertEqual(manifest['total_sessions'], 1)
        self.assertEqual(manifest['diagnostics']['kimi_excluded_auxiliary_sessions'], 1)
        self.assertEqual(self.prepare(exclude_project=Path('c:/synthetic trip'))['eligible_sessions'], 0)
        s.write(self.out / 'excluded-sessions.json', ['kimi:conv-example'])
        self.assertEqual(self.prepare()['total_sessions'], 0)

    def test_version_dates_and_invalid_shapes_fail_closed(self):
        path, rows = self.fixture()
        self.write_rows(path, rows, version='2.0')
        self.assertEqual(self.prepare()['diagnostics']['kimi_unsupported_wire_format'], 1)
        for row in rows: row['time'] = 0
        self.write_rows(path, rows)
        self.assertEqual(self.prepare()['total_sessions'], 0)
        for row in rows: row['time'] = 'not-a-timestamp'
        self.write_rows(path, rows)
        self.assertEqual(self.prepare()['diagnostics']['kimi_invalid_timestamp'], 4)
        path.write_text('[]\n', encoding='utf-8')
        self.assertEqual(self.prepare()['total_sessions'], 0)

    def test_index_required_and_never_followed_outside_root(self):
        path, _ = self.fixture()
        index = self.home / kimi.DESKTOP_HOME / 'session_index.jsonl'
        index.write_text(json.dumps(dict(sessionId='conv-outside', sessionDir=str(path.parents[2]), workDir='elsewhere')), encoding='utf-8')
        self.assertEqual(self.prepare()['total_sessions'], 0)
        index.write_text('null\n[]\n{"partial":', encoding='utf-8')
        self.assertEqual(self.prepare()['diagnostics']['kimi_invalid_index_rows'], 3)

    def test_single_turn_is_eligible(self):
        self.fixture(rows=[self.row('user','u'),self.row('assistant','a')])
        manifest = self.prepare()
        coverage = next(c for c in manifest['source_coverage'] if c['source']=='kimi')
        self.assertEqual(coverage['available_sessions'], 1)
        self.assertEqual(coverage['eligible_sessions'], 1)

    def test_budget_cache_render_and_private_share_boundary(self):
        path, rows = self.fixture()
        manifest = self.prepare(max_chars=1000)
        self.assertLessEqual(manifest['read_chars'], 1000)
        packet = manifest['selected'][0]
        review = dict(schema=s.RUBRIC, cache_key=packet['cache_key'], reviewer='synthetic only', purposes=[dict(id='unknown',evidence=[],reason='Synthetic fixture.')],
                      ratings={key:dict(status='uncertain',evidence=[],reason='test') for key in s.IDS})
        s.write(self.out / 'reviews.json', [review])
        with contextlib.redirect_stdout(io.StringIO()):
            report = s.finalize(self.out, self.out / 'reviews.json')
        self.assertEqual(report['sources'], {'kimi':1})
        self.assertNotIn('kimi', (self.out/'share-profile.json').read_text(encoding='utf-8'))
        self.assertEqual(self.prepare(max_chars=1000)['cache_hits'], 1)
        rows.append(self.row('user','new'))
        self.write_rows(path, rows)
        self.assertEqual(self.prepare(max_chars=1000)['cache_hits'], 0)
        with contextlib.redirect_stdout(io.StringIO()):
            audit = s.scan_execution(self.home, self.out, consent=True)
        self.assertIn('kimi', audit['limitations'])


if __name__ == '__main__':
    unittest.main()
