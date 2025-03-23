import logging
import queue

import grpc
import spec_pb2
import spec_pb2_grpc

from models import init_db, get_session_factory

import threading
import time
import queue
from slave_server import *
from master_server import *


def claim_mastery(master_state):
    """Informs all the slaves that this server has become the new master
    wathcout for competing masters problem"""
    master_id, master_address = master_state['master_id'], master_state['master_address']
    for _, slave_address in master_state['slaves']:
        # print('trying to update slave', slave_address)
        with grpc.insecure_channel(slave_address) as channel:
            stub = spec_pb2_grpc.SlaveServiceStub(channel)
            # print(slave_address, stub, channel)
            update_master_request = spec_pb2.NewMasterRequest(
                new_master_address=master_address, new_master_id=master_id)
            # print(update_master_request)
            # response = stub.SIMPLE(spec_pb2.Empty(), timeout=5)
            # print('after simple')
            response = stub.UpdateMaster(update_master_request, timeout=5)
            # print('response', response)


def upgrade_slave(old_state):
    # Upgrade the slave to a master
    # Start the master server
    # Start the slave server
    master_state = old_state
    master_state['master_address'] = old_state['slave_address']
    master_state['master_id'] = old_state['slave_id']
    master_state['update_queue'] = queue.Queue()

    # print('killing the opersor :)')
    master_state['slave_master_server'].stop(None)
    master_state['slave_master_server'].wait_for_termination()
    master_state['slave_client_server'].stop(None)
    master_state['slave_client_server'].wait_for_termination()

    del master_state['slave_master_server']
    del master_state['slave_id']
    del master_state['slave_address']

    # start a new master service
    master_slave_server = serve_master_slave(master_state)

    # create updater thread
    update_thread = threading.Thread(
        target=update_slaves, args=(master_state,))
    update_thread.start()

    # start a new client service
    master_client_server = serve_master_client(master_state)

    claim_mastery(master_state)

    master_slave_server.wait_for_termination()
    master_client_server.wait_for_termination()

    # remove from other's slaves list


def check_new_master(min_slave, slave_state):

    with grpc.insecure_channel(min_slave[1]) as channel:
        num_tries = 2
        stub = spec_pb2_grpc.MasterServiceStub(channel)
        success = False
        for _ in range(num_tries):
            try:
                response = stub.CheckMaster(spec_pb2.Empty())
                if (response.error_code == 0):
                    print('New master is alive')
                    slave_state['master_address'] = min_slave[1]
                    slave_state['master_id'] = min_slave[0]
                    success = True
                else:
                    # remove the min slave from the list
                    slave_state['slaves'].remove(min_slave)
            except:
                pass
        if not success:
            print('New master is dead')
            try:
                slave_state['slaves'].remove(min_slave)
            except:
                print('Error removing the slave')
                pass

# represents a single client


def slave_heart_beat_checker(slave_state):

    while True:
        master_address = slave_state['master_address']
        print("Heartbeat check", master_address)

        # Check if the master is alive
        # If not start the election process
        with grpc.insecure_channel(master_address) as channel:
            num_tries = 2
            success = False
            for i in range(num_tries):
                try:
                    stub = spec_pb2_grpc.MasterServiceStub(channel)
                    heartbeat_request = spec_pb2.Empty()
                    response = stub.HeartBeat(heartbeat_request)
                    # print(response, "Master is alive")
                    success = True
                    break
                except Exception as e:
                    # print(e)
                    if i == num_tries - 1:
                        print("Master is not alive, starting election process.")
                        # Start the election process
            if not success:
                slaves = slave_state['slaves']
                min_slave = None if len(slaves) == 0 else min(
                    slaves, key=lambda x: int(x[0]))
                # elction policy
                # if you are smallest id become the master
                # if not wait for a new master and then try again
                if min_slave == None or int(server_id) < int(min_slave[0]):
                    # become the new master
                    return upgrade_slave(slave_state)

                else:
                    # check if the new slave becomes the master if they can't be
                    # delete them and assign yourself
                    print('Waiting for a new master!')
                    time.sleep(10)
                    # check if the new master is alive
                    # otherwise assume that master is dead and remove it from
                    # your list
                    check_new_master(min_slave, slave_state)

        time.sleep(5)


def master_routine(
    server_id, internal_address, client_address, master_address=None
):
    database_url = f'sqlite:///chat_{server_id}.db'
    database_engine = init_db(database_url)

    SessionFactory = get_session_factory(database_engine)

    master_state = {
        'master_id': server_id,
        'master_address': internal_address,
        'slaves': [],
        'db_engine': database_engine,
        'db_session': SessionFactory,
        'update_queue': queue.Queue(),
        'client_address': client_address
    }

    # slave communication
    master_server = serve_master_slave(master_state)

    # Start a separate thread to send updates to slaves
    update_thread = threading.Thread(
        target=update_slaves, args=(master_state,))
    update_thread.start()

    # start client server
    clinet_server = serve_master_client(master_state)

    # wait for both
    master_server.wait_for_termination()
    clinet_server.wait_for_termination()


def slave_routine(server_id, internal_address, client_address, master_address=None):
    database_url = f'sqlite:///chat_{server_id}.db'
    database_engine = init_db(database_url, drop_tables=True)

    SessionFactory = get_session_factory(database_engine)
    logging.basicConfig()

    slave_state = {
        "slaves": [],
        "master_address": master_address,
        "slave_id": server_id,
        "slave_address": internal_address,
        "database_engine": database_engine,
        "db_session": SessionFactory,
        'client_address': client_address,
        'db_engine': database_engine,
        'slave_client_server': None,
        'database_url': database_url,
    }

    # start internal server for slave
    slave_server = server_slave_master(
        slave_state
    )

    slave_state['slave_master_server'] = slave_server
    # send message to the masters registe method
    request_update(slave_state)

    # create a thread for the heart beat checker
    heart_beat_thread = threading.Thread(
        target=slave_heart_beat_checker, args=(slave_state, ))
    heart_beat_thread.start()

    clinet_server = serve_slave_client(slave_state)
    slave_state['slave_client_server'] = clinet_server
    slave_state['heartbeat_thread'] = heart_beat_thread
    clinet_server.wait_for_termination()
    slave_server.wait_for_termination()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description="Start a chat server as a master or a slave.")
    parser.add_argument("server_id", help="Unique server ID.")
    parser.add_argument(
        "type", choices=["master", "slave"], help="Server type: master or slave.")
    parser.add_argument(
        "client_address", help="Server address to communicate client in the format < host > : < port >"
    )
    parser.add_argument(
        "internal_address", help="Server address to communicate internally in the format < host > : < port >"
    )
    parser.add_argument(
        "--master_address", help="Master server address (required for slave servers).")

    args = parser.parse_args()

    server_id = args.server_id
    server_type = args.type
    client_address = args.client_address
    internal_address = args.internal_address
    master_address = args.master_address

    if server_type == "slave" and master_address is None:
        parser.error("Slave servers require the --master_address option.")

    if server_type == 'master':
        master_routine(server_id, internal_address, client_address)
    else:
        slave_routine(server_id, internal_address,
                      client_address, master_address)

    # incase slave is upgraded to master
    # keep the main thread alive
    # for the new master to run
    stop_event = threading.Event()
    stop_event.wait()
