import struct

class CustomWireProtocol:
    """
    Custom wire protocol for message encoding and decoding.

    Message format:
        - 4 bytes: Total message length
        - 2 bytes: Command type (unsigned short)
        - Remaining bytes: Payload

    Attributes:
        CMD_CREATE (int): Command identifier for creating an account.
        CMD_LOGIN (int): Command identifier for logging in.
        CMD_LIST (int): Command identifier for listing users.
        CMD_SEND (int): Command identifier for sending a message.
        CMD_GET_MESSAGES (int): Command identifier for retrieving messages.
        CMD_GET_UNDELIVERED (int): Command identifier for retrieving undelivered messages.
        CMD_DELETE_MESSAGES (int): Command identifier for deleting messages.
        CMD_DELETE_ACCOUNT (int): Command identifier for deleting an account.
        CMD_LOGOUT (int): Command identifier for logging out.
    """
    # Command type constants
    CMD_CREATE = 1
    CMD_LOGIN = 2
    CMD_LIST = 3
    CMD_SEND = 4
    CMD_GET_MESSAGES = 5
    CMD_GET_UNDELIVERED = 6
    CMD_DELETE_MESSAGES = 7
    CMD_DELETE_ACCOUNT = 8
    CMD_LOGOUT = 9

    @staticmethod
    def encode_message(cmd, payload_parts):
        """
        Encodes a message for transmission.

        Args:
            cmd (int): The command type identifier.
            payload_parts (list): A list of data elements to be encoded.

        Returns:
            bytes: The encoded message in binary format.
        """
        # Encode each payload part
        encoded_payload = []
        for part in payload_parts:
            if part is None:
                continue
            if isinstance(part, str):
                # Encode string with length prefix (2 bytes for length)
                encoded_str = part.encode('utf-8')
                encoded_payload.append(struct.pack('!H', len(encoded_str)))
                encoded_payload.append(encoded_str)
            elif isinstance(part, bytes):
                # If it's already bytes, add directly
                encoded_payload.append(part)
            elif isinstance(part, list):
                # Handle lists of IDs or other types
                if not part:
                    encoded_payload.append(struct.pack('!H', 0))
                else:
                    encoded_payload.append(struct.pack('!H', len(part)))
                    for item in part:
                        if isinstance(item, int):
                            # 4 bytes for integer IDs
                            encoded_payload.append(struct.pack('!I', item))
            elif isinstance(part, bool):
                # Boolean as 1 byte
                encoded_payload.append(struct.pack('!?', part))
            elif isinstance(part, int):
                # Handle different integer sizes
                if part > 65535:
                    # 4-byte integer
                    encoded_payload.append(struct.pack('!I', part))
                else:
                    # 2-byte integer for smaller numbers
                    encoded_payload.append(struct.pack('!H', part))
            elif isinstance(part, float):
                # 8-byte float for timestamps
                encoded_payload.append(struct.pack('!d', part))
        
        # Combine payload parts
        payload = b''.join(encoded_payload)
        
        # Pack total length (4 bytes), command (2 bytes), then payload
        header = struct.pack('!IH', len(payload) + 6, cmd)
        return header + payload

    @staticmethod
    def decode_message(data):
        """
        Decodes an incoming message.

        Args:
            data (bytes): The received binary data.

        Returns:
            tuple: A tuple containing:
                - total_length (int): The total length of the message.
                - cmd (int): The command identifier.
                - payload (bytes): The payload data.
        """
        total_length, cmd = struct.unpack('!IH', data[:6])
        payload = data[6:total_length]
        return total_length, cmd, payload

    @staticmethod
    def decode_string(data):
        """
        Decodes a length-prefixed string from binary data.

        Args:
            data (bytes): The binary data containing the encoded string.

        Returns:
            tuple: A tuple containing:
                - decoded_string (str): The decoded string.
                - remaining_data (bytes): The remaining data after extracting the string.
        """
        if len(data) < 2:
            return "", data
        length = struct.unpack('!H', data[:2])[0]
        if len(data) < 2 + length:
            return "", data
        return data[2:2+length].decode('utf-8'), data[2+length:]

    @staticmethod
    def decode_success_response(payload):
        """
        Decodes a standard success response.

        Args:
            payload (bytes): The binary data payload.

        Returns:
            tuple: A tuple containing:
                - success (bool): Whether the response indicates success.
                - message (str): The decoded response message.
                - remaining_payload (bytes): The remaining data in the payload.
        """
        if len(payload) < 1:
            return False, "Invalid response", b''
        
        success = struct.unpack('!?', payload[:1])[0]
        payload = payload[1:]
        
        # Decode message string
        message, payload = CustomWireProtocol.decode_string(payload)
        
        return success, message, payload