import unittest
from gtrmrs import __version__

class TestVersion(unittest.TestCase):
    def test_version_exists(self):
        self.assertIsInstance(__version__, str)
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")

if __name__ == "__main__":
    unittest.main()
