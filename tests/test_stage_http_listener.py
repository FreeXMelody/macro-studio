import unittest

from stage_http_listener import TcpStreamBuffer, extract_stage_config


REQUEST = (
    b"GET /nshm/action-station/work/list/search?page=1&page_size=20&role_id=6259"
    b"&user_id=5211&keyword=%E9%97%AE%E7%88%B1&sort=hot HTTP/1.1\r\n"
    b"Host: hapi.hi.163.com\r\n"
    b"User-Agent: UnityPlayer/2020.3.26f1\r\n"
    b"skey: local-test-secret\r\n\r\n"
)


class StageHttpListenerTests(unittest.TestCase):
    def test_extracts_target_request(self):
        config = extract_stage_config(REQUEST)
        self.assertEqual(config["role_id"], "6259")
        self.assertEqual(config["user_id"], "5211")
        self.assertEqual(config["keyword"], "问爱")
        self.assertEqual(config["skey"], "local-test-secret")

    def test_reassembles_out_of_order_fragments(self):
        stream = TcpStreamBuffer()
        split = 92
        stream.add(1000 + split, REQUEST[split:])
        stream.add(1000, REQUEST[:split])
        config = extract_stage_config(stream.joined())
        self.assertEqual(config["keyword"], "问爱")

    def test_ignores_other_host(self):
        request = REQUEST.replace(b"hapi.hi.163.com", b"example.com")
        self.assertIsNone(extract_stage_config(request))


if __name__ == "__main__":
    unittest.main()
