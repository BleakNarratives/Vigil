
import unittest
from unittest.mock import patch, MagicMock
import requests
from vigil.equinex_bridge.client import EquiNexClient
from vigil.equinex_bridge.exceptions import AuthenticationError, EquiNexException

class TestEquiNexClient(unittest.TestCase):

    def setUp(self):
        self.key = "test_key"
        self.client = EquiNexClient(gemini_api_key=self.key)

    def test_init_fails_without_key(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(AuthenticationError):
                EquiNexClient()

    def test_init_succeeds_with_provided_key(self):
        self.assertEqual(self.client.GEMINI_API_KEY, self.key)

    @patch.object(requests.Session, 'post')
    def test_steer_lyria_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = self.client.steer_lyria("test prompt", 0.5)
        self.assertEqual(result, {"status": "success"})
        mock_post.assert_called_once()

    @patch.object(requests.Session, 'post')
    def test_steer_lyria_failure(self, mock_post):
        mock_post.side_effect = requests.exceptions.RequestException("Network down")

        with self.assertRaises(EquiNexException):
            self.client.steer_lyria("test prompt", 0.5)

if __name__ == '__main__':
    unittest.main()
