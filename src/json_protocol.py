import json

class JSONProtocol:
    """JSON-based protocol for encoding and decoding messages."""
    
    OP_CREATE_ACCOUNT = "create_account"
    OP_LOGIN = "login"
    OP_SEND_MESSAGE = "send_message"
    OP_READ_MESSAGES = "read_messages"
    
    @staticmethod
    def encode(opcode, username, payload):
        """Encodes a message using JSON format.
        
        Args:
            opcode (str): Operation code.
            username (str): Username.
            payload (str): Additional message data.
        
        Returns:
            bytes: JSON-encoded message.
        """
        request = {
            "opcode": opcode,
            "username": username,
            "payload": payload
        }
        return json.dumps(request).encode('utf-8')
    
    @staticmethod
    def decode(data):
        """Decodes a JSON message into readable components.
        
        Args:
            data (bytes): JSON-encoded message.
        
        Returns:
            tuple: Decoded (opcode, username, payload).
        """
        request = json.loads(data.decode('utf-8'))
        return request["opcode"], request["username"], request["payload"]
    
    @staticmethod
    def encode_response(success, data=""):
        """Encodes a response message.
        
        Args:
            success (bool): Whether the request was successful.
            data (str, optional): Additional response data.
        
        Returns:
            bytes: JSON-encoded response message.
        """
        response = {
            "success": success,
            "data": data
        }
        return json.dumps(response).encode('utf-8')
    
    @staticmethod
    def decode_response(data):
        """Decodes a JSON response message.
        
        Args:
            data (bytes): JSON-encoded response message.
        
        Returns:
            tuple: Success status and response payload.
        """
        response = json.loads(data.decode('utf-8'))
        return response["success"], response.get("data", "")
