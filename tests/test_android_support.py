import os
import tempfile
import unittest

from gtrmrs.gitmig.engine import GitMigEngine
from gtrmrs.locr.engine import LocrEngine
from gtrmrs.rtree.engine import RepoTreeVisualizer


def write_file(root: str, relative_path: str, content: str) -> None:
    path = os.path.join(root, *relative_path.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


class TestAndroidLocrSupport(unittest.TestCase):
    def test_locr_counts_android_languages_and_skips_generated_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            write_file(
                repo,
                "app/src/main/java/com/example/MainActivity.kt",
                "\n// comment\nclass MainActivity {\n    val title = \"Android\"\n}\n",
            )
            write_file(
                repo,
                "settings.gradle.kts",
                "// comment\nrootProject.name = \"Demo\"\n",
            )
            write_file(
                repo,
                "app/build.gradle",
                "// plugin setup\nplugins {\n    id 'com.android.application'\n}\n",
            )
            write_file(
                repo,
                "app/src/main/aidl/com/example/IRemoteService.aidl",
                "// comment\ninterface IRemoteService {\n}\n",
            )
            write_file(
                repo,
                "app/proguard-rules.pro",
                "# keep app classes\n-keep class com.example.** { *; }\n",
            )
            write_file(
                repo,
                "gradle.properties",
                "# gradle tuning\norg.gradle.jvmargs=-Xmx2048m\n",
            )
            write_file(
                repo,
                "app/src/main/java/com/example/Legacy.java",
                "// comment\nclass Legacy {}\n",
            )
            write_file(
                repo,
                "app/src/main/AndroidManifest.xml",
                "<manifest>\n</manifest>\n",
            )
            write_file(
                repo,
                "app/src/main/res/layout/activity_main.xml",
                "<LinearLayout>\n</LinearLayout>\n",
            )

            write_file(repo, ".gradle/cache/output.kt", "class Cached {}\n")
            write_file(repo, ".cxx/Debug/native.cpp", "int main() { return 0; }\n")
            write_file(
                repo,
                "externalNativeBuild/logs/build.c",
                "int native_build(void) { return 0; }\n",
            )
            write_file(repo, "captures/screen.kt", "class Capture {}\n")
            write_file(repo, "build/generated/Generated.kt", "class Generated {}\n")

            results, _ = LocrEngine(repo).scan()

            self.assertEqual(results["Kotlin"]["files"], 1)
            self.assertEqual(results["Kotlin Script"]["files"], 1)
            self.assertEqual(results["Gradle"]["files"], 1)
            self.assertEqual(results["AIDL"]["files"], 1)
            self.assertEqual(results["ProGuard"]["files"], 1)
            self.assertEqual(results["Properties"]["files"], 1)
            self.assertEqual(results["Java"]["files"], 1)
            self.assertEqual(results["XML"]["files"], 2)


class TestAndroidGitMigSupport(unittest.TestCase):
    def test_gitmig_keeps_android_sources_and_skips_android_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as dest_dir:
            write_file(source_dir, "app/src/main/java/com/example/MainActivity.kt", "class MainActivity {}\n")
            write_file(source_dir, "settings.gradle.kts", "rootProject.name = \"Demo\"\n")
            write_file(source_dir, "app/build.gradle", "plugins {}\n")
            write_file(source_dir, "gradle.properties", "org.gradle.jvmargs=-Xmx2g\n")
            write_file(source_dir, ".env.local", "API_URL=https://example.test\n")
            write_file(source_dir, ".gitignore", "build/\n")
            write_file(source_dir, "local.properties", "sdk.dir=C:\\Android\\Sdk\n")
            write_file(source_dir, ".gradle/state.bin", "cache\n")
            write_file(source_dir, "externalNativeBuild/log.txt", "native build log\n")
            write_file(source_dir, "app/build/outputs/apk/debug/app-debug.apk", "apk\n")

            engine = GitMigEngine(source_dir, dest_dir)
            files_to_copy, _ = engine._scan_repo("android-app", source_dir)
            copied_paths = {relative_path.replace("\\", "/") for relative_path, _ in files_to_copy}
            preserved_paths = {path.replace("\\", "/") for path in engine.preserved_files}

            self.assertIn("app/src/main/java/com/example/MainActivity.kt", copied_paths)
            self.assertIn("settings.gradle.kts", copied_paths)
            self.assertIn("app/build.gradle", copied_paths)
            self.assertIn("gradle.properties", copied_paths)
            self.assertIn(".env.local", copied_paths)
            self.assertIn(".gitignore", copied_paths)

            self.assertNotIn("local.properties", copied_paths)
            self.assertNotIn(".gradle/state.bin", copied_paths)
            self.assertNotIn("externalNativeBuild/log.txt", copied_paths)
            self.assertNotIn("app/build/outputs/apk/debug/app-debug.apk", copied_paths)

            self.assertIn("android-app/.env.local", preserved_paths)
            self.assertIn("android-app/.gitignore", preserved_paths)


class TestAndroidRtreeSupport(unittest.TestCase):
    def test_rtree_hides_android_dirs_by_default_and_shows_them_in_raw_mode(self) -> None:
        with tempfile.TemporaryDirectory() as repo:
            write_file(repo, "app/src/main/java/com/example/MainActivity.kt", "class MainActivity {}\n")
            write_file(repo, ".gradle/cache.txt", "cache\n")
            write_file(repo, ".kotlin/session.txt", "cache\n")
            write_file(repo, ".cxx/build.txt", "cache\n")
            write_file(repo, "captures/screenshot.txt", "capture\n")
            write_file(repo, "externalNativeBuild/output.txt", "native\n")
            write_file(repo, "build/generated/source.txt", "generated\n")

            default_tree = RepoTreeVisualizer(repo, raw_mode=False, use_color=False)
            raw_tree = RepoTreeVisualizer(repo, raw_mode=True, use_color=False)

            self.assertIn("app/", default_tree.visible_paths)
            self.assertNotIn(".gradle/", default_tree.visible_paths)
            self.assertNotIn(".kotlin/", default_tree.visible_paths)
            self.assertNotIn(".cxx/", default_tree.visible_paths)
            self.assertNotIn("captures/", default_tree.visible_paths)
            self.assertNotIn("externalNativeBuild/", default_tree.visible_paths)
            self.assertNotIn("build/", default_tree.visible_paths)

            self.assertIn(".gradle/", raw_tree.visible_paths)
            self.assertIn(".kotlin/", raw_tree.visible_paths)
            self.assertIn(".cxx/", raw_tree.visible_paths)
            self.assertIn("captures/", raw_tree.visible_paths)
            self.assertIn("externalNativeBuild/", raw_tree.visible_paths)
            self.assertIn("build/", raw_tree.visible_paths)
