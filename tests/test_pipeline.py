"""Offline regression tests. All PDFs, archives and repositories are synthetic."""
import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import fitz
import common
import fetch_paper as fp
import extract_figures as ef


def make_pdf(path, watermark=None, caption=True, scan=False):
    doc = fitz.open()
    page = doc.new_page()
    if not scan:
        page.insert_text((60,60), 'Synthetic Test Paper', fontsize=16)
        page.insert_text((60,85), 'A controlled fixture for offline tests. No research claims.', fontsize=10)
        if watermark:
            page.insert_text((60,105), 'arXiv:' + watermark, fontsize=10)
    page.draw_rect(fitz.Rect(60,130,300,230), color=(0,0,0), fill=(0.8,0.8,0.8))
    if caption and not scan:
        page.insert_text((60,250), 'Figure 1: A synthetic box.', fontsize=10)
    doc.save(path)
    doc.close()


def run_main(*args):
    with patch.object(sys, 'argv', ['fetch_paper.py', *map(str,args)]), contextlib.redirect_stdout(io.StringIO()):
        fp.main()


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tf:
        for name, value in entries:
            ti = tarfile.TarInfo(name)
            if value is None:
                ti.type = tarfile.SYMTYPE
                ti.linkname = '../outside'
                tf.addfile(ti)
            else:
                body = value.encode()
                ti.size = len(body)
                tf.addfile(ti, io.BytesIO(body))
    return stream.getvalue()


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def paper(self, watermark=None):
        dest = self.root / 'paper'
        dest.mkdir()
        make_pdf(dest/'paper.pdf', watermark)
        return dest


class SecurityTests(Workspace):
    def test_tar_valid(self):
        fp.safe_extract(archive([('sections/a.tex','hello')]), self.root/'source')
        self.assertEqual((self.root/'source/sections/a.tex').read_text(),'hello')
    def test_tar_sibling_prefix_escape(self):
        with self.assertRaises(ValueError):
            fp.safe_extract(archive([('../source-other/probe','bad')]),self.root/'source')
        self.assertFalse((self.root/'source-other').exists())
    def test_tar_absolute_path(self):
        with self.assertRaises(ValueError):
            fp.safe_extract(archive([(str(self.root/'outside'),'bad')]),self.root/'source')
        self.assertFalse((self.root/'outside').exists())
    def test_tar_symlink(self):
        with self.assertRaises(ValueError):
            fp.safe_extract(archive([('link',None)]),self.root/'source')
    def test_tar_preflight_before_writes(self):
        with self.assertRaises(ValueError):
            fp.safe_extract(archive([('ok.tex','ok'),('../source-bad/x','bad')]),self.root/'source')
        self.assertFalse((self.root/'source/ok.tex').exists())
    def test_flatten_escape(self):
        src=self.root/'source';src.mkdir()
        (self.root/'outside.tex').write_text('PRIVATE_FIXTURE')
        (src/'main.tex').write_text(r'\input{../outside.tex}')
        with self.assertRaises(ValueError): fp.flatten(src/'main.tex',src)
    def test_flatten_valid_nested(self):
        src=self.root/'source';src.mkdir()
        (src/'part.tex').write_text('EXPECTED')
        (src/'main.tex').write_text(r'\input{part}')
        self.assertIn('EXPECTED',fp.flatten(src/'main.tex',src))
    def test_flatten_symlink_escape(self):
        src=self.root/'source';src.mkdir()
        (self.root/'outside.tex').write_text('PRIVATE_FIXTURE')
        try: (src/'link.tex').symlink_to(self.root/'outside.tex')
        except OSError: self.skipTest('symlinks unavailable')
        (src/'main.tex').write_text(r'\input{link}')
        with self.assertRaises(ValueError): fp.flatten(src/'main.tex',src)
    def test_repository_url_validation(self):
        for bad in ['http://github.com/a/b','https://github.com.evil/a/b','https://github.com/a/b?x=1','https://github.com/a/b/tree/main','https://user:pass@github.com/a/b']:
            with self.subTest(url=bad), self.assertRaises(ValueError): fp.normalize_repo(bad)
        self.assertEqual(fp.normalize_repo('https://github.com/a/b.git'),'https://github.com/a/b')
    def test_untrusted_host_not_arxiv(self):
        self.assertEqual(fp.parse_target('https://notarxiv.example/2410.24164')['kind'],'url-pdf')
    def test_github_lookalike_not_code(self):
        self.assertNotEqual(fp.classify('https://evilgithub.com/a/b')[0],'code')
    def test_download_size_bound(self):
        response=io.BytesIO(b'abcdef')
        response.geturl=lambda: 'https://example.org/paper'
        with patch.object(fp.urllib.request,'urlopen',return_value=response):
            with self.assertRaises(ValueError): fp.http_get('https://example.org/paper',max_bytes=4)


class ProvenanceTests(Workspace):
    def test_invalid_pdf_does_not_poison_destination(self):
        bad=self.root/'invalid.pdf';bad.write_bytes(b'%PDF-invalid fixture')
        dest=self.root/'output'
        with self.assertRaises((RuntimeError,ValueError)):
            run_main(bad,'--dest',dest,'--offline')
        self.assertFalse((dest/'paper.pdf').exists())
        good=self.root/'valid.pdf';make_pdf(good)
        run_main(good,'--dest',dest,'--offline')
        self.assertTrue((dest/'paper.pdf').exists())
    def test_output_symlink_does_not_overwrite_user_notes(self):
        dest=self.paper()
        keep=self.root/'keep.txt';keep.write_text('private notes')
        try:(dest/'paper.txt').symlink_to(keep)
        except OSError:self.skipTest('symlinks unavailable')
        (dest/'outline.md').symlink_to(keep)
        run_main(dest,'--offline')
        self.assertEqual(keep.read_text(),'private notes')
        self.assertFalse((dest/'paper.txt').is_symlink())
    def test_unversioned_legacy_pdf_does_not_fetch_latest_metadata(self):
        dest=self.paper()
        common.write_json(dest/'meta.json',{'arxiv_id':'2410.24164','title':'Old fixture','authors':['Cached']})
        with patch.object(fp,'arxiv_meta',side_effect=AssertionError('cannot query latest for legacy PDF')):
            run_main(dest,'--level','quick')
        meta=common.read_json(dest/'meta.json')
        self.assertFalse(meta['pdf_version_verified'])
        self.assertNotIn('version',meta)
    def test_offline_quick_then_full(self):
        source=self.root/'input.pdf';make_pdf(source)
        dest=self.root/'output'
        with patch.object(fp,'http_get',side_effect=AssertionError('network forbidden')):
            run_main(source,'--dest',dest,'--offline','--level','quick')
            self.assertFalse((dest/'figures').exists())
            run_main(dest,'--offline')
        self.assertTrue((dest/'figures/fig-01.png').exists())
        self.assertEqual(common.read_json(dest/'meta.json')['pdf_sha256'],common.sha256_file(source))
    def test_api_failure_preserves_metadata(self):
        dest=self.paper('2410.24164v1')
        common.write_json(dest/'meta.json',{'arxiv_id':'2410.24164','version':'v1','authors':['Fixture Author'],'abstract':'Cached abstract'})
        with patch.object(fp,'arxiv_meta',return_value={}),patch.object(fp,'fetch_source',return_value='failed'),patch.object(fp,'hf_paper',return_value={}):
            run_main(dest)
        meta=common.read_json(dest/'meta.json')
        self.assertEqual(meta['authors'],['Fixture Author'])
        self.assertEqual(meta['abstract'],'Cached abstract')
        self.assertEqual(meta['version'],'v1')
    def test_version_is_pinned_on_rerun(self):
        dest=self.paper('2410.24164v1')
        run_main(dest,'--offline','--level','quick')
        with patch.object(fp,'arxiv_meta',return_value={'version':'v1','title':'Pinned title'}) as api:
            run_main(dest,'--level','quick')
        api.assert_called_once_with('2410.24164v1')
        self.assertEqual(common.read_json(dest/'meta.json')['resolved_arxiv_id'],'2410.24164v1')
    def test_api_version_mismatch_rejected(self):
        dest=self.paper('2410.24164v1')
        with patch.object(fp,'arxiv_meta',return_value={'version':'v2'}):
            with self.assertRaisesRegex(ValueError,'版本'): run_main(dest,'--level','quick')
    def test_different_requested_version_rejected(self):
        dest=self.paper('2410.24164v1')
        run_main(dest,'--offline','--level','quick')
        with self.assertRaises(ValueError): run_main('2410.24164v2','--dest',dest,'--level','quick')
    def test_changed_pdf_rejected(self):
        dest=self.paper();run_main(dest,'--offline','--level','quick')
        with (dest/'paper.pdf').open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'哈希'):run_main(dest,'--offline')
    def test_missing_pdf_cannot_change_existing_identity(self):
        dest=self.paper('2410.24164v1');run_main(dest,'--offline','--level','quick')
        old_meta=(dest/'meta.json').read_bytes()
        (dest/'paper.pdf').unlink()
        replacement=self.root/'other.pdf';make_pdf(replacement)
        with self.assertRaisesRegex(ValueError,'哈希'):
            run_main(replacement,'--dest',dest,'--offline')
        self.assertFalse((dest/'paper.pdf').exists())
        self.assertEqual((dest/'meta.json').read_bytes(),old_meta)
    def test_offline_selected_repository_can_be_pending(self):
        dest=self.paper()
        run_main(dest,'--offline','--code','https://github.com/example/model')
        meta=common.read_json(dest/'meta.json')
        self.assertEqual(meta['code']['status'],'not-cloned')
        self.assertIsNone(meta['code_dir'])
    def test_changed_source_rejected(self):
        dest=self.paper();src=dest/'source';src.mkdir()
        tex=src/'main.tex';tex.write_text(r'\documentclass{article}\begin{document}hello\end{document}')
        run_main(dest,'--offline')
        tex.write_text(tex.read_text()+'changed')
        with self.assertRaisesRegex(ValueError,'源码'):run_main(dest,'--offline')
    def test_legacy_source_is_explicitly_unverified(self):
        dest=self.paper('2410.24164v1');src=dest/'source';src.mkdir()
        (src/'main.tex').write_text(r'\documentclass{article}\begin{document}legacy\end{document}')
        run_main(dest,'--offline')
        self.assertEqual(common.read_json(dest/'meta.json')['source_status'],'user-or-legacy-source-unverified')
    def test_scan_is_flagged(self):
        source=self.root/'scan.pdf';make_pdf(source,scan=True)
        dest=self.root/'output';run_main(source,'--dest',dest,'--offline','--level','quick')
        self.assertEqual(common.read_json(dest/'meta.json')['text_status'],'needs-ocr-or-visual-reading')
    def test_candidate_not_official_or_cloned(self):
        dest=self.paper()
        with patch.object(fp,'collect_links',return_value={'code':[{'url':'https://github.com/example/baseline','score':99}]}),patch.object(fp,'clone',side_effect=AssertionError('must not clone')):
            run_main(dest,'--offline')
        meta=common.read_json(dest/'meta.json')
        self.assertNotIn('official_code',meta)
        self.assertEqual(meta['code']['status'],'candidates-only')
        self.assertEqual(len(meta['code_candidates']),1)
    def test_non_git_directory_is_not_valid_clone(self):
        directory=self.root/'code';directory.mkdir();(directory/'note').write_text('keep')
        self.assertEqual(fp.clone('https://github.com/example/model',directory),'invalid-existing-directory')
        self.assertEqual((directory/'note').read_text(),'keep')
    def test_existing_repository_identity_and_commit(self):
        directory=self.root/'code'
        subprocess.run(['git','init',str(directory)],check=True,capture_output=True)
        for args in [['config','user.name','Fixture'],['config','user.email','fixture@example.invalid'],['remote','add','origin','https://github.com/example/model'],['commit','--allow-empty','-m','fixture']]:
            subprocess.run(['git','-C',str(directory),*args],check=True,capture_output=True)
        result=fp.inspect_code(directory,'https://github.com/example/model')
        self.assertEqual(result['status'],'exists');self.assertEqual(len(result['commit']),40)
        self.assertEqual(fp.clone('https://github.com/other/repo',directory),'repository-mismatch')


class FigureTests(Workspace):
    def test_direct_extraction_rejects_changed_pdf(self):
        dest=self.paper();run_main(dest,'--offline')
        index=(dest/'figures/index.json').read_bytes()
        figure=(dest/'figures/fig-01.png').read_bytes()
        with (dest/'paper.pdf').open('ab') as f:f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'哈希'):ef.extract(dest,quiet=True)
        self.assertEqual((dest/'figures/index.json').read_bytes(),index)
        self.assertEqual((dest/'figures/fig-01.png').read_bytes(),figure)
        crop=subprocess.run([sys.executable,str(ROOT/'scripts/crop.py'),str(dest/'paper.pdf'),'--page','1'],capture_output=True)
        self.assertNotEqual(crop.returncode,0)
    def test_manual_correction_survives_rerun(self):
        dest=self.paper();ef.extract(dest,quiet=True)
        figure=dest/'figures/fig-01.png'
        subprocess.run([sys.executable,str(ROOT/'scripts/crop.py'),str(dest/'paper.pdf'),'--page','1','0.1','0.1','0.7','0.4','-o',str(figure)],check=True,capture_output=True)
        before=common.sha256_file(figure)
        ef.extract(dest,quiet=True)
        self.assertEqual(common.sha256_file(figure),before)
        self.assertTrue(common.read_json(dest/'figures/index.json')[0]['manual_override'])
    def test_external_edit_preserved_by_hash(self):
        dest=self.paper();ef.extract(dest,quiet=True)
        figure=dest/'figures/fig-01.png'
        with figure.open('ab') as f:f.write(b'edited')
        before=figure.read_bytes();ef.extract(dest,quiet=True)
        self.assertEqual(figure.read_bytes(),before)
    def test_user_directories_preserved(self):
        dest=self.paper()
        for name in ['figures','figures-auto']:
            d=dest/name;d.mkdir();(d/'user.txt').write_text('keep')
        self.assertEqual(ef.figures_dir(dest).name,'figures-auto-2')
        ef.extract(dest,quiet=True)
        self.assertEqual((dest/'figures-auto/user.txt').read_text(),'keep')
    def test_crop_rejects_invalid_page_step_and_source_overwrite(self):
        dest=self.paper()
        for args in [['--page','-1'],['--page','2'],['--page','1','--grid','--step','0'],['--page','1','-o',str(dest/'paper.pdf')]]:
            proc=subprocess.run([sys.executable,str(ROOT/'scripts/crop.py'),str(dest/'paper.pdf'),*args],capture_output=True)
            self.assertNotEqual(proc.returncode,0)
    def test_crop_creates_parent(self):
        dest=self.paper();out=dest/'nested/figure.png'
        subprocess.run([sys.executable,str(ROOT/'scripts/crop.py'),str(dest/'paper.pdf'),'--page','1','-o',str(out)],check=True,capture_output=True)
        self.assertTrue(out.exists())
    def test_no_figures_is_valid(self):
        dest=self.root/'empty';dest.mkdir();make_pdf(dest/'paper.pdf',caption=False)
        self.assertEqual(ef.extract(dest,quiet=True),[])
        self.assertTrue((dest/'figures/index.json').exists())
    def test_version_matches(self):
        self.assertEqual((ROOT/'VERSION').read_text().strip(),common.VERSION)


if __name__ == '__main__':
    unittest.main()
