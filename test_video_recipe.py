import unittest
import argparse
from pathlib import Path
from unittest.mock import patch
from video_recipe import build_recipe, validate_evidence
from video_recipe import prepare_input, main
from video_recipe import report_fetch_error
from video_recipe import resolve_share_url


def record(start, text, source='ocr'):
    return {'start': start, 'end': start + 1, 'text': text, 'source': source}


class RecipeTests(unittest.TestCase):
    def test_sieving_and_short_caption_retained_together(self):
        speech = record(37, '最后过一遍筛口感会更细腻', 'speech')
        speech['end'] = 40
        result = build_recipe([speech, record(38, '最后过一遍筛')])
        self.assertEqual(len(result['steps']), 1)
        self.assertIn('筛', result['steps'][0]['instruction'])

    def test_social_speech_not_a_cooking_step(self):
        result = build_recipe([record(1, '如果西班牙的夏天只能留下一道菜'),
                               record(65, '在西班牙煮久了以后慢慢也习惯了这种节奏'),
                               record(6, '熟透的番茄、黄瓜、一点青椒'),
                               record(12, '全部切成小块'), record(20, '番茄已经杀出很多水分了')])
        self.assertEqual(len(result['narration']), 2)
        self.assertFalse(any('西班牙' in s['instruction'] for s in result['steps']))
        self.assertTrue(any('番茄' in i['text'] for i in result['ingredients']))
        self.assertTrue(any('水分' in s['instruction'] for s in result['steps']))

    def test_mixed_opinion_keeps_instruction(self):
        result = build_recipe([record(1, '我觉得更好吃的做法是加入大蒜小火煮三分钟')])
        self.assertEqual(len(result['steps']), 1)
        self.assertFalse(result['narration'])

    def test_fragment_uses_same_time_speech_context(self):
        speech = record(5, '用白醋或者生抽微微打湿', 'speech')
        speech['end'] = 8
        result = build_recipe([speech, record(6, '或者生抽')])
        self.assertEqual(result['content_classification'][1]['category'], 'operation')

    def test_opening_materials_and_long_sentence_preserved(self):
        material = record(5.6, '熟透的番茄、黄瓜、一点青椒', 'speech')
        speech = record(9.6, '还有隔夜的酸面包全部切成小块', 'speech')
        speech['end'] = 13.4
        caption = record(12, '全部切成小块')
        caption['confidence'] = .999
        result = build_recipe([material, speech, caption, record(15, '还有一枚大蒜')])
        self.assertTrue(any('番茄' in i['text'] and '黄瓜' in i['text'] for i in result['ingredients']))
        self.assertIn('酸面包', result['steps'][0]['instruction'])
        self.assertTrue(any('大蒜' in i['text'] for i in result['ingredients']))

    def test_unclassified_context_is_retained(self):
        result = build_recipe([record(1, '某种尚未收录的食材'), record(2, '全部切成小块')])
        self.assertEqual(result['context'][0]['text'], '某种尚未收录的食材')

    def test_card_quantities_not_lost_or_made_steps(self):
        card = record(15, '红葱头1个切丝')
        card.update(kind='ingredient_card', confidence=.99)
        result = build_recipe([card, record(4, '红油皮蛋面')])
        self.assertEqual(result['ingredients'][0]['text'], '红葱头1个切丝')
        self.assertEqual(result['dish_name_candidates'][0]['text'], '红油皮蛋面')
        self.assertFalse(any(s['instruction'] == card['text'] for s in result['steps']))

    def test_high_confidence_ocr_preferred(self):
        speech = record(30, '油温升至五楼成热之后', 'speech')
        caption = record(30, '油温升至五六成热之后')
        caption['confidence'] = .99
        self.assertEqual(build_recipe([speech, caption])['steps'][0]['instruction'], caption['text'])
    def test_align_split_caption_with_speech(self):
        speech = record(19, '再放入青红花椒中小火炸一分钟以后捞出', 'speech')
        speech['end'] = 23
        result = build_recipe([speech, record(20, '再放入青红花椒'), record(21, '中小火炸一分钟以后捞出')])
        self.assertEqual(len(result['steps']), 1)
        self.assertEqual(len(result['steps'][0]['evidence']), 3)

    def test_important_operations_retained(self):
        result = build_recipe([record(1, '先取一个皮蛋和葱姜水搅打成泥'), record(5, '油温降低到100度左右的时候')])
        self.assertEqual(len(result['steps']), 2)

    def test_bad_words_flagged_not_silently_corrected(self):
        result = build_recipe([record(1, '油温升至五流成热')])
        self.assertTrue(result['steps'][0]['review_notes'])
        self.assertIn('五流', result['steps'][0]['instruction'])

    def test_short_link_resolved_before_extraction(self):
        from unittest.mock import MagicMock
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.url = 'https://www.xiaohongshu.com/explore/test'
        with patch('video_recipe.build_opener', return_value=opener):
            self.assertEqual(resolve_share_url('https://xhslink.cn/o/test'), 'https://www.xiaohongshu.com/explore/test')

    def test_dependency_error_names_missing_module(self):
        with patch('builtins.print') as output:
            report_fetch_error(ModuleNotFoundError('missing', name='yt_dlp'), '下载')
        self.assertIn('yt_dlp', output.call_args_list[0].args[0])

    def test_fetch_error_redacts_url(self):
        with patch('builtins.print') as output:
            report_fetch_error(RuntimeError('blocked https://example.com/?token=secret'), '下载')
        self.assertNotIn('secret', output.call_args.args[0])

    def args(self):
        return argparse.Namespace(share=None, video=None, evidence=None, mode='both', download_models=False, output=None)

    def test_link_prompt_download_success(self):
        args = self.args()
        with patch('builtins.input', side_effect=['分享 https://xhslink.cn/o/test 文字', 'y']), patch('video_recipe.download_video', return_value=Path('download.mp4')) as download:
            url = prepare_input(args, True)
        self.assertEqual(url, 'https://xhslink.cn/o/test')
        download.assert_called_once()
        self.assertEqual(args.mode, 'both')
        self.assertTrue(args.download_models)
        self.assertIsNotNone(args.output)

    def test_link_failure_local_fallback(self):
        args = self.args()
        with patch('builtins.input', side_effect=['https://xhslink.cn/o/test', 'n']), patch('video_recipe.download_video', side_effect=RuntimeError('blocked')), patch('browser_video.fetch_with_browser', side_effect=RuntimeError('blocked')), patch('video_recipe.prompt_local_video', return_value=Path('local.mp4')) as local:
            prepare_input(args, True)
        local.assert_called_once()
        self.assertEqual(args.video, Path('local.mp4'))
        self.assertFalse(args.download_models)

    def test_invalid_link_can_retry(self):
        args = self.args()
        with patch('builtins.input', side_effect=['invalid', '', 'n']), patch('video_recipe.prompt_local_video', return_value=Path('local.mp4')):
            prepare_input(args, True)
        self.assertEqual(args.mode, 'both')

    def test_no_arguments_quit_without_models(self):
        with patch('builtins.input', return_value='q') as prompt, patch('video_recipe.ocr_video') as ocr:
            main([])
        self.assertIn('链接', prompt.call_args.args[0])
        ocr.assert_not_called()

    def test_cli_failed_download_does_not_prompt(self):
        args = self.args()
        args.share = 'https://xhslink.cn/o/test'
        with patch('video_recipe.download_video', side_effect=RuntimeError()), patch('browser_video.fetch_with_browser', side_effect=RuntimeError()), patch('builtins.input') as prompt:
            with self.assertRaises(ValueError):
                prepare_input(args, False)
        prompt.assert_not_called()

    def test_browser_fallback_reuses_video(self):
        args = self.args()
        args.share = 'https://xhslink.cn/o/test'
        with patch('builtins.input', side_effect=['https://xhslink.cn/o/test', 'n']), patch('video_recipe.download_video', side_effect=RuntimeError()), patch('browser_video.fetch_with_browser', return_value=Path('browser.mp4')) as browser, patch('video_recipe.prompt_local_video') as local:
            prepare_input(args, True)
        self.assertEqual(args.video, Path('browser.mp4'))
        self.assertTrue(browser.call_args.kwargs['allow_login'])
        local.assert_not_called()

    def test_chronology_and_evidence(self):
        result = build_recipe([record(20, '小火慢炖两个小时', 'speech'), record(1, '加入黄油')])
        self.assertEqual([s['start'] for s in result['steps']], [1, 20])
        self.assertEqual(result['steps'][1]['evidence'][0]['source'], 'speech')
        self.assertIn('两个小时', result['steps'][1]['instruction'])

    def test_caption_repeat_and_later_repeat(self):
        result = build_recipe([record(1, '加入黄油'), record(2, '加入黄油'), record(20, '加入黄油')])
        self.assertEqual(len(result['steps']), 2)
        self.assertEqual(len(result['steps'][0]['evidence']), 2)

    def test_no_invention(self):
        result = build_recipe([record(0, '今天这道菜很好吃')])
        self.assertEqual(result['steps'], [])
        self.assertEqual(result['status'], 'no_steps_detected')

    def test_fixture_is_not_model_output(self):
        self.assertEqual(build_recipe([record(1, '切块', 'manual_fixture')])['status'], 'fixture_draft')

    def test_invalid_evidence(self):
        for bad in [[record(-1, '切块')], [record(float('nan'), '切块')], [{'text': '切块'}], [record(1, '切块', 'unknown')]]:
            with self.assertRaises(ValueError):
                validate_evidence(bad)


if __name__ == '__main__':
    unittest.main()

