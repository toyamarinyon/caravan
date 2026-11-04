import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/caravan/scripts'))
import portrait
import representative as rep
import semantic


class RepresentativeTests(unittest.TestCase):
    def setup_sample(self, output):
        packets = [dict(session='synthetic', cache_key='fixture', messages=[
            dict(id='m1', role='user', text='SYNTHETIC TEST ONLY'),
            dict(id='m2', role='assistant', text='SYNTHETIC RESPONSE')])]
        classification = dict(evidence_ready=True, candidate_codes=['SGBC', 'EGBC'], profile=None)
        report = dict(method=semantic.RUBRIC, sample_key=portrait.sample_key(packets),
                      generated_at='original-date', portrait=dict(schema='portrait-v2', axes=[], classification=classification))
        portrait.write(output / 'manifest.json', dict(schema=semantic.RUBRIC, selected=packets))
        portrait.write(output / 'report.json', report)
        review = dict(schema=rep.SCHEMA, cache_key=rep.key(report, packets), reviewer='SYNTHETIC TEST',
                      code='SGBC', reason='架空の選択を紹介するため。', evidence=[dict(session='synthetic', refs=['m1'])])
        return report, review

    def test_selection_preserves_classification_date_and_sharing(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp); report, review = self.setup_sample(output)
            portrait.write(output / 'review.json', review)
            with patch.object(semantic, 'render_pages'):
                rep.finalize(output, output / 'review.json')
            actual = portrait.read(output / 'report.json')
            self.assertEqual(actual['portrait'], report['portrait'])
            self.assertEqual(actual['generated_at'], report['generated_at'])
            self.assertEqual(actual['representative']['code'], 'SGBC')
            self.assertFalse((output / 'share-profile.json').exists())
            rep.validate_saved(actual['representative'], actual)
            actual['portrait']['axes'] = ['changed']
            with self.assertRaisesRegex(ValueError, 'different portrait'):
                rep.validate_saved(actual['representative'], actual)

    def test_stale_non_candidate_and_assistant_evidence_fail_before_write(self):
        from unittest.mock import patch
        for field, value in [('code', 'EDIT'), ('cache_key', 'stale'),
                             ('evidence', [dict(session='synthetic', refs=['m2'])]),
                             ('evidence', [])]:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp); original, review = self.setup_sample(output)
                review[field] = value; portrait.write(output / 'review.json', review)
                with patch.object(semantic, 'render_pages'), self.assertRaises(ValueError):
                    rep.finalize(output, output / 'review.json')
                self.assertEqual(portrait.read(output / 'report.json'), original)

    def test_abstention_and_consent(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp); report, review = self.setup_sample(output)
            with self.assertRaisesRegex(ValueError, 'Consent'): rep.prepare(output)
            with contextlib.redirect_stdout(io.StringIO()): rep.prepare(output, True)
            self.assertEqual(portrait.read(output / 'representative-pending.json')['packets'][0]['session'], 'synthetic')
            review.update(code=None, evidence=[])
            portrait.write(output / 'review.json', review)
            with patch.object(semantic, 'render_pages'): rep.finalize(output, output / 'review.json')
            self.assertIsNone(portrait.read(output / 'report.json')['representative']['code'])

    def test_render_and_backup_round_trip_for_selected_mixed_and_insufficient(self):
        import subprocess
        import backup
        import diagnose
        from test_developer_report import DeveloperReportTests
        from test_portrait import PortraitTests
        fixture = PortraitTests()
        packets = [fixture.packet(i) for i in range(3)]
        for mode in ('mixed', 'selected', 'abstained', 'insufficient'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                output = Path(tmp)
                report = DeveloperReportTests().report()
                report.update(sample_key=portrait.sample_key(packets), sessions=3, messages=6)
                report['portrait'] = portrait.aggregate(packets, [fixture.review(p, 'uncertain' if mode == 'insufficient' else 'both') for p in packets])
                if mode in ('selected', 'abstained'):
                    report['representative'] = dict(schema=rep.SCHEMA, sample_key=report['sample_key'],
                        portrait_key=portrait.digest(rep.context(report)), cache_key=rep.key(report, packets),
                        reviewer='SYNTHETIC TEST', generated_at='2026-11-04T00:00:00+00:00',
                        code='SGBC' if mode == 'selected' else None, reason='架空の代表選択の理由。',
                        evidence=[dict(session=packets[0]['session'], refs=['m1'])])
                restored = backup.bundle(report)['report']
                self.assertEqual(restored.get('representative'), report.get('representative'))
                with contextlib.redirect_stdout(io.StringIO()): semantic.render_pages(output, report)
                portrait.write(output / 'share.json', diagnose.make_share(report))
                self.assertNotIn('架空の代表選択の理由', (output / 'share.json').read_text())
                subprocess.run(['node', str(Path(__file__).with_name('report_ui.cjs')), str(output / 'index.html'), str(output / 'share.json')], check=True, capture_output=True)
