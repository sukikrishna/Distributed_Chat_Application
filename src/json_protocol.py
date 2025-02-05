import json

class JSONProtocol:
    OP_CREATE_ACCOUNT = "create_account"
    OP_LOGIN = "login"
    OP_SEND_MESSAGE = "send_message"
    OP_READ_MESSAGES = "read_messages"
    
    @staticmethod
    def encode(opcode, username, payload):
        request = {
            "opcode": opcode,
            "username": username,
            "payload": payload
        }
        return json.dumps(request).encode('utf-8')
    
    @staticmethod
    def decode(data):
        request = json.loads(data.decode('utf-8'))
        return request["opcode"], request["username"], request["payload"]
    
    @staticmethod
    def encode_response(success, data=""):
        response = {
            "success": success,
            "data": data
        }
        return json.dumps(response).encode('utf-8')
    
    @staticmethod
    def decode_response(data):
        response = json.loads(data.decode('utf-8'))
        return response["success"], response.get("data", "")
