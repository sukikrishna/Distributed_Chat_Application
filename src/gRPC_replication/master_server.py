from concurrent import futures
import logging
import uuid
import queue

import grpc
import spec_pb2
import spec_pb2_grpc
from utils import StatusCode, StatusMessages

from models import UserModel, MessageModel, DeletedMessageModel, init_db, get_session_factory
from sqlalchemy.orm import scoped_session
from sqlalchemy import or_, and_
from google.protobuf.timestamp_pb2 import Timestamp

import pickle
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect
import threading
import time
import queue
from slave_server import *


class ClientService(spec_pb2_grpc.ClientAccountServicer):

    def __init__(self, db_session, update_queue):
        super().__init__()
        self.db_session = db_session
        self.update_queue = update_queue

    def CreateAccount(self, request, context):

        session = scoped_session(self.db_session)
        context.set_code(grpc.StatusCode.OK)

        user_exists = session.query(UserModel).filter_by(
            username=request.username).scalar()
        if user_exists:
            status_code = StatusCode.USER_NAME_EXISTS
            status_message = StatusMessages.get_error_message(status_code)
        else:
            # create a new user
            new_user = UserModel(username=request.username,
                                 password=request.password)
            session.add(new_user)
            session.commit()
            status_code = StatusCode.SUCCESS
            status_message = "Account created successfully!!"

            # get added user
            added_user = session.query(UserModel).filter_by(
                username=request.username).first()

            update_info = pickle.dumps(('users', 'add', added_user))
            # create_update_info("add", added_user, 'users')

            self.update_queue.put(update_info)

        session.remove()
        return spec_pb2.ServerResponse(error_code=status_code, error_message=status_message)

    def Login(self, request, context):

        context.set_code(grpc.StatusCode.OK)
        session = scoped_session(self.db_session)
        user = session.query(UserModel).filter_by(
            username=request.username).first()

        session_id = None
        if user is None:
            status_code = StatusCode.USER_DOESNT_EXIST
            status_message = StatusMessages.get_error_message(status_code)
        else:
            if user.password != request.password:
                status_code = StatusCode.INCORRECT_PASSWORD
                status_message = StatusMessages.get_error_message(status_code)
            else:
                session_id = self.GenerateSessionID()
                user.logged_in = True
                user.session_id = session_id
                session.commit()

                status_code = StatusCode.SUCCESS
                status_message = "Login successful!!"
                session_id = session_id

        return spec_pb2.ServerResponse(error_code=status_code, error_message=status_message, session_id=session_id)

    def Send(self, request, context):

        context.set_code(grpc.StatusCode.OK)

        session_id = request.session_id
        session = scoped_session(self.db_session)
        user = session.query(UserModel).filter_by(
            session_id=session_id).first()

        if user is None:
            status_code = StatusCode.USER_NOT_LOGGED_IN
            status_message = StatusMessages.get_error_message(status_code)
        else:
            receiver = session.query(UserModel).filter_by(
                username=request.to).first()

            if receiver is None:
                status_code = StatusCode.RECEIVER_DOESNT_EXIST
                status_message = StatusMessages.get_error_message(status_code)
            else:
                msg = MessageModel(
                    sender_id=user.id,
                    receiver_id=receiver.id,
                    content=request.message
                )
                session.add(msg)
                session.commit()

                status_code = StatusCode.SUCCESS
                status_message = "Message sent successfully!!"
                # breakpoint()
                # get added message
                msg2 = session.query(MessageModel).filter_by(
                    id=msg.id).first()

                # print("before updating slaves")
                update_info = pickle.dumps(('messages', "add", msg2))
                # print(update_info)
                try:
                    self.update_queue.put(update_info)
                except Exception as e:
                    print(e)
        # Remove any remaining session
        session.remove()
        # print("responding with server response")
        return spec_pb2.ServerResponse(error_code=status_code, error_message=status_message)

    def ListUsers(self, request, context):
        context.set_code(grpc.StatusCode.OK)
        users = spec_pb2.Users()

        session = scoped_session(self.db_session)
        all_users = session.query(UserModel).all()

        for user in all_users:
            user_ = users.user.add()
            user_.username = user.username
            user_.status = "online" if user.logged_in else "offline"

        # Remove any remaining session
        session.remove()

        return users

    def GetMessages(self, request, context):
        context.set_code(grpc.StatusCode.OK)

        msgs = spec_pb2.Messages()

        session = scoped_session(self.db_session)
        user = session.query(UserModel).filter_by(
            session_id=request.session_id).first()

        if not user:
            msgs.error_code = StatusCode.USER_NOT_LOGGED_IN
            msgs.error_message = StatusMessages.get_error_message(
                msgs.error_code)
        else:

            messages = session.query(MessageModel).filter(
                and_(MessageModel.receiver_id == user.id, MessageModel.is_received == False)).all()

            if len(messages) == 0:
                msgs.error_code = StatusCode.NO_MESSAGES
                msgs.error_message = StatusMessages.get_error_message(
                    msgs.error_code)
            else:
                for message in messages:
                    # print(message.is_received)
                    msg = msgs.message.add()
                    msg.from_ = message.sender.username
                    msg.message = message.content
                    msg.message_id = message.id
                    message.is_received = True

                session.commit()
                msgs.error_code = StatusCode.SUCCESS
                msgs.error_message = "Messages received successfully!!"

        session.remove()

        return msgs

    def AcknowledgeReceivedMessages(self, request, context):
        session = scoped_session(self.db_session)
        user = session.query(UserModel).filter_by(
            session_id=request.session_id).first()

        if user is None:
            status_code = StatusCode.USER_NOT_LOGGED_IN
            status_message = StatusMessages.get_error_message(status_code)
        else:
            messages = session.query(MessageModel).filter(
                MessageModel.id.in_(request.message_ids),
                MessageModel.receiver_id == user.id
            ).all()

            for message in messages:
                message.is_received = True

                # stop deleting messages
                # Move the message to the deleted_messages table
                # deleted_message = DeletedMessageModel(
                #     sender_id=message.sender_id,
                #     receiver_id=message.receiver_id,
                #     content=message.content,
                #     is_received=message.is_received,
                #     original_message_id=message.id,
                # )
                # session.add(deleted_message)
                # session.delete(message)

            session.commit()
            status_code = StatusCode.SUCCESS
            status_message = "Messages acknowledged successfully!!"

        session.remove()

        return spec_pb2.ServerResponse(error_code=status_code, error_message=status_message)

    def Logout(self, request, context):
        session = scoped_session(self.db_session)
        user = session.query(UserModel).filter_by(
            session_id=request.session_id).first()

        if user is None:
            status = StatusCode.USER_NOT_LOGGED_IN
            status_message = StatusMessages.get_error_message(status)
        else:
            user.session_id = None
            user.logged_in = False
            session.commit()
            status = StatusCode.SUCCESS
            status_message = "Logout successful!!"

        session.remove()

        return spec_pb2.ServerResponse(error_code=status, error_message=status_message)

    def GetChat(self, request, context):
        context.set_code(grpc.StatusCode.OK)

        msgs = spec_pb2.Messages()

        session = scoped_session(self.db_session)
        user = session.query(UserModel).filter_by(
            session_id=request.session_id).first()

        if user is None:
            msgs.error_code = StatusCode.USER_NOT_LOGGED_IN
            msgs.error_message = StatusMessages.get_error_message(
                msgs.error_code)
        else:
            receiver = session.query(UserModel).filter_by(
                username=request.username).first()

            messages = session.query(MessageModel).filter(
                or_(
                    and_(MessageModel.sender_id == user.id,
                         MessageModel.receiver_id == receiver.id),
                    and_(MessageModel.sender_id == receiver.id,
                         MessageModel.receiver_id == user.id)
                )
            ).order_by(MessageModel.time_stamp).all()

            if len(messages) == 0:
                msgs.error_code = StatusCode.NO_MESSAGES
                msgs.error_message = StatusMessages.get_error_message(
                    msgs.error_code)
            else:
                for message in messages:
                    msg = msgs.message.add()
                    msg.from_ = message.sender.username
                    msg.message = message.content
                    msg.message_id = message.id
                    # print(message.time_stamp)
                    timestamp_proto = Timestamp()
                    # print(timestamp_proto)
                    timestamp_proto.FromDatetime(message.time_stamp)
                    msg.time_stamp.CopyFrom(timestamp_proto)
                    if (message.receiver_id == user.id):
                        message.is_received = True

                session.commit()
                msgs.error_code = StatusCode.SUCCESS
                msgs.error_message = "Messages received successfully!!"

        session.remove()

        return msgs

    def DeleteAccount(self, request, context):
        session = scoped_session(self.db_session)
        user = session.query(UserModel).filter_by(
            session_id=request.session_id).first()

        if user is None:
            status_code = StatusCode.USER_NOT_LOGGED_IN
            status_message = StatusMessages.get_error_message(status_code)
        else:
            # Move user's messages to deleted_messages table
            messages_to_delete = session.query(MessageModel).filter(
                MessageModel.receiver_id == user.id
            ).all()

            for message in messages_to_delete:
                deleted_message = DeletedMessageModel(
                    sender_id=message.sender_id,
                    receiver_id=message.receiver_id,
                    content=message.content,
                    is_received=message.is_received,
                    original_message_id=message.id,
                )
            session.add(deleted_message)
            session.delete(message)

            # Delete user
            session.delete(user)
            session.commit()

            status_code = StatusCode.SUCCESS
            status_message = "Account deleted successfully!!"

        session.remove()

        return spec_pb2.ServerResponse(error_code=status_code, error_message=status_message)

    @staticmethod
    def GenerateSessionID():
        return str(uuid.uuid4())


def fetch_all_data_from_orm(connection):
    data = {}
    Session = sessionmaker(bind=connection)
    session = Session()

    # Get the list of classes defined in your ORM
    # Replace with your actual ORM classes
    orm_classes = [UserModel, MessageModel, DeletedMessageModel]

    for orm_class in orm_classes:
        table_name = orm_class.__tablename__
        table_data = session.query(orm_class).all()
        data[table_name] = table_data

    session.close()
    return data


class MasterService(spec_pb2_grpc.MasterServiceServicer):
    def __init__(self, states, db_engine):
        super().__init__()
        self.states = states
        self.db_engine = db_engine

    def RegisterSlave(self, request, context):
        slave_id = request.slave_id
        slave_address = request.slave_address
        if (slave_id, slave_address) not in self.states['slaves']:
            self.states['slaves'].append((slave_id, slave_address))
        # print(self.states)

        # Fetch and pickle the data from ORM objects
        with self.db_engine.begin() as connection:
            # Implement this function to fetch data from ORM objects
            data = fetch_all_data_from_orm(connection)
            pickled_data = pickle.dumps(data)

        other_slaves = [
            f"{slave[0]}-{slave[1]}" for slave in self.states['slaves'] if slave[0] != slave_id]
        # print(other_slaves)
        # inform other slaves about this new slave
        for slave in other_slaves:
            saddress = slave.split("-")[1]
            # print(slave, saddress)
            with grpc.insecure_channel(saddress) as channel:
                stub = spec_pb2_grpc.SlaveServiceStub(channel)
                # print(channel, stub)
                stub.UpdateSlaves(spec_pb2.UpdateSlavesRequest(
                    update_data=pickle.dumps((slave_id, slave_address))
                ))

        response = spec_pb2.RegisterSlaveResponse(
            error_code=0,
            error_message="",
            pickled_db=pickled_data,
            other_slaves=other_slaves
        )
        # print("Slave {} registered {} resp {}".format(slave_id, request.slave_address, response))

        return response

    def HeartBeat(self, request, context):
        return spec_pb2.Ack(error_code=0, error_message="")

    def CheckMaster(self, request, context):
        return spec_pb2.Ack(error_code=0, error_message="")


table_class_mapping = {
    'users': UserModel,
    'messages': MessageModel,
    'deleted_messages': DeletedMessageModel
}


def serve_master_client(master_state):
    db_session, address, update_queue, client_address = master_state['db_session'], master_state[
        'master_address'], master_state['update_queue'], master_state['client_address']
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    spec_pb2_grpc.add_ClientAccountServicer_to_server(
        ClientService(db_session=db_session, update_queue=update_queue), server)
    server.add_insecure_port(client_address)
    server.start()
    print("Client server started, listening on " + client_address)
    return server

# internal channel for master to communicate with slave


def serve_master_slave(master_state):
    address, db_engine = master_state['master_address'], master_state['db_engine']

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=20))
    spec_pb2_grpc.add_MasterServiceServicer_to_server(
        MasterService(master_state, db_engine=db_engine), server)
    server.add_insecure_port(address)
    server.start()
    print("Master server started, listening on " + address)
    return server


def get_update_data(update_queue):
    try:
        data = update_queue.get(block=False)
        return data
    except queue.Empty:
        return None


def update_slaves(master_state):

    while True:
        slave_addresses = master_state['slaves']
        update_queue = master_state['update_queue']

        # Fetch the update data here
        update_data = get_update_data(update_queue)

        if update_data is not None:
            # Iterate through each slave and send updates
            for _, slave_address in slave_addresses:
                try:
                    # print(slave_address)
                    with grpc.insecure_channel(slave_address) as channel:
                        stub = spec_pb2_grpc.SlaveServiceStub(channel)
                        accept_updates_request = spec_pb2.AcceptUpdatesRequest(
                            update_data=update_data)
                        response = stub.AcceptUpdates(accept_updates_request)
                except Exception as e:
                    print("Error while sending updates to slave: " + str(e))
        time.sleep(2)
