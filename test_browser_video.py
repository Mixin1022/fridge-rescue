import unittest
from unittest.mock import MagicMock
from browser_video import cookie_jar, inspect_page, launch_browser
from browser_video import wait_for_content
from unittest.mock import patch


class BrowserTests(unittest.TestCase):
    def test_login_returns_to_original_note(self):
        page = MagicMock()
        page.is_closed.return_value = False
        context = MagicMock()
        context.pages = [page]
        blocked = {'content': False, 'login_overlay': True}
        home = {'content': False, 'login_overlay': False}
        ready = {'content': True, 'login_overlay': False}
        with patch('browser_video.inspect_page', side_effect=[blocked, blocked, home, home, ready]):
            self.assertIs(wait_for_content(context, page, 'https://xhslink.cn/o/test', 30), page)
        page.goto.assert_called_once_with('https://xhslink.cn/o/test', wait_until='domcontentloaded', timeout=30000)

    def test_new_tab_detected(self):
        page, new = MagicMock(), MagicMock()
        page.is_closed.return_value = new.is_closed.return_value = False
        context = MagicMock()
        context.pages = [page, new]
        with patch('browser_video.inspect_page', return_value={'content': True, 'login_overlay': False}):
            self.assertIs(wait_for_content(context, page, 'https://xhslink.cn/o/test', 30), new)

    def test_launch_channel_fallback(self):
        chromium = MagicMock()
        chromium.launch_persistent_context.side_effect = [RuntimeError('spawn'), 'context']
        with patch('browser_video.Path.mkdir'):
            self.assertEqual(launch_browser(chromium, 'dedicated', False), 'context')
        calls = chromium.launch_persistent_context.call_args_list
        self.assertEqual([c.kwargs['channel'] for c in calls], ['msedge', 'chrome'])
        self.assertTrue(calls[1].kwargs['headless'])

    def test_all_launch_failures_explained(self):
        chromium = MagicMock()
        chromium.launch_persistent_context.side_effect = RuntimeError('spawn')
        with patch('browser_video.Path.mkdir'), self.assertRaisesRegex(RuntimeError, '均无法启动'):
            launch_browser(chromium, 'dedicated', True)
    def test_only_xhs_cookies(self):
        records = [{'domain': d, 'name': 'session', 'value': 'test', 'expires': -1} for d in ['.xiaohongshu.com', 'evilxiaohongshu.com', '.example.com']]
        cookies = list(cookie_jar(records))
        self.assertEqual(len(cookies), 1)
        self.assertIsNone(cookies[0].expires)
        self.assertTrue(cookies[0].discard)

    def test_content_does_not_override_login_overlay(self):
        page = MagicMock()
        page.url = 'https://www.xiaohongshu.com/explore/123'
        page.locator.return_value.evaluate_all.return_value = True
        page.locator.return_value.count.return_value = 1
        page.get_by_text.return_value.count.return_value = 1
        page.get_by_text.return_value.nth.return_value.is_visible.return_value = True
        self.assertEqual(inspect_page(page), {'content': True, 'login_overlay': True})

    def test_public_content_without_overlay(self):
        page = MagicMock()
        page.url = 'https://www.xiaohongshu.com/discovery/item/123'
        page.locator.return_value.evaluate_all.return_value = True
        page.locator.return_value.count.return_value = 1
        page.get_by_text.return_value.count.return_value = 0
        self.assertEqual(inspect_page(page), {'content': True, 'login_overlay': False})

    def test_feed_video_is_not_note(self):
        page = MagicMock()
        page.url = 'https://www.xiaohongshu.com/explore'
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.evaluate_all.return_value = True
        page.get_by_text.return_value.count.return_value = 0
        self.assertFalse(inspect_page(page)['content'])

    def test_unloaded_video_is_not_ready(self):
        page = MagicMock()
        page.url = 'https://www.xiaohongshu.com/explore/123'
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.evaluate_all.return_value = False
        page.get_by_text.return_value.count.return_value = 0
        self.assertFalse(inspect_page(page)['content'])


if __name__ == '__main__':
    unittest.main()
