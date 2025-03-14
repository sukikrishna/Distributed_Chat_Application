import socket

def get_local_ip():
    """Retrieves the local machine's IP address.

    Returns:
        str: The detected local IP address, or '127.0.0.1' if retrieval fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # Connect to Google's DNS to determine external-facing IP
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
    

if __name__ == "__main__":
    print(get_local_ip())
    #or can run ipconfig