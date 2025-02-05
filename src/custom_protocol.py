import struct

class CustomProtocol:
    OP_CREATE_ACCOUNT = 1
    OP_LOGIN = 2
    OP_SEND_MESSAGE = 3
    OP_READ_MESSAGES = 4
    
    @staticmethod
    def encode(opcode, username, payload):
        username_bytes = username.encode('utf-8')
        payload_bytes = payload.encode('utf-8')
        header = struct.pack('!B B I', opcode, len(username_bytes), len(payload_bytes))
        return header + username_bytes + payload_bytes
    
    @staticmethod
    def decode(data):
        opcode, username_length, payload_length = struct.unpack('!B B I', data[:6])
        username = data[6:6+username_length].decode('utf-8')
        payload = data[6+username_length:6+username_length+payload_length].decode('utf-8')
        return opcode, username, payload
    
    @staticmethod
    def encode_response(success, data=""):
        response = "1" if success else "0"
        response += f"|{data}" if data else ""
        return response.encode('utf-8')
    
    @staticmethod
    def decode_response(data):
        response = data.decode('utf-8')
        success = response[0] == "1"
        payload = response[2:] if "|" in response else ""
        return success, payload
