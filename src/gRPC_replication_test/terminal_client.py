from __future__ import print_function

import logging
import threading
import cmd

import grpc
import spec_pb2
import spec_pb2_grpc
import time
from utils import HelpMessages


class ChatClientTerminal(cmd.Cmd):
    """
    A simple command-line-based chat client called "Chat_Client" that allows users to create accounts,
    log in, send messages to other users, and more. The client communicates with a remote server using gRPC.
    """

    prompt = "Chat> "

    def __init__(self, port):
        """
        Initialize the Chat_Client instance, setting up the gRPC channel, stub, and displaying help message.
        """
        super(ChatClientTerminal, self).__init__()

        self.user_session_id = ""
        self.channel = grpc.insecure_channel(f'localhost:{port}')
        self.stub = spec_pb2_grpc.ClientAccountStub(self.channel)

        self.do_help("")

    # The following methods parse the client input depending on the given command
    def do_list(self, arg):
        """
        List all users registered on the server.
        """
        response = self.stub.ListUsers(spec_pb2.Empty())
        for user in response.user:
            print("=>", user.username, "[", user.status, "]")

    def do_create(self, arg):
        """
        Create a new user account with the provided username and password.
        """
        args = arg.split(" ")
        if (len(args) < 2):
            print("Invalid Arguments to command")
            return

        username = args[0]
        password = args[1]

        response = self.stub.CreateAccount(
            spec_pb2.CreateAccountRequest(username=username, password=password))
        print(response.error_message)

    def do_login(self, arg):
        """
        Log in to an existing user account with the provided username and password.
        """
        args = arg.split(" ")
        if (len(args) < 2):
            print("Invalid Arguments to command")
            return
        username = args[0]
        password = args[1]

        response = self.stub.Login(
            spec_pb2.LoginRequest(username=username, password=password))
        if response.error_code == 0:
            self.user_session_id = response.session_id
            threading.Thread(target=self.receive_thread).start()

        print(response.error_message)

    def do_send(self, arg):
        """
        Send a message to another user.
        """
        args = arg.split(" ")
        if (len(args) < 2):
            print("Invalid Arguments to command")
            return

        to = args[0]
        message = ' '.join(args[1:])

        response = self.stub.Send(
            spec_pb2.SendRequest(session_id=self.user_session_id, message=message, to=to))
        print(response.error_message)

    def do_logout(self, arg):
        """
        Log out from the current user account.
        """
        response = self.stub.Logout(
            spec_pb2.DeleteAccount(session_id=self.user_session_id))
        if response.error_code == 0:
            self.user_session_id = ""
        print(response.error_message)
        return response

    def do_exit(self, arg):
        """
        Close the gRPC channel and exit the application.
        """
        # close the channel
        self.channel.close()
        quit()

    def do_delete(self, arg):
        """
        Delete the current user account.
        """
        response = self.stub.DeleteAccount(
            spec_pb2.DeleteAccountRequest(session_id=self.user_session_id))
        print(response.error_message)
        return response

    def do_help(self, arg):
        """
        Display help information for the specified command or general help if no command is specified.
        """
        if arg == "list":
            print(HelpMessages.HELP_LIST)
        elif arg == "create":
            print(HelpMessages.HELP_CREATE)
        elif arg == "login":
            print(HelpMessages.HELP_LOGIN)
        elif arg == "send":
            print(HelpMessages.HELP_SEND)
        elif arg == "logout":
            print(HelpMessages.HELP_LOGOUT)
        elif arg == "exit":
            print(HelpMessages.HELP_EXIT)
        elif arg == "delete":
            print(HelpMessages.HELP_DELETE)
        elif arg == "help":
            print(HelpMessages.HELP_HELP)
        else:
            print(HelpMessages.HELP_HELP)

    def emptyline(self):
        """
        Override the emptyline method to do nothing when an empty line is entered.
        """
        return None

    def receive_thread(self):
        """
        Thread responsible for receivsignuping messages from other users.
        """
        # Create a stream for receiving messages
        while True:
            msgs = self.stub.GetMessages(
                spec_pb2.ReceiveRequest(session_id=self.user_session_id))

            if msgs.error_code != 0:
                time.sleep(2)
                continue
            else:
                for message in msgs.message:
                    print(f"{message.from_}: {message.message}")

                # Send acknowledgment for the received messages
                message_ids = [msg.id for msg in msgs.message]
                ack_response = self.stub.AcknowledgeReceivedMessages(
                    spec_pb2.AcknowledgeRequest(session_id=self.user_session_id, message_ids=message_ids))

                if ack_response.error_code != 0:
                    print(
                        f"Error acknowledging messages: {ack_response.error_message}")
                    return

                if msgs.error_code != 0:
                    return


if __name__ == '__main__':
    logging.basicConfig()
    ChatClientTerminal(2625).cmdloop()
