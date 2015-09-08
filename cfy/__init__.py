# coding=UTF-8

"""Provides a wrapper that functions as the Cloudify interface."""

from __future__ import print_function
from resttypes import cobjects
from time import sleep
from datetime import datetime

__author__ = 'alen'


class NoResourceError(Exception):

    """Exception raised when no results found despite being expected."""

    def __init__(self, res_type, query):
        self.res_type = res_type
        self.query = query

    def __str__(self):
        return 'No resource of type {} with query {}'.format(self.res_type,
                                                             self.query)


###############################################################################
# "Utility functions"
###############################################################################

def get_token(fco_api):
    """
    Get API token.

    :param fco_api: FCO API object
    :return: API public token
    """
    return fco_api.getAuthenticationToken(automaticallyRenew=True).publicToken


def wait_for_state(fco_api, res_uuid, state, res_type, time=5, step=24):
    """
    SSC-recommended state checking function.

    :param fco_api: FCO API object
    :param res_uuid: Resource UUID to monitor
    :param state: Desired resource state
    :param res_type: Resource type
    :param time: Time to wait before tries in seconds
    :param step: Number of tries
    :return: True if desired state is reached, False otherwise
    """
    fc1 = cobjects.FilterCondition(field='resourceUUID',
                                   condition='IS_EQUAL_TO',
                                   value=[res_uuid])
    fc2 = cobjects.FilterCondition(field='resourceState',
                                   condition='IS_EQUAL_TO',
                                   value=[state])
    sf = cobjects.SearchFilter(filterConditions=[fc1, fc2])
    result_set = fco_api.listResources(resourceType=res_type, searchFilter=sf)

    while step and not result_set.totalCount:
        result_set = fco_api.listResources(resourceType=res_type,
                                           searchFilter=sf)
        sleep(time)
        step -= 1

    return bool(result_set.totalCount)


def wait_for_status(fco_api, res_uuid, status, res_type, time=5, step=24):
    """
    SSC-recommended status checking function.

    :param fco_api: FCO API object
    :param res_uuid: Resource UUID to monitor
    :param status: Desired resource status
    :param res_type: Resource type
    :param time: Time to wait before tries in seconds
    :param step: Number of tries
    :return: True if desired status is reached, False otherwise
    """
    fc1 = cobjects.FilterCondition(field='resourceUUID',
                                   condition='IS_EQUAL_TO',
                                   value=[res_uuid])
    fc2 = cobjects.FilterCondition(field='status',
                                   condition='IS_EQUAL_TO',
                                   value=[status])
    sf = cobjects.SearchFilter(filterConditions=[fc1, fc2])
    result_set = fco_api.listResources(resourceType=res_type, searchFilter=sf)

    while step and not result_set.totalCount:
        result_set = fco_api.listResources(resourceType=res_type,
                                           searchFilter=sf)
        sleep(time)
        step -= 1

    return bool(result_set.totalCount)


def get_resource(fco_api, res_uuid, res_type):
    """
    Get a resource by Id and type.

    :param fco_api: FCO API object
    :param res_uuid: Resource UUID
    :param res_type: Resource type
    :return: Resource type-compatible dict
    """
    fc = cobjects.FilterCondition(field='resourceUUID',
                                  condition='IS_EQUAL_TO',
                                  value=[res_uuid])
    sf = cobjects.SearchFilter(filterConditions=[fc])
    try:
        return fco_api.listResources(searchFilter=sf, resourceType=res_type)\
            .list[0]
    except KeyError:
        raise NoResourceError(res_type, sf)


def first_resource(fco_api, res_type):
    """
    Get the first listed resource of a type.

    :param fco_api: FCO API object
    :param res_type: Resource type
    :return: Resource type-compatible dict
    """
    try:
        return fco_api.resourceType(resourceType=res_type).list[0]
    except KeyError:
        raise NoResourceError(res_type, None)


def get_resource_type(fco_api, res_type, limit=False, number=200, page=0):
    """
    Get list of resources of given type.

    :param fco_api: FCO API object
    :param res_type: Resource type
    :param limit: Use a query limit
    :param number: If a query limit is set, return this many results per page
    :param page: If aq query limit is set, return this page
    :return: List of resource type-compatible dicts
    """
    if limit:
        ql = cobjects.QueryLimit(from_=page*number, to=(page+1)*number,
                                 maxRecords=number, loadChildren=True)
        return fco_api.listResources(resourceType=res_type, queryLimit=ql)
    return fco_api.listResources(resourceType=res_type).list


def delete_resource(fco_api, res_uuid, res_type, cascade=False):
    """
    Delete a resource.

    :param fco_api: FCO API object
    :param res_uuid: Resource UUID
    :param res_type: Resource type
    :param cascade: Cascade the deletion
    :return: Job-compatible dict
    """
    return fco_api.deleteResource(resourceUUID=res_uuid, resourceType=res_type,
                                  cascade=cascade)


def get_prod_offer(fco_api, prod_offer_name):
    """
    Get product offer from product offer name.

    :param fco_api: FCO API object
    :param prod_offer_name: Product offer name
    :return: Product Offer-compatible dict
    """
    fc1 = cobjects.FilterCondition(field='resourceName',
                                   condition='IS_EQUAL_TO',
                                   value=[prod_offer_name])
    fc2 = cobjects.FilterCondition(field='resourceState',
                                   condition='IS_EQUAL_TO',
                                   value=['ACTIVE'])
    sf = cobjects.SearchFilter(filterConditions=[fc1, fc2])
    try:
        return fco_api.listResources(resourceType='PRODUCTOFFER',
                                     searchFilter=sf).list[0]
    except KeyError:
        raise NoResourceError('PRODUCTOFFER', sf)


###############################################################################
# Cluster stuff
###############################################################################

def get_cluster_uuid(fco_api):
    """
    SSC-recommended way to get a cluster.

    :param fco_api: FCO API object
    :return: Cluster-compatible dict
    """
    return first_resource(fco_api, 'CLUSTER').resourceUUID


###############################################################################
# VDC stuff
###############################################################################

def create_vdc(fco_api, cluster_uuid, name=None):
    """
    Create VDC.

    :param fco_api: FCO API object
    :param cluster_uuid: Cluster UUID
    :param name: VDC name
    :return: Job-compatible dict
    """
    if name is None:
        name = 'VDC ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    vdc = cobjects.VDC(resourceType='VDC', resourceName=name,
                       clusterUUID=cluster_uuid, sortOrder=None,
                       vdcUUID=None)
    return fco_api.createVDC(skeletonVDC=vdc)


def get_vdc_uuid_by_cluster(fco_api, cluster_uuid):
    """
    SSC-recommended way to get a VDC; essentially takes first VDC in the given
    cluster.

    :param fco_api: FCO API object
    :param cluster_uuid: Cluster UUID
    :return: VDC UUID
    """
    for v in get_resource_type(fco_api, 'VDC'):
        if v.clusterUUID == cluster_uuid:
            return v.resourceUUID
    raise NoResourceError('VDC', 'get_vdc_uuid_by_cluster')


def get_vdc_uuid(fco_api):
    """
    SSC-recommended way to get a VDC; takes first VDC listed.

    :param fco_api: FCO API object
    :return: VDC UUID
    """
    return first_resource(fco_api, 'VDC').resourceUUID


###############################################################################
# Network stuff
###############################################################################

def create_network(fco_api, cluster_uuid, net_type, vdc_uuid, name=None):
    """
    Create network.

    :param fco_api: FCO API object
    :param cluster_uuid: Cluster UUID
    :param net_type: Network type; currently recommended 'IP'
    :param vdc_uuid: VDC UUID
    :param name: Network name
    :return: Job-compatible dict
    """
    if name is None:
        name = 'NETWORK ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    net_data = cobjects.Network(clusterUUID=cluster_uuid,
                                resourceType='NETWORK', vdcUUID=vdc_uuid,
                                sortOrder=None, networkType=net_type,
                                resourceName=name)
    return fco_api.createNetwork(skeletonNetwork=net_data)


def get_network_uuid(fco_api, net_type, cluster_uuid):
    """
    Get best possible network UUID given type and cluster.

    :param fco_api: FCO API object
    :param net_type: Network type; currently recommended 'IP'
    :param cluster_uuid: Cluster UUID
    :return: Network UUID
    """
    fc = cobjects.FilterCondition(field='resourceState',
                                  condition='IS_EQUAL_TO',
                                  value=['ACTIVE'])
    sf = cobjects.SearchFilter(filterConditions=[fc])
    ql = cobjects.QueryLimit(loadChildren=False, maxRecords=200)
    result_set = fco_api.listResources(searchFilter=sf, queryLimit=ql,
                                       resourceType='NETWORK')
    for v in result_set.list:
        if v.clusterUUID == cluster_uuid and v.networkType == net_type:
            return v.resourceUUID
    raise NoResourceError('NETWORK', 'get_network_uuid')


###############################################################################
# Image stuff
###############################################################################

def get_image(fco_api, uuid):
    """
    Get image.

    :param fco_api: FCO API object
    :param uuid: Image UUID
    :return: Job-compatible dict
    """
    fc = cobjects.FilterCondition(field='resourceUUID',
                                  condition='IS_EQUAL_TO',
                                  value=[uuid])
    sf = cobjects.SearchFilter(filterConditions=[fc])
    result_set = fco_api.listResources(searchFilter=sf, resourceType='IMAGE')

    if not result_set.totalCount:
        raise RuntimeError('Image {} not found or no permissions to use.'
                           .format(uuid))
    try:
        return result_set.list[0]
    except KeyError:
        raise NoResourceError('IMAGE', sf)


###############################################################################
# Server stuff
###############################################################################

def get_server_state(fco_api, server_uuid):
    """
    Get server state.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible dict
    """
    try:
        return get_resource(fco_api, server_uuid, 'SERVER').status
    except AttributeError:
        raise NoResourceError('SERVER', server_uuid)


def change_server_status(fco_api, server_uuid, state):
    """
    Change server status.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param state: Server state
    :return: Job-compatible dict
    """
    fco_api.changeServerStatus(serverUUID=server_uuid, newStatus=state,
                               safe=True)
    return wait_for_status(fco_api, server_uuid, state, 'SERVER')


def start_server(fco_api, server_uuid):
    """
    Start server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible dict
    """
    return change_server_status(fco_api, server_uuid, 'RUNNING')


def stop_server(fco_api, server_uuid):
    """
    Stop server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible dict
    """
    return change_server_status(fco_api, server_uuid, 'STOPPED')


def create_server(fco_api, server_po_uuid, image_uuid, cluster_uuid, vdc_uuid,
                  cpu_count, ram_amount, boot_disk_po_uuid, keys_uuid=(),
                  name=None):
    """
    Create server.

    :param fco_api: FCO API object
    :param server_po_uuid: Server product offer UUID
    :param image_uuid: Server image UUID
    :param cluster_uuid: Server cluster UUID
    :param vdc_uuid: Server VDC UUID
    :param cpu_count: Server CPU count
    :param ram_amount: Server RAM amount
    :param boot_disk_po_uuid: Server boot disk product offer UUID
    :param keys_uuid: SSH keys to provision
    :param name: Server name
    :return: Job-compatible dict
    """
    if name is None:
        name = 'SERVER ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        disk_name = 'DISK ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    else:
        disk_name = name + ' Disk'
    disk_size = get_image(fco_api, image_uuid).size
    if not isinstance(keys_uuid, list):
        keys_uuid = [keys_uuid]
    disk = cobjects.Disk(storageCapabilities=None, clusterUUID=None,
                         resourceType='DISK', iso=False, sortOrder=None,
                         vdcUUID=vdc_uuid, resourceName=disk_name,
                         size=disk_size, resourceUUID=boot_disk_po_uuid)
    server = cobjects.Server(serverCapabilities=None, clusterUUID=cluster_uuid,
                             virtualizationType=None, resourceType='SERVER',
                             disks=[disk], vmId=None, sortOrder=None,
                             vdcUUID=vdc_uuid, resourceName=name,
                             productOfferUUID=server_po_uuid,
                             imageUUID=image_uuid, cpu=cpu_count,
                             ram=ram_amount, sshkeys=keys_uuid)
    return fco_api.createServer(skeletonServer=server)


###############################################################################
# Disk stuff
###############################################################################

def create_disk(fco_api, vdc_uuid, disk_po_uuid, disk_size, name=None):
    """
    Create Disk.

    :param fco_api: FCO API object
    :param vdc_uuid: VDC UUID
    :param disk_po_uuid: Disk product offer UUID
    :param disk_size: Disk size
    :param name: Disk name
    :return: Job-compatible object
    """
    if name is None:
        name = 'DISK ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sc = ['CLONE', 'CHILDREN_PERSIST_ON_DELETE', 'CHILDREN_PERSIST_ON_REVERT']
    disk = cobjects.Disk(storageCapabilities=sc, clusterUUID=None,
                         resourceType='DISK', iso=False, sortOrder=None,
                         vdcUUID=vdc_uuid, resourceName=name,
                         size=disk_size, resourceUUID=disk_po_uuid)
    return fco_api.createDisk(skeletonDisk=disk)


def attach_disk(fco_api, server_uuid, disk_uuid, index):
    """
    Attach disk to server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param disk_uuid: Disk UUID
    :param index: Disk index on the server
    :return: Job-compatible object
    """
    return fco_api.attachDisk(serverUUID=server_uuid, diskUUID=disk_uuid,
                              index=index)


def detach_disk(fco_api, server_uuid, disk_uuid):
    """
    Detach disk from server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param disk_uuid: Disk UUID
    :return: Job-compatible object
    """
    return fco_api.detachDisk(serverUUID=server_uuid, diskUUID=disk_uuid)


###############################################################################
# NIC stuff
###############################################################################

def create_nic(fco_api, cluster_uuid, net_type, net_uuid, vdc_uuid, name=None):
    """
    Create NIC.

    :param fco_api: FCO API object
    :param cluster_uuid: Cluster UUID
    :param net_type: Network type; currently recommended 'IP'
    :param net_uuid: Network UUID
    :param vdc_uuid: VDC UUID
    :param name: NIC name
    :return: Job-compatible dict
    """
    if name is None:
        name = 'NIC ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    nic_data = cobjects.Nic(clusterUUID=cluster_uuid, networkUUID=net_uuid,
                            vdcUUID=vdc_uuid, resourceType='NIC',
                            serverUUID=None, sortOrder=None,
                            networkType=net_type,
                            resourceName=name)
    return fco_api.createNetworkInterface(skeletonNIC=nic_data)


def attach_nic(fco_api, server_uuid, nic_uuid, index):
    """
    Attach NIC to server

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param nic_uuid: NIC UUID
    :return: Job-compatible dict
    """
    return fco_api.attachNetworkInterface(serverUUID=server_uuid,
                                          networkInterfaceUUID=nic_uuid,
                                          index=index)


def detach_nic(fco_api, server_uuid, nic_uuid):
    """
    Detach NIC from server

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param nic_uuid: NIC UUID
    :return: Job-compatible dict
    """
    return fco_api.detachNic(serverUUID=server_uuid,
                             networkInterfaceUUID=nic_uuid)


###############################################################################
# SSH Key stuff
###############################################################################

def get_customer_keys(fco_api, customer_uuid):
    """
    List resources belonging to a customer.

    :param fco_api: FCO API object
    :param customer_uuid: Customer UUID
    :return: list of dicts compatible to corresponding complex objects
    """
    fc = cobjects.FilterCondition(field='customerUUID',
                                  condition='IS_EQUAL_TO',
                                  value=[customer_uuid])
    sf = cobjects.SearchFilter(filterConditions=[fc])
    return fco_api.listResources(resourceType='SSHKEY', searchFilter=sf)


def create_ssh_key(fco_api, public_key, name):
    """
    Create SSH key.

    :param fco_api: FCO API object
    :param public_key: Public key string
    :param name: SSH Key name
    :return: Job-compatible dict
    """
    if name is None:
        name = 'SSHKEY ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    key = cobjects.SSHKey(clusterUUID=None, resourceType='SSHKEY',
                          publicKey=public_key, public_key=False,
                          sortOder=None, vdcUUID=None, resourceName=name)
    return fco_api.createSSHKey(skeletonSSHKey=key)


def attach_ssh_key(fco_api, server_uuid, key_uuid):
    """
    Attach SSH key to server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param key_uuid: Private key UUID
    :return: Job-compatible dict
    """
    return fco_api.attachSSHKey(serverUUID=server_uuid, SSHKeyUUID=key_uuid)


def detach_ssh_key(fco_api, server_uuid, key_uuid):
    """
    Detach SSH Key from server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param key_uuid: Private key UUID
    :return: Job-compatible dict
    """
    return fco_api.detachSSHKey(serverUUID=server_uuid, SSHKeyUUID=key_uuid)
