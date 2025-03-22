from concurrent import futures
import grpc
import spec_pb2
import spec_pb2_grpc
from utils import StatusCode, StatusMessages

from models import UserModel, MessageModel, DeletedMessageModel, init_db, get_session_factory
from sqlalchemy.orm import scoped_session

import pickle
import queue

table_class_mapping = {
    'users': UserModel,
    'messages': MessageModel,
    'deleted_messages': DeletedMessageModel
}


class SlaveService(spec_pb2_grpc.SlaveServiceServicer):
    def __init__(self, db_session, master_address, state):
        self.db_session = db_session
        self.master_address = master_address
        self.state = state
        # print("Slave service initialized")

    def AcceptUpdates(self, request, context):
        update_data = request.update_data
        self.process_update_data(update_data)

        response = spec_pb2.ServerResponse(
            error_code=0,
            error_message=""
        )
        return response

    def process_update_data(self, update_data):
        # Add your implementation for processing the update_data
        session = scoped_session(self.db_session)

        data = pickle.loads(update_data)
        # update the slaves list
        table, action, obj = data
        # print(action, obj)
        from sqlalchemy import inspect

        def object_as_dict(obj_):
            return {c.key: getattr(obj_, c.key)
                    for c in inspect(obj_).mapper.column_attrs}
        # Convert the original object to a dictionary
        obj_dict = object_as_dict(obj)

        # Recreate the object from the data
        new_obj = table_class_mapping[table]()
        for key, value in obj_dict.items():
            # print(key, value)
            setattr(new_obj, key, value)

        if action == 'add':
            session.add(new_obj)
        elif action == 'delete':
            session.delete(new_obj)
        elif action == 'update':
            session.merge(new_obj)
        session.commit()

        # print database to check if it is updated
        # query all users
        Users = session.query(UserModel).all()
        # print('after update', Users)

    def UpdateMaster(self, request, context):
        # print("UPDATING master", flush=True)
        master_address, master_id = request.new_master_address, request.new_master_id
        # print('new master', master_address, master_id, flush=True)
        assign_new_master(self.state, master_address, master_id)
        return spec_pb2.Ack(error_code=0, error_message="")

    def UpdateSlaves(self, request, context):
        # print("Updating slaves for slave")
        new_slave = pickle.loads(request.update_data)
        # remove the current slave from the list
        self.state['slaves'].append(new_slave)
        # print(new_slave, self.state['slaves'])
        return spec_pb2.Ack(error_code=0, error_message="")


def request_update(slave_state):

    master_address, server_id, internal_address, db_session = slave_state[
        'master_address'], slave_state['slave_id'], slave_state['slave_address'], slave_state['db_session']

    with grpc.insecure_channel(master_address) as channel:
        stub = spec_pb2_grpc.MasterServiceStub(channel)
        register_slave_request = spec_pb2.RegisterSlaveRequest(
            slave_id=server_id, slave_address=internal_address)
        response = stub.RegisterSlave(register_slave_request)
        master_db = pickle.loads(response.pickled_db)

        # update database with the master data
        session = scoped_session(db_session)
        try:
            for table_name, records in master_db.items():
                for record in records:
                    # print("record", record, type(record), record.username)

                    from sqlalchemy import inspect

                    def object_as_dict(obj):
                        return {c.key: getattr(obj, c.key)
                                for c in inspect(obj).mapper.column_attrs}
                    new_record = table_class_mapping[table_name](
                        **object_as_dict(record)
                    )
                    session.add(new_record)

            # Commit the transaction
            session.commit()
        except Exception as e:
            print("Error occurred:", e)
            session.rollback()
        finally:
            session.remove()  # Replace session.close() with session.remove()
        slave_state['slaves'] = list(
            set([tuple(slave.split('-')) for slave in response.other_slaves]))


def assign_new_master(state, master_address, master_id):
    print("Accepting new master")
    state['master_address'] = master_address
    # this is only required for windows that has file lockers
    # print('db_eninge in ', 'db_engine' in state)
    if 'db_engine' in state:
        try:
            state['db_engine'].dispose()
        except Exception as e:
            print('deleting engine', e)
    database_engine = init_db(state['database_url'], drop_tables=True)
    SessionFactory = get_session_factory(database_engine)
    state['database_engine'] = database_engine
    state['db_session'] = SessionFactory

    slave_server = server_slave_master(state)

    state['slave_master_server'] = slave_server
    # send message to the masters registe method
    request_update(state)

    # remove master from the list of slaves
    try:
        state['slaves'].remove((master_address, master_id))
    except:
        pass

    print('Assigning new master complete')


class ClientServiceSlave(spec_pb2_grpc.ClientAccountServicer):
    pass


def serve_slave_client(slave_state):
    db_session, address, master_address, client_address = slave_state['db_session'], slave_state[
        'slave_address'], slave_state['master_address'], slave_state['client_address']

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    spec_pb2_grpc.add_ClientAccountServicer_to_server(
        ClientServiceSlave(), server)
    server.add_insecure_port(client_address)
    server.start()
    print("Client server started, listening on ", client_address)
    return server


def server_slave_master(slave_state):
    db_session, master_address, address, slaves = slave_state['db_session'], slave_state[
        'master_address'], slave_state['slave_address'], slave_state['slaves']

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    spec_pb2_grpc.add_SlaveServiceServicer_to_server(
        SlaveService(db_session=db_session, master_address=master_address, state=slave_state), server)

    server.add_insecure_port(address)
    server.start()
    print("Slave server started, listening on " + address)
    return server
