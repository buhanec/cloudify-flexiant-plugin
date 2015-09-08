# coding=UTF-8

"""Provides a wrapper that functions as the Cloudify interface."""

from __future__ import print_function
from resttypes import cobjects, enums
from functools import wraps
from time import sleep
from datetime import datetime, timedelta

__author__ = 'alen'


JS = enums.JobStatus


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


###############################################################################
# Job scheduling and dependencies
###############################################################################

class Task(object):

    """Represents a task with potential dependencies."""

    def __init__(self, fco_api, func, timeout, dependencies):
        self._fco_api = fco_api
        self._func = func
        self._timeout = float(timeout)
        self._dependencies = set(dependencies)
        self._completed = False
        self._successful = False
        self._job_uuid = None
        self._result = None

    @property
    def dependencies(self):
        return self._dependencies

    @property
    def successful(self):
        return self._successful

    @property
    def completed(self):
        return self._completed

    @property
    def job_uuid(self):
        if isinstance(self._result, cobjects.ComplexObject):
            return self._result.resourceUUID
        return None

    @property
    def item_uuid(self):
        if isinstance(self._result, cobjects.ComplexObject):
            return self._result.itemUUID
        return None

    def update(self):
        if self._completed:
            return False

        if not all(task.successful for task in self._dependencies):
            raise TaskStartError()

        if self._result is None:
            self._result = self._func()
        else:
            self._result = get_resource(self._fco_api,
                                        self._result.resourceUUID,
                                        'JOB')
        status = JS(self._result.status)

        if status in {JS.FAILED, JS.CANCELLED}:
            self._completed = True
            self._successful = False
        elif status in {JS.SUCCESSFUL}:
            self._completed = True
            self._successful = True
        return True

    def add_dependency(self, task):
        self._dependencies.add(task)


class Topology(object):

    """Represents the overall topology and is in charge of running tasks."""

    def __init__(self, check_rate=5):
        self._check_rate = float(check_rate)
        self._nodes = set()
        self._roots = set()
        self._current = set()

    def add_task_tree(self, task):
        self._nodes.add(task)
        if not len(task.dependencies):
            self._roots.add(task)

    def create_dependency(self, task, dependency):
        task.add_dependency(dependency)
        try:
            self._roots.remove(task)
        except KeyError:
            pass

    def execute(self):
        # TODO: concurrent execution with dependency passing parameters
        # ... or use partials and uuid_with_timeout
        pass


def uuid_with_timeout(f, fco_api, timeout=None, check_rate=5):
    """
    Fetch item UUID from using a function that returns a Job or Job-compatible
    object. If a timeout is specified the Job will be cancelled if not
    successful before within the timeout period..

    :param f: function to wrap
    :param fco_api: FCO API object
    :param timeout: time in seconds to wait before cancelling the job
    :param check_rate: time in seconds to wait before checking job status
    :return: function wrapper
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        result = f(fco_api, *args, **kwargs)
        f_timeout = timeout
        f_check_rate = float(check_rate)
        if f_timeout is not None and int(f_timeout) > 0:
            when = result.startTime + timedelta(seconds=int(f_timeout))
            # TODO: can cancellations be scheduled?
            fco_api.cancelJob(JobUUID=result.resourceUUID, when=when)
        while True:
            status = JS(result.status)
            if status == JS.FAILED:
                raise JobFailed()
            elif status == JS.CANCELLED:
                raise JobCancelled()
            elif status == JS.SUCCESSFUL:
                return result.itemUUID
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


def get_resource(fco_api, res_id, res_type=None, force_uuid=False):
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
    named = []
    nsf = None
    if not force_uuid:
        fc = cobjects.FilterCondition(field='resourceName',
                                      condition='IS_EQUAL_TO',
                                      value=[res_id])
        nsf = cobjects.SearchFilter(filterConditions=[fc])
        if res_type is not None:
            named = fco_api.listResources(searchFilter=nsf,
                                          resourceType=res_type).list
        else:
            named = fco_api.listResources(searchFilter=nsf).list
        if len(named) == 1:
            return named[0]
        else:
            named = set(r.resourceUUID for r in named)
    fc = cobjects.FilterCondition(field='resourceUUID',
                                  condition='IS_EQUAL_TO',
                                  value=[res_id])
    sf = cobjects.SearchFilter(filterConditions=[fc])
    if res_type is not None:
        uuid = fco_api.listResources(searchFilter=sf, resourceType=res_type) \
            .list
    else:
        uuid = fco_api.listResources(searchFilter=sf).list
    if len(uuid) == 1:
        return uuid[0]
    elif len(named):
        raise ConflictingResourceError(res_type, nsf, named)
    else:
        raise NoResourceError(res_type, sf)


def first_resource(fco_api, res_type):
    """
    Get the first listed resource of a type.

    :param fco_api: FCO API object
    :param res_type: Resource type
    :return: Resource type-compatible object
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


def get_prod_offer(fco_api, prod_offer_name):
    """
    Get product offer from product offer name.

    :param fco_api: FCO API object
    :param prod_offer_name: Product offer name
    :return: Product Offer-compatible object
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
    :return: Cluster-compatible object
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
    :return: Job-compatible object
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
    :return: Job-compatible object
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
    :return: Job-compatible object
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
    :return: Job-compatible object
    """
    fco_api.changeServerStatus(serverUUID=server_uuid, newStatus=state,
                               safe=True)
    return wait_for_status(fco_api, server_uuid, state, 'SERVER')


def start_server(fco_api, server_uuid):
    """
    Start server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible object
    """
    return change_server_status(fco_api, server_uuid, 'RUNNING')


def stop_server(fco_api, server_uuid):
    """
    Stop server.

    :param fco_api: FCO API object
    :param server_uuid: Server UUID
    :return: Job-compatible object
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
    :return: Job-compatible object
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
    :return: Job-compatible object
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
