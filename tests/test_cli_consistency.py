"""CLI streams, output and scanner ownership using temporary fixtures."""

import argparse
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gtrmrs.cli import main
from gtrmrs.deps.engine import DepsEngine
from gtrmrs.deps.models import ProjectProfile
from gtrmrs.gitmig import cli as migration
from gtrmrs.gitmig.engine import GitMigEngine
from gtrmrs.rtree import cli as tree


class Terminal(io.StringIO):
    def isatty(self):
        return True


class Configurable(io.StringIO):
    def __init__(self):
        super().__init__()
        self.configuration = None

    def reconfigure(self, **options):
        self.configuration = options


class TestCliConsistency(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_umbrella_configures_both_streams_before_reporting_unicode_path(self):
        output, errors = Configurable(), Configurable()
        with patch('sys.argv', ['gtrmrs', 'locr', str(self.root / '不存在')]), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 1)
        for stream in (output, errors):
            self.assertEqual(stream.configuration, dict(encoding='utf-8', errors='replace'))
        self.assertIn('不存在', errors.getvalue())

    def test_tree_clears_terminal_width_after_success_and_scan_failure(self):
        parser = argparse.ArgumentParser()
        tree._configure_parser(parser)
        for failing in (False, True):
            output, errors = Terminal(), io.StringIO()
            with self.subTest(failing=failing), contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), patch('gtrmrs.rtree.cli.shutil.get_terminal_size', return_value=os.terminal_size((37, 20))):
                if failing:
                    with patch('gtrmrs.rtree.cli.RepoTreeVisualizer', side_effect=PermissionError('fixture failure')):
                        with self.assertRaises(SystemExit):
                            tree.run(parser.parse_args(['--repo', str(self.root)]))
                else:
                    tree.run(parser.parse_args(['--repo', str(self.root)]))
            self.assertIn('\r' + ' ' * 36 + '\r', output.getvalue())
            if failing:
                self.assertIn('fixture failure', errors.getvalue())

    def test_library_category_comes_from_its_producing_scanner(self):
        project = self.root / 'custom'
        project.mkdir()
        scanner = SimpleNamespace(
            discover_projects=lambda path: {'custom': str(project)},
            scan_project=lambda name, path: (ProjectProfile(name, path, 'custom'), {
                'libraries': {'lib': {'coord': 'example:lib', 'version': '1.0'}}, 'plugins': {},
            }),
            categorize=lambda identifier: 'Custom Libraries',
        )
        engine = DepsEngine()
        engine.register_scanner(scanner)
        result = engine.run_audit(str(self.root), no_upstream=True)
        self.assertEqual(result.components[0].category, 'Custom Libraries')

    def migration_output(self, terminal, no_color):
        if not shutil.which('git'):
            self.skipTest('Git required for migration fixtures')
        source = self.root / 'source'
        source.mkdir()
        subprocess.run(['git', '-c', 'init.templateDir=', '-C', str(source), 'init', '-q'], capture_output=True, check=True)
        (source / 'main.py').write_text('pass\n', encoding='utf-8')
        destination = self.root / 'destination'
        output, errors = (Terminal() if terminal else io.StringIO()), io.StringIO()
        parser = argparse.ArgumentParser()
        migration._configure_parser(parser)
        arguments = [str(source), str(destination)] + (['--no-color'] if no_color else [])
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            migration.run(parser.parse_args(arguments))
        self.assertTrue((destination / 'source/main.py').exists())
        self.assertNotIn('\x1b', output.getvalue())
        self.assertEqual(errors.getvalue(), '')

    def test_redirected_migration_has_no_ansi_or_terminal_hyperlinks(self):
        self.migration_output(terminal=False, no_color=False)

    def test_no_color_migration_disables_styling_links_and_spinner(self):
        self.migration_output(terminal=True, no_color=True)

    def test_no_color_migration_errors_remain_plain_on_terminal(self):
        engine = GitMigEngine(str(self.root), str(self.root.parent), use_color=False)
        errors = Terminal()
        with contextlib.redirect_stderr(errors):
            engine._print_error('fixture failure')
        self.assertEqual(errors.getvalue(), 'fixture failure\n')
        self.assertEqual(engine.errors, ['fixture failure'])
