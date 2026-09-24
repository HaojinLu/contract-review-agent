import json
import unittest

from contract_review_agent.json_utils import extract_json_payload, to_pretty_json


class JsonUtilsTests(unittest.TestCase):
    def test_fenced_json_with_surrounding_explanation(self):
        payload = extract_json_payload('说明文字\n```json\n{"missing_items": [{"dimension": "delivery"}]}\n```\n结束')
        self.assertEqual(payload["missing_items"][0]["dimension"], "delivery")

    def test_inline_json_with_surrounding_text(self):
        self.assertEqual(extract_json_payload('Result: {"ok": true}.'), {"ok": True})

    def test_array_payload(self):
        self.assertEqual(extract_json_payload('[{"risk_level": "low"}]'), [{"risk_level": "low"}])
        self.assertEqual(extract_json_payload('Result: [{"risk_level": "low"}]'), [{"risk_level": "low"}])

    def test_rejects_empty_and_non_json_output(self):
        for text in ("", "   ", "no structured result"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                extract_json_payload(text)

    def test_rejects_malformed_json(self):
        with self.assertRaises(json.JSONDecodeError):
            extract_json_payload('```json\n{"missing_items": }\n```')

    def test_pretty_json_preserves_chinese(self):
        result = to_pretty_json({"review_summary": "需要人工复核"})
        self.assertIn("需要人工复核", result)
        self.assertEqual(json.loads(result)["review_summary"], "需要人工复核")


if __name__ == "__main__":
    unittest.main()
