# coding=UTF-8

"""Provides a wrapper that functions as the Cloudify interface."""

from __future__ import print_function
from resttypes import cobjects, enums
from functools import wraps
from time import sleep
from datetime import datetime, timedelta

__author__ = 'alen'


RT = enums.ResourceType
R = cobjects.Resource


###############################################################################
# Exceptions
###############################################################################

class NoResourceError(Exception):

    """Exception raised when no results found despite being expected."""

    def __init__(self, res_type, query):
        self.res_type = res_type
        self.query = query

    def __str__(self):
        return 'No resource of type {} with query {}'.format(self.res_type,
                                                             self.query)


class ConflictingResourceError(Exception):

    """Exception raised when conflicting results found."""

    def __init__(self, res_type, query, results):
        self.res_type = res_type
        self.query = query
        self.results = results

    def __str__(self):
        return 'Multipled matches: {} of type {} with query {}'.format(
            self.results, self.res_type, self.query)


class TaskStartError(Exception):

    """Exception raised when Task cannot start."""


class JobFailed(Exception):

    """Exception raised with Job failed."""


class JobCancelled(Exception):

    """Exception raised with Job is cancelled."""


class JobTimedout(Exception):

    """Exception raised with Job is timed out."""



###############################################################################
# Job scheduling and dependencies
###############################################################################

def created_uuid_from_job(f, timeout=300, check_rate=3):
    """
    Fetch item UUID from using a function that returns a Job or Job-compatible
    object. If a timeout is specified the Job will be cancelled if not
    successful within the timeout period, with an error margin of the check
    rate.

    :param f: function to wrap
    :param fco_api: FCO API object
    :param timeout: time in seconds to wait before cancelling the job
    :param check_rate: time in seconds to wait before checking job status
    :return: function wrapper
    """
    @wraps(f)
    def wrapper(fco_api, *args, **kwargs):
        # Timeout and check rate
        f_cancel = datetime.now() + timedelta(seconds=timeout)
        f_check_rate = check_rate

        # Execute creation query
        result = f(fco_api, *args, **kwargs)

        while True:
            status = enums.JobStatus(result.status)
            if status == enums.JobStatus.FAILED:
                raise JobFailed(result.resourceUUID)
            elif status == enums.JobStatus.CANCELLED:
                raise JobCancelled(result.resourceUUID)
            elif status == enums.JobStatus.SUCCESSFUL:
                return result.itemUUID
            if datetime.now() > f_cancel:
                raise JobTimedout(result.resourceUUID)
            sleep(f_check_rate)
            result = get_resource(fco_api, result.resourceUUID, 'JOB')
    return wrapper


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


def list_resource(fco_api, conditions, resource_type=None, **limits):
    ql = cobjects.QueryLimit(**limits)
    if not isinstance(conditions, list):
        conditions = [conditions]
    sf = cobjects.SearchFilter(filterConditions=conditions)
    if resource_type is None:
        return fco_api.listResources(searchFilter=sf, queryLimit=ql)
    return fco_api.listResources(searchFilter=sf, queryLimit=ql,
                                 resourceType=resource_type)


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
    filter_ = (R.resourceUUID == res_uuid) & (R.resourceState == state)
    result_set = list_resource(fco_api, filter_, res_type)

    while step and not result_set.totalCount:
        result_set = list_resource(fco_api, filter_, res_type)
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


def get_resource(fco_api, res_id, res_type=None,
                 res_state=enums.ResourceState.ACTIVE, force_uuid=False):
    """
    Get a resource by first checking for a resource with the name `res_id`.
    If no results or multiple results are found, the next check is performed
    for a resource with the UUID `res_id`. If a resource is found, it is
    returned. If no resource and multiple resources were found with the name
    query, a `ConflictingResourceError` is raised, otherwise a
    `NoResourceError` is raised.

    :param fco_api: FCI API object
    :param res_id: Resource name or UUID
    :param res_type: Resource type (optional)
    :param force_uuid: Force UUID check
    :return: Resource of type-compatible object
    """
    filter_name = (R.resourceName == res_id) & (R.resourceState == res_state)
    filter_uuid = (R.resourceUUID == res_id) & (R.resourceState == res_state)

    if res_type is not None:

        def _list_resource(filter_):
            return list_resource(fco_api, filter_, res_type).list
    else:

        def _list_resource(filter_):
            return list_resource(fco_api, filter_).list

    if not force_uuid:
        named = _list_resource(filter_name)
    else:
        named = []

    uuided = _list_resource(filter_uuid)

    if len(uuided) == 1:
        return uuided[0]
    elif len(named) == 1:
        return named[0]
    elif len(named):
        raise ConflictingResourceError(res_type, filter_name,
                                       set(r.resourceUUID for r in named))
    else:
        raise NoResourceError(res_type, filter_uuid)


def first_resource(fco_api, res_type):
    """
    Get the first listed resource of a type.

    :param fco_api: FCO API object
    :param res_type: Resource type
    :return: Resource type-compatible object
    """
    result_set = fco_api.resourceType(resourceType=res_type)
    if result_set.totalCount:
        return result_set.list[0]
    raise NoResourceError(res_type, None)


def get_resource_type(fco_api, res_type, limit=False, number=200, page=0):
    """
    Get list of resources of given type.

    :param fco_api: FCO API object
    :param res_type: Resource type
    :param limit: Use a query limit
    :param number: If a query limit is set, return this many results per page
    :param page: If aq query limit is set, return this page
    :return: List of resource type-compatible objects
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
    :return: Job-compatible object
    """
    return fco_api.deleteResource(resourceUUID=res_uuid, resourceType=res_type,
                                  cascade=cascade)


###############################################################################
# Cluster stuff
###############################################################################

def get_cluster_uuid(fco_api):
    """
    SSC-recommended way to get a cluster.

    :param fco_api: FCO API object
    :return: Cluster-compatible object
    """
    return first_resource(fco_api, RT.CLUSTER).resourceUUID


###############################################################################
# VDC stuff
###############################################################################

@created_uuid_from_job
def create_vdc(fco_api, cluster_uuid, name=None):
    """
    Create VDC.

    :param fco_api: FCO API object
    :param cluster_uuid: Cluster UUID
    :param name: VDC name
    :return: Job-compatible object
    """
    if name is None:
        name = 'VDC ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    vdc = cobjects.VDC(resourceType=RT.VDC, resourceName=name,
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
    filter_ = ((cobjects.VDC.resourceState == enums.ResourceState.ACTIVE) &
               (cobjects.VDC.clusterUUID == cluster_uuid))
    result_set = list_resource(fco_api, filter_, RT.VDC)
    if result_set.totalCount:
        return result_set.list[0].resourceUUID
    raise NoResourceError(RT.VDC, filter_)


def get_vdc_uuid(fco_api):
    """
    SSC-recommended way to get a VDC; takes first VDC listed.

    :param fco_api: FCO API object
    :return: VDC UUID
    """
    return first_resource(fco_api, RT.VDC).resourceUUID


###############################################################################
# Network stuff
###############################################################################

@created_uuid_from_job
def create_network(fco_api, cluster_uuid, net_type, vdc_uuid, name=None):
    """
    Create network.

    :param fco_api: FCO API object
    :param cluster_uuid: Cluster UUID
    :param net_type: Network type; currently recommended 'IP'
    :param vdc_uuid: VDC UUID
    :param name: Network name
    :return: Job-compatible object
    """
    if name is None:
        name = 'NETWORK ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    net_data = cobjects.Network(clusterUUID=cluster_uuid,
                                resourceType=RT.NETWORK, vdcUUID=vdc_uuid,
                                sortOrder=None, networkType=net_type,
                                resourceName=name)
    return fco_api.createNetwork(skeletonNetwork=net_data)


def get_network_uuid_by_vdc(fco_api, net_type, vdc_uuid):
    """
    Get best possible network UUID given type and cluster.

    :param fco_api: FCO API object
    :param net_type: Network type; currently recommended 'IP'
    :param vdc_uuid: VDC UUID
    :return: Network UUID
    """
    filter_ = ((cobjects.Network.resourceState == enums.ResourceState.ACTIVE) &
               (cobjects.Network.vdcUUID == vdc_uuid) &
               (cobjects.Network.networkType == net_type))
    result_set = list_resource(fco_api, filter_, RT.NETWORK)
    if result_set.totalCount:
        return result_set.list[0].resourceUUID
    raise NoResourceError(RT.NETWORK, filter_)


def get_network_uuid_by_cluster(fco_api, net_type, cluster_uuid):
    """
    Get best possible network UUID given type and cluster.

    :param fco_api: FCO API object
    :param net_type: Network type; currently recommended 'IP'
    :param cluster_uuid: Cluster UUID
    :return: Network UUID
    """
    filter_ = ((cobjects.Network.resourceState == enums.ResourceState.ACTIVE) &
               (cobjects.Network.clusterUUID == cluster_uuid) &
               (cobjects.Network.networkType == net_type))
    result_set = list_resource(fco_api, filter_, RT.NETWORK)
    if result_set.totalCount:
        return result_set.list[0].resourceUUID
    raise NoResourceError(RT.NETWORK, filter_)


###############################################################################
# Server stuff
###############################################################################

def get_server_status(fco_api, server_uuid):
    """
    Get server state.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible object
    """
    return get_resource(fco_api, server_uuid, RT.SERVER).status


def change_server_status(fco_api, server_uuid, status):
    """
    Change server status.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param status: Server status
    :return: Job-compatible object
    """
    fco_api.changeServerStatus(serverUUID=server_uuid, newStatus=status,
                               safe=True)
    return wait_for_status(fco_api, server_uuid, status, RT.SERVER)


def start_server(fco_api, server_uuid):
    """
    Start server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible object
    """
    return change_server_status(fco_api, server_uuid,
                                enums.ServerStatus.RUNNING)


def stop_server(fco_api, server_uuid):
    """
    Stop server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible object
    """
    return change_server_status(fco_api, server_uuid,
                                enums.ServerStatus.STOPPED)


@created_uuid_from_job
def create_server_with_skeletons(fco_api, server_po_id, image_id, vdc_id,
                                 cpu_count, ram_amount, disk_skeletons=(),
                                 nic_skeletons=(), key_uuids=(), name=None):
    """
    Create a server given skeletons of related objects.

    :param fco_api: FCO API object
    :param server_po_id: Server product offer name or UUID
    :param image_id: Server image name or UUID
    :param vdc_id: Server VDC name or UUID
    :param cpu_count: Server CPU count
    :param ram_amount: Server RAM amount
    :param disk_skeletons: Server disk skeletons
    :param nic_skeletons: Server NIC skeletons
    :param key_uuids: Server keys to attach
    :param name: Server name, propagates to disks & NICs
    :return: Job-compatible object
    """

    if name is None:
        name = 'SERVER ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    server_po_uuid = get_resource(fco_api, server_po_id, RT.PRODUCTOFFER) \
        .resourceUUID
    image_uuid = get_resource(fco_api, image_id, RT.IMAGE).resourceUUID
    vdc = get_resource(fco_api, vdc_id, RT.VDC)
    vdc_uuid = vdc.resourceUUID
    cluster_uuid = vdc.clusterUUID

    server = cobjects.Server(serverCapabilities=None, clusterUUID=cluster_uuid,
                             virtualizationType=None, resourceType=RT.SERVER,
                             disks=disk_skeletons, vmId=None, sortOrder=None,
                             vdcUUID=vdc_uuid, resourceName=name,
                             productOfferUUID=server_po_uuid,
                             imageUUID=image_uuid, cpu=cpu_count,
                             ram=ram_amount, sshkeys=key_uuids,
                             nics=nic_skeletons)
    return fco_api.createServer(skeletonServer=server)


@created_uuid_from_job
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
    :return: Job-compatible object
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
                         resourceType=RT.DISK, iso=False, sortOrder=None,
                         vdcUUID=vdc_uuid, resourceName=disk_name,
                         size=disk_size, resourceUUID=boot_disk_po_uuid)
    server = cobjects.Server(serverCapabilities=None, clusterUUID=cluster_uuid,
                             virtualizationType=None, resourceType=RT.SERVER,
                             disks=[disk], vmId=None, sortOrder=None,
                             vdcUUID=vdc_uuid, resourceName=name,
                             productOfferUUID=server_po_uuid,
                             imageUUID=image_uuid, cpu=cpu_count,
                             ram=ram_amount, sshkeys=keys_uuid)
    return fco_api.createServer(skeletonServer=server)


###############################################################################
# Disk stuff
###############################################################################

@created_uuid_from_job
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
    sc = [enums.StorageCapability.CLONE,
          enums.StorageCapability.CHILDREN_PERSIST_ON_DELETE,
          enums.StorageCapability.CHILDREN_PERSIST_ON_REVERT]
    disk = cobjects.Disk(storageCapabilities=sc, clusterUUID=None,
                         resourceType=RT.DISK, iso=False, sortOrder=None,
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

@created_uuid_from_job
def create_nic(fco_api, cluster_uuid, net_type, net_uuid, vdc_uuid, name=None):
    """
    Create NIC.

    :param fco_api: FCO API object
    :param cluster_uuid: Cluster UUID
    :param net_type: Network type; currently recommended 'IP'
    :param net_uuid: Network UUID
    :param vdc_uuid: VDC UUID
    :param name: NIC name
    :return: Job-compatible object
    """
    if name is None:
        name = 'NIC ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    nic_data = cobjects.Nic(clusterUUID=cluster_uuid, networkUUID=net_uuid,
                            vdcUUID=vdc_uuid, resourceType=RT.NIC,
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
    :return: Job-compatible object
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
    :return: Job-compatible object
    """
    return fco_api.detachNic(serverUUID=server_uuid,
                             networkInterfaceUUID=nic_uuid)


###############################################################################
# SSH Key stuff
###############################################################################

@created_uuid_from_job
def create_ssh_key(fco_api, public_key, name=None):
    """
    Create SSH key.

    :param fco_api: FCO API object
    :param public_key: Public key string
    :param name: SSH Key name
    :return: Job-compatible object
    """
    if name is None:
        name = 'SSHKEY ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    key = cobjects.SSHKey(clusterUUID=None, resourceType=RT.SSHKEY,
                          publicKey=public_key, sortOrder=None, vdcUUID=None,
                          resourceName=name)
    return fco_api.createSSHKey(skeletonSSHKey=key)


def attach_ssh_key(fco_api, server_uuid, key_uuid):
    """
    Attach SSH key to server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param key_uuid: Private key UUID
    :return: Job-compatible object
    """
    return fco_api.attachSSHKey(serverUUID=server_uuid, SSHKeyUUID=key_uuid)


def detach_ssh_key(fco_api, server_uuid, key_uuid):
    """
    Detach SSH Key from server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :param key_uuid: Private key UUID
    :return: Job-compatible object
    """
    return fco_api.detachSSHKey(serverUUID=server_uuid, SSHKeyUUID=key_uuid)
