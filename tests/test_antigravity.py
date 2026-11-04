import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/caravan/scripts'))
import semantic as s


class AntigravityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / 'output/antigravity-tests'
        self.root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=self.root)
        self.home = Path(self.tmp.name)
        self.out = self.home / 'result'
        self.stamp = s.datetime.now(s.timezone.utc).isoformat()

    def tearDown(self):
        assert self.home.resolve().is_relative_to(self.root.resolve())
        self.tmp.cleanup()

    def fixture(self, sid='session-a', parent='', workspace='file:///C:/My%20Game'):
        root = self.home / '.gemini/antigravity-cli'
        path = root / 'brain' / sid / '.system_generated/logs/transcript.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(2):
            rows.extend([
                dict(step_index=i*2, type='USER_INPUT', source='USER_EXPLICIT', status='DONE',
                     created_at=self.stamp,
                     content='<USER_REQUEST>\n' + ('月のウサギのゲームの名前を考えて。理由も説明してほしい。' * 3) + str(i)
                     + '\n</USER_REQUEST>\n<ADDITIONAL_METADATA>PRIVATE_METADATA</ADDITIONAL_METADATA>'
                     + '<USER_SETTINGS_CHANGE>PRIVATE_SETTINGS</USER_SETTINGS_CHANGE>'),
                dict(step_index=i*2+1, type='PLANNER_RESPONSE', source='MODEL', status='DONE',
                     created_at=self.stamp, content='提案した名前とその理由。' + str(i)),
            ])
        path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
        with contextlib.closing(sqlite3.connect(root / 'conversation_summaries.db')) as c:
            with c:
                c.execute('CREATE TABLE IF NOT EXISTS conversation_summaries (conversation_id TEXT, workspace_uris TEXT, parent_conversation_id TEXT)')
                c.execute('INSERT INTO conversation_summaries VALUES (?,?,?)', (sid, json.dumps([workspace]), parent))
        return path, rows

    def prepare(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return s.prepare(self.home, self.out, consent=True, **kwargs)

    def test_real_format_filters_metadata_tools_and_duplicates(self):
        path, rows = self.fixture()
        for kind, source, status in [('SYSTEM_MESSAGE', 'SYSTEM', 'DONE'), ('TOOL_RESULT', 'MODEL', 'DONE'),
                                     ('USER_INPUT', 'SYSTEM', 'DONE'), ('PLANNER_RESPONSE', 'MODEL', 'RUNNING')]:
            rows.append(dict(type=kind, source=source, status=status, created_at=self.stamp,
                             content='<USER_REQUEST>UNWANTED</USER_REQUEST>'))
        rows.extend([rows[0], [], dict(type='USER_INPUT', source='USER_EXPLICIT', status='DONE',
                                     created_at=self.stamp, content='UNSUPPORTED_WRAPPER')])
        path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n{"partial":', encoding='utf-8')
        path.with_name('transcript_full.jsonl').write_text(path.read_text(encoding='utf-8'), encoding='utf-8')
        stats = s.Counter()
        session = s.transcript(path, 'antigravity', s.datetime.now(s.timezone.utc)-s.timedelta(days=1),
                               s.datetime.now(s.timezone.utc), stats, dict(id='session-a', project='C:/My Game'))
        self.assertEqual([m['role'] for m in session['messages']], ['user', 'assistant', 'user', 'assistant'])
        serialized = json.dumps(session)
        for forbidden in ['PRIVATE_METADATA', 'PRIVATE_SETTINGS', 'UNWANTED', 'UNSUPPORTED_WRAPPER']:
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(stats['malformed_lines'], 2)
        self.assertEqual(stats['antigravity_unsupported_user_format'], 1)
        manifest = self.prepare()
        self.assertEqual(manifest['total_sessions'], 1)
        self.assertEqual(manifest['diagnostics']['files_scanned'], 1)
        self.assertEqual(manifest['selected'][0]['source'], 'antigravity')

    def test_unique_sessions_subagents_and_project_exclusion(self):
        self.fixture('a')
        self.fixture('b')
        self.fixture('child', parent='a')
        manifest = self.prepare()
        self.assertEqual(manifest['total_sessions'], 2)
        self.assertEqual(len({p['session'] for p in manifest['selected']}), 2)
        self.assertEqual(manifest['diagnostics']['excluded_subagent_files'], 1)
        self.assertEqual(self.prepare(exclude_project=Path('c:\\my game'))['eligible_sessions'], 0)

    def test_persistent_and_command_line_exclusions(self):
        self.fixture('probe')
        self.fixture('other')
        s.write(self.out / 'excluded-sessions.json', ['antigravity:probe'])
        manifest = self.prepare(exclude_sessions=['antigravity:other'])
        self.assertEqual(manifest['total_sessions'], 0)
        self.assertEqual(manifest['diagnostics']['excluded_sessions'], 2)
        self.assertEqual(len(self.prepare()['selected']), 1)
        s.write(self.out / 'excluded-sessions.json', {'wrong': 'shape'})
        with self.assertRaisesRegex(ValueError, 'excluded-sessions'):
            self.prepare()

    def test_dates_limits_cache_and_appended_turn(self):
        path, rows = self.fixture()
        packet = self.prepare(max_chars=1000)['selected'][0]
        review = dict(schema=s.RUBRIC, cache_key=packet['cache_key'], reviewer='synthetic test only', purposes=[dict(id='unknown',evidence=[],reason='Synthetic fixture.')],
                      ratings={key: dict(status='uncertain', evidence=[], reason='test') for key in s.IDS})
        s.write(self.out / 'cache' / (packet['cache_key'] + '.json'), review)
        self.assertEqual(self.prepare(max_chars=1000)['cache_hits'], 1)
        with path.open('a', encoding='utf-8') as stream:
            stream.write('\n' + json.dumps(dict(type='PLANNER_RESPONSE', source='MODEL', status='DONE',
                                              created_at=self.stamp, content='追加の説明。')))
        changed = self.prepare(max_chars=1000)
        self.assertEqual(changed['cache_hits'], 0)
        self.assertLessEqual(changed['read_chars'], 1000)
        for row in rows:
            row['created_at'] = '2000-01-01T00:00:00Z'
        path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
        self.assertEqual(self.prepare()['total_sessions'], 0)

    def test_missing_metadata_is_reported_and_no_database_fallback(self):
        self.fixture()
        db = self.home / '.gemini/antigravity-cli/conversation_summaries.db'
        db.write_bytes(b'unsupported database')
        manifest = self.prepare()
        self.assertEqual(len(manifest['selected']), 1)
        self.assertEqual(manifest['diagnostics']['antigravity_unreadable_metadata'], 1)
        self.assertEqual(manifest['diagnostics']['antigravity_missing_project'], 1)

    def test_final_report_accepts_source_without_leaking_original(self):
        self.fixture()
        packet = self.prepare()['selected'][0]
        review = dict(schema=s.RUBRIC, cache_key=packet['cache_key'], reviewer='synthetic test only', purposes=[dict(id='unknown',evidence=[],reason='Synthetic fixture.')],
                      ratings={key: dict(status='uncertain', evidence=[], reason='test') for key in s.IDS})
        s.write(self.out / 'reviews.json', [review])
        with contextlib.redirect_stdout(io.StringIO()):
            report = s.finalize(self.out, self.out / 'reviews.json')
        self.assertEqual(report['sources'], {'antigravity': 1})
        self.assertNotIn('月のウサギ', (self.out / 'index.html').read_text(encoding='utf-8'))
        self.assertNotIn('antigravity', (self.out / 'share-profile.json').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
