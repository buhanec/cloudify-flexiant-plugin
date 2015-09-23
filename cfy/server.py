# coding=UTF-8

"""Server stuff."""

from __future__ import print_function
from cfy import (create_server,
                 create_ssh_key,
                 attach_ssh_key,
                 wait_for_state,
                 wait_for_status,
                 create_nic,
                 attach_nic,
                 get_resource,
                 get_server_status,
                 start_server,
                 stop_server,
                 delete_resource)
import socket
import errno
from cloudify import ctx
from cloudify.decorators import operation
from cfy.helpers import (with_fco_api, with_exceptions_handled)
from resttypes import enums
from paramiko import SSHClient
from scp import SCPClient
import os


RT = enums.ResourceType

PROP_RESOURCE_ID = 'resource_id'
PROP_USE_EXISTING = 'use_existing'
PROP_IMAGE = 'image'
PROP_VDC = 'vdc'
PROP_NET = 'network'
PROP_SERVER_PO = 'server_type'
PROP_CPU_COUNT = 'cpu_count'
PROP_RAM_AMOUNT = 'ram_amount'
PROP_MANAGER_KEY = 'manager_key'
PROP_PRIVATE_KEYS = 'private_keys'
PROP_PUBLIC_KEYS = 'public_keys'

RPROP_UUID = 'uuid'
RPROP_DISKS = 'disks'
RPROP_NIC = 'nic'
RPROP_NICS = 'nics'
RPROP_IP = 'ip'
RPROP_USER = 'username'
RPROP_PASS = 'password'


def ssh_probe(server_ip, server_port=22, time=10, step=90):
    while step:
        ctx.logger.info('SSH probing [{}]'.format(step))
        try:
            s = socket.create_connection((server_ip, server_port), time)
            s.close()
            break
        except socket.error, msg:
            if str(msg[0]) == str(errno.ECONNREFUSED):
                break
            step -= 1
    return bool(step)


# TODO: completely rehaul
@operation
@with_fco_api
@with_exceptions_handled
def create(fco_api, *args, **kwargs):
    ctx.logger.info('starting server creation')

    # Ease of access
    _rp = ctx.instance.runtime_properties
    _np = ctx.node.properties

    # Check if existing server is to be used
    if _np[PROP_USE_EXISTING]:
        server = get_resource(fco_api, _np[PROP_RESOURCE_ID, RT.SERVER])
        if not server.nics:
            raise Exception('No NICs attached to server')
        _rp[RPROP_UUID] = server.resourceUUID
        _rp[RPROP_DISKS] = [d.resourceUUID for d in server.disks]
        _rp[RPROP_NIC] = server.nics[0].resourceUUID
        _rp[RPROP_NICS] = [n.resourceUUID for n in server.nics]
        _rp[RPROP_IP] = server.nics[0].ipAddresses[0].ipAddress
        _rp[RPROP_USER] = server.initialUser
        _rp[RPROP_PASS] = server.initialPassword
        return  _rp[RPROP_UUID], _rp[RPROP_IP], _rp[RPROP_USER], \
                _rp[RPROP_PASS]


    # Get configuration
    image = get_resource(fco_api, _np[PROP_IMAGE], RT.IMAGE)
    if _np[PROP_IMAGE]:
        vdc = get_resource(fco_api, _np[PROP_IMAGE], RT.IMAGE)
    else:
        vdc = None
    network = get_resource(fco_api, _np[PROP_NET], RT.NETWORK)
    server_po = get_resource(fco_api, _np[PROP_SERVER_PO], RT.PRODUCTOFFER)
    manager_key = get_resource(fco_api, _np[PROP_MANAGER_KEY], RT.SSHKEY)
    cpu_count = _np[PROP_CPU_COUNT]
    ram_amount = _np[PROP_RAM_AMOUNT]
    public_keys = _np[PROP_PUBLIC_KEYS] or []
    private_keys = _np[PROP_PRIVATE_KEYS] or []

    # Verify existence of private keys
    missing_keys = set()
    for key in private_keys:
        if not os.path.isfile(os.path.expanduser(key)):
            missing_keys.add(key)
    if missing_keys:
        raise Exception('Missing private keys: {}'.format(missing_keys))

    # Generate missing configuration
    image_uuid = image.resourceUUID
    if vdc is not None:
        cluster_uuid = vdc.clusterUUID
        vdc_uuid = vdc.resourceUUID
    else:
        cluster_uuid = image.clusterUUID
        vdc_uuid = image.vdcUUID
    network_uuid = network.resourceUUID
    network_type = network.networkType
    server_po_uuid = server_po.resourceUUID
    manager_key_uuid = manager_key.resourceUUID
    # TODO: better way of determining suitable disk
    boot_disk_po_uuid = get_resource(fco_api,
                                     '{} GB Storage Disk'.format(image.size),
                                     RT.PRODUCTOFFER).resourceUUID

    ctx.log.info('Configuration: \n'
                 'image_uuid: %s\n'
                 'cluster_uuid: %s\n'
                 'vdc_uuid: %s\n'
                 'network_uuid: %s\n'
                 'server_po_uuid: %s\n'
                 'manager_key_uuid: %s\n'
                 'boot_disk_po_uuid: %s\n',
                 image_uuid, cluster_uuid, vdc_uuid, network_uuid,
                 server_po_uuid, manager_key_uuid, boot_disk_po_uuid)

    # Create server
    server_name = '{}{}_{}'.format(ctx.bootstrap_context.resources_prefix,
                                   ctx.deployment.id, ctx.instance.id)
    try:
        server_uuid = _rp[RPROP_UUID]
    except KeyError:
        # key_obj = get_resource(fco_api, key_uuid, RT.SSHKEY)
        # keys = SSHKey.REQUIRED_ATTRIBS.copy()
        # keys.add('resourceUUID')
        # submit_key = {}
        # for k in keys:
        #     try:
        #         submit_key[k] = getattr(manager_key, k)
        #     except AttributeError:
        #         submit_key[k] = None
        server_uuid = create_server(fco_api, server_po_uuid, image_uuid,
                                    cluster_uuid, vdc_uuid, cpu_count,
                                    ram_amount, boot_disk_po_uuid,
                                    [manager_key], server_name)
        _rp[RPROP_UUID] = server_uuid

    ctx.logger.info('server_uuid: %s', server_uuid)

    server = get_resource(fco_api, server_uuid, RT.SERVER)
    server_nics = [nic.resourceUUID for nic in server.nics]
    server_keys = [key.resourceUUID for key in server.sshkeys]

    # Wait for server to be active
    if not wait_for_state(fco_api, server_uuid, enums.ResourceState.ACTIVE,
                          RT.SERVER):
        raise Exception('Server failed to prepare in time!')

    ctx.logger.info('Server ACTIVE')

    # Add keys
    new_keys = set()
    for key in public_keys:
        if key not in server_keys:
            key_uuid = create_ssh_key(fco_api, key, server_name + ' Key')
            attach_ssh_key(fco_api, server_uuid, key_uuid)
            new_keys.add(key_uuid)

    ctx.logger.info('Keys attached: %s', new_keys)

    # Create NIC
    try:
        nic_uuid = _rp[RPROP_NIC]
    except KeyError:
        nic_uuid = create_nic(fco_api, cluster_uuid, network_type,
                              network_uuid, vdc_uuid, server_name + ' NIC')
        if not wait_for_state(fco_api, nic_uuid, enums.ResourceState.ACTIVE,
                              RT.NIC):
            raise Exception('NIC failed to create in time!')
        _rp[RPROP_NIC] = nic_uuid

    ctx.logger.info('nic_uuid: %s', nic_uuid)

    # Stop server if started
    if get_server_status(fco_api, server_uuid) != enums.ServerStatus.STOPPED:
        if not stop_server(fco_api, server_uuid):
            raise Exception('Stopping server failed to complete in time!')

    ctx.logger.info('Server STOPPED')

    # Attach NIC
    if nic_uuid not in server_nics:
        attach_nic_job = attach_nic(fco_api, server_uuid, nic_uuid, 1)
        if not wait_for_status(fco_api, attach_nic_job.resourceUUID,
                               enums.JobStatus.SUCCESSFUL, RT.JOB):
            raise Exception('Attaching NIC failed to complete in time!')
        ctx.logger.info('NICs attached')
    else:
        ctx.logger.info('NICs already attached')

    # Start server if not started
    if get_server_status(fco_api, server_uuid) == enums.ServerStatus.STOPPED:
        if not start_server(fco_api, server_uuid):
            raise Exception('Running server failed to complete in time!')

    ctx.logger.info('Server RUNNING')

    nic = get_resource(fco_api, nic_uuid, RT.NIC)
    server_ip = nic.ipAddresses[0].ipAddress
    server_port = 22

    if not ssh_probe(server_ip, server_port, step=-1):
        raise Exception('Starting server failed to complete in time!')

    ctx.logger.info('Server READY')

    username = server.initialUser
    password = server.initialPassword

    # Provision private keys
    for key in private_keys:
        key = os.path.expanduser(key)
        ssh = SSHClient()
        ssh.connect(server_ip, server_port, username, password)
        ssh.exec_command('mkdir ~/.ssh')
        ssh.exec_command('chmod 0700 ~/.ssh')
        with SCPClient(ssh.get_transport()) as scp:
            remote_key =  os.path.join('~', '.ssh', os.path.basename(key))
            scp.put(key, remote_key)
            ssh.exec_command('chmod 0600 ' + remote_key)

    _rp[RPROP_UUID] = server_uuid
    _rp[RPROP_IP] = server_ip
    _rp[RPROP_USER] = username
    _rp[RPROP_PASS] = password

    server = get_resource(fco_api, server_uuid, RT.SERVER)
    _rp[RPROP_DISKS] = [d.resourceUUID for d in server.disks]
    _rp[RPROP_NICS] = [n.resourceUUID for n in server.nics]

    ctx.logger.info('Server IP: ' + server_ip)
    ctx.logger.info('Server User: ' + username)
    ctx.logger.info('Server Password: ' + password)

    return server_uuid, server_ip, username, password


@operation
@with_fco_api
@with_exceptions_handled
def delete(fco_api, *args, **kwargs):
    server_uuid = ctx.instance.runtime_properties.get(RPROP_UUID)
    job_uuid = delete_resource(fco_api, server_uuid, RT.SERVER, True) \
        .resourceUUID
    if not wait_for_status(fco_api, job_uuid, enums.JobStatus.SUCCESSFUL,
                           RT.JOB):
        raise Exception('Failed to delete server')


@operation
@with_fco_api
@with_exceptions_handled
def start(fco_api, *args, **kwargs):
    server_uuid = ctx.instance.runtime_properties.get(RPROP_UUID)
    if get_server_status(fco_api, server_uuid) != enums.ServerStatus.RUNNING:
        if not start_server(fco_api, server_uuid):
            raise Exception('Could not start server!')


@operation
@with_fco_api
@with_exceptions_handled
def stop(fco_api, *args, **kwargs):
    server_uuid = ctx.instance.runtime_properties.get(RPROP_UUID)
    if get_server_status(fco_api, server_uuid) != enums.ServerStatus.STOPPED:
        if not stop_server(fco_api, server_uuid):
            raise Exception('Could not stop server!')


@operation
@with_fco_api
@with_exceptions_handled
def creation_validation(fco_api, *args, **kwargs):
    server_uuid = ctx.instance.runtime_properties.get(RPROP_UUID)
    try:
        get_resource(fco_api, server_uuid, RT.SERVER)
    except Exception:
        return False
    return True
