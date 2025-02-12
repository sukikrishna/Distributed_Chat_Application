import pytest
import json
import os
import sys
from unittest.mock import mock_open, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.config import Config

@pytest.fixture
def config():
    with patch('os.path.exists') as mock_exists:
        mock_exists.return_value = False
        return Config()

@pytest.fixture
def sample_config_data():
    return {
        "host": "192.168.1.100",
        "port": 12345,
        "message_fetch_limit": 10
    }

def test_init_default_values(config):
    assert config.config['port'] == 50000
    assert config.config['message_fetch_limit'] == 5
    assert Config.HOST is not None

@pytest.mark.parametrize("ip_address", [
    "192.168.1.100",
    "10.0.0.1",
    "127.0.0.1"
])
def test_get_local_ip(monkeypatch, ip_address):
    def mock_socket(*args, **kwargs):
        mock_sock = type('MockSocket', (), {
            'getsockname': lambda: (ip_address, 0),
            'close': lambda: None
        })
        return mock_sock()
    
    with patch('socket.socket', mock_socket):
        assert Config.get_local_ip() == ip_address

def test_get_local_ip_failure(monkeypatch):
    def mock_socket(*args, **kwargs):
        raise Exception("Network error")
    
    with patch('socket.socket', mock_socket):
        assert Config.get_local_ip() == "127.0.0.1"

def test_load_config_existing_file(sample_config_data):
    mock_file = mock_open(read_data=json.dumps(sample_config_data))
    
    with patch('os.path.exists') as mock_exists, \
         patch('builtins.open', mock_file):
        mock_exists.return_value = True
        config = Config()
        
        assert config.config['host'] == sample_config_data['host']
        assert config.config['port'] == sample_config_data['port']
        assert config.config['message_fetch_limit'] == sample_config_data['message_fetch_limit']

def test_load_config_file_error():
    with patch('os.path.exists') as mock_exists, \
         patch('builtins.open') as mock_file:
        mock_exists.return_value = True
        mock_file.side_effect = IOError("Permission denied")
        
        with pytest.raises(IOError) as exc_info:
            Config()
        assert "Error reading config file" in str(exc_info.value)

def test_save_config(config, sample_config_data):
    mock_file = mock_open()
    
    with patch('builtins.open', mock_file):
        config.config = sample_config_data.copy()
        config.save_config()
        
        mock_file.assert_called_once_with("chat_config.json", 'w')
        handle = mock_file()
        handle.write.assert_called_once()
        written_data = json.loads(handle.write.call_args[0][0])
        assert written_data == sample_config_data

def test_save_config_error(config):
    with patch('builtins.open') as mock_file:
        mock_file.side_effect = IOError("Permission denied")
        
        with pytest.raises(IOError) as exc_info:
            config.save_config()
        assert "Error writing config file" in str(exc_info.value)

def test_get_config_value(config, sample_config_data):
    config.config = sample_config_data.copy()
    
    assert config.get('port') == sample_config_data['port']
    assert config.get('message_fetch_limit') == sample_config_data['message_fetch_limit']
    assert config.get('nonexistent_key') == config.default_config.get('nonexistent_key')

def test_update_config(config):
    new_port = 54321
    
    with patch('builtins.open', mock_open()):
        config.update('port', new_port)
        assert config.config['port'] == new_port

def test_config_file_creation(tmp_path, monkeypatch):
    config_file = tmp_path / "chat_config.json"
    monkeypatch.setattr(Config, 'config_file', str(config_file))
    
    config = Config()
    assert os.path.exists(config_file)
    
    with open(config_file) as f:
        saved_config = json.load(f)
        assert 'host' in saved_config
        assert 'port' in saved_config
        assert 'message_fetch_limit' in saved_config