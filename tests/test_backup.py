import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/caravan/scripts'))
import backup
import semantic
import test_developer_report
import test_portrait
from test_distribution import temporary_workspace
import portrait


class BackupTests(unittest.TestCase):
    def report(self):
        r=test_developer_report.DeveloperReportTests().report()
        t=test_portrait.PortraitTests(); packets=[t.packet(i) for i in range(3)]
        r['portrait']=portrait.aggregate(packets,[t.review(p) for p in packets])
        return r

    def test_round_trip_keeps_all_private_analysis_and_dates(self):
        with temporary_workspace() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);source=root/'source';source.mkdir()
            report=self.report();semantic.write(source/'report.json',report)
            saved=root/'private.json';backup.export(source,saved)
            dest=root/'restored';backup.restore(saved,dest)
            self.assertEqual(json.loads((dest/'report.json').read_text(encoding='utf-8')),backup.current_report(report))
            self.assertIn('PRIVATE_REASON',(dest/'index.html').read_text(encoding='utf-8'))
            shared=(dest/'share-profile.json').read_text(encoding='utf-8')
            self.assertNotIn('PRIVATE_REASON',shared);self.assertNotIn('tones',shared)
            self.assertTrue((dest/'developer.html').exists())
            self.assertFalse((dest/'manifest.json').exists())
            with self.assertRaises(ValueError):backup.restore(saved,dest)
            backup.restore(saved,dest,replace=True)
            self.assertEqual(backup.read(dest/'before-restore.backup.json')['report'],backup.current_report(report))

    def test_export_removes_legacy_and_refreshes_names_without_changing_evidence(self):
        report=self.report()
        report['type_name']='OBSOLETE'
        report['portrait']['classification']['type_catalog'][0]['name']='OBSOLETE'
        saved=backup.bundle(report)['report']
        self.assertFalse(set(backup.LEGACY_FIELDS) & set(saved))
        self.assertNotIn('OBSOLETE', json.dumps(saved))
        for key in ('perspectives','generated_at','sessions'):
            self.assertEqual(saved[key],report[key])
        for key in ('axes','tones','discoveries','generated_at'):
            self.assertEqual(saved['portrait'][key],report['portrait'][key])
        self.assertEqual(report['type_name'],'OBSOLETE')
        legacy=self.report(); del legacy['portrait']
        self.assertEqual(backup.bundle(legacy)['report'],legacy)

    def test_old_semantic_v3_portrait_v1_backup_and_render(self):
        report=self.report(); report['method']='semantic-38-v3'; report['portrait']['schema']='portrait-v1'
        with temporary_workspace() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory); path=root/'legacy.json'; semantic.write(path,backup.bundle(report))
            dest=root/'result'; backup.restore(path,dest)
            restored=json.loads((dest/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(restored['method'],'semantic-38-v3')
            self.assertEqual(restored['portrait']['schema'],'portrait-v1')
            self.assertTrue((dest/'index.html').exists())
            self.assertIn('portrait-v1', (dest/'share-profile.json').read_text())

    def test_reject_invalid_before_touching_existing_result(self):
        value=backup.bundle(self.report())
        for edit in (lambda v:v.update(schema='future'),lambda v:v['report'].update(method='future'),
                     lambda v:v['report'].update(journey={'image':'https://example.invalid'}),
                     lambda v:v['report'].update(__proto__={}),
                     lambda v:v['report'].update(days=float('nan'))):
            invalid=copy.deepcopy(value);edit(invalid)
            with self.assertRaises(ValueError):backup.validate(invalid)
        with temporary_workspace() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);dest=root/'result';dest.mkdir()
            (dest/'index.html').write_text('ORIGINAL',encoding='utf-8')
            del value['report']['portrait']['classification']['type_catalog']
            semantic.write(root/'bad.json',value)
            with self.assertRaises(ValueError):backup.restore(root/'bad.json',dest,True)
            self.assertEqual((dest/'index.html').read_text(encoding='utf-8'),'ORIGINAL')

    def test_restore_does_not_keep_unrelated_execution_audit(self):
        with temporary_workspace() as directory, contextlib.redirect_stdout(io.StringIO()):
            root=Path(directory);dest=root/'result';dest.mkdir()
            semantic.write(dest/'report.json',self.report())
            semantic.write(dest/'execution-audit.json',{'schema':'execution-events-v1'})
            semantic.write(root/'backup.json',backup.bundle(self.report()))
            backup.restore(root/'backup.json',dest,True)
            self.assertFalse((dest/'execution-audit.json').exists())
            self.assertEqual(backup.read(dest/'before-restore.backup.json')['execution_audit']['schema'],'execution-events-v1')


if __name__=='__main__':unittest.main()
