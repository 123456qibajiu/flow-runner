import unittest
from unittest.mock import patch

from app import APP_VERSION, BILIBILI_ACCOUNT, PROJECT_URL, RPAApp


class AboutDialogTests(unittest.TestCase):
    @patch("app.messagebox.showinfo")
    def test_about_dialog_contains_release_information(self, showinfo):
        RPAApp._show_about(None)

        showinfo.assert_called_once()
        title, content = showinfo.call_args.args
        self.assertEqual(title, "关于")
        self.assertIn(f"当前版本：v{APP_VERSION}", content)
        self.assertIn(BILIBILI_ACCOUNT, content)
        self.assertIn(PROJECT_URL, content)


if __name__ == "__main__":
    unittest.main()
