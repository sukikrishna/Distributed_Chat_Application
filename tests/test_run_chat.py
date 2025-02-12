import pytest
from unittest.mock import patch, Mock
import sys
from pathlib import Path
import argparse

# Add root directory to Python path
root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))

from run_chat import main

@pytest.fixture
def mock_subprocess():
    with patch('subprocess.run') as mock:
        yield mock

class TestRunChat:
    def test_custom_client(self, mock_subprocess):
        with patch('sys.argv', ['run_chat.py', '--custom', '--mode', 'client', '--ip', '127.0.0.1']):
            main()
            mock_subprocess.assert_called_once()
            args = mock_subprocess.call_args[0][0]
            assert 'custom_client.py' in args[1]
            assert args[2] == '127.0.0.1'

    def test_json_client_with_port(self, mock_subprocess):
        with patch('sys.argv', ['run_chat.py', '--json', '--mode', 'client', '--ip', '127.0.0.1', '--port', '8000']):
            main()
            mock_subprocess.assert_called_once()
            args = mock_subprocess.call_args[0][0]
            assert 'json_client.py' in args[1]
            assert args[2] == '127.0.0.1'
            assert args[3] == '8000'

    def test_custom_server(self, mock_subprocess):
        with patch('sys.argv', ['run_chat.py', '--custom', '--mode', 'server']):
            main()
            mock_subprocess.assert_called_once()
            args = mock_subprocess.call_args[0][0]
            assert 'custom_server.py' in args[1]

    def test_json_server_with_port(self, mock_subprocess):
        with patch('sys.argv', ['run_chat.py', '--json', '--mode', 'server', '--port', '8000']):
            main()
            mock_subprocess.assert_called_once()
            args = mock_subprocess.call_args[0][0]
            assert 'json_server.py' in args[1]
            assert args[2] == '8000'

    def test_default_to_json(self, mock_subprocess):
        with patch('sys.argv', ['run_chat.py', '--mode', 'server']):
            main()
            mock_subprocess.assert_called_once()
            args = mock_subprocess.call_args[0][0]
            assert 'json_server.py' in args[1]

    def test_client_requires_ip(self, mock_subprocess):
        with patch('sys.argv', ['run_chat.py', '--mode', 'client']), \
             pytest.raises(SystemExit):
            main()

    @pytest.mark.parametrize('mode', ['invalid', 'test'])
    def test_invalid_mode(self, mode, mock_subprocess):
        with patch('sys.argv', ['run_chat.py', '--mode', mode]), \
             pytest.raises(SystemExit):
            main()