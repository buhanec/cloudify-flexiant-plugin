# coding=UTF-8

"""SSH key stuff."""

from __future__ import print_function
from cfy import (create_ssh_key,
                 wait_for_status,
                 get_resource,
                 delete_resource)
from cloudify import ctx
from cloudify.decorators import operation
from cfy.helpers import (with_fco_api, with_exceptions_handled)
from resttypes import enums
import os
from Crypto.PublicKey import RSA


RT = enums.ResourceType

PROP_RESOURCE_ID = 'resource_id'
PROP_USE_EXISTING = 'use_existing'
PROP_PRIVATE_KEY = 'private_key_path'
PROP_USER = 'user'
PROP_GLOBAL = 'global'

RPROP_UUID = 'uuid'


@operation
@with_fco_api
@with_exceptions_handled
def create(fco_api, *args, **kwargs):
    ctx.logger.info('Starting SSH key creation')

    # Ease of access
    _rp = ctx.instance.runtime_properties
    _np = ctx.node.properties

    # Check if existing server is to be used
    if _np[PROP_USE_EXISTING]:
        key = get_resource(fco_api, _np[PROP_RESOURCE_ID, RT.SSHKEY])
        _rp[RPROP_UUID] = key.resourceUUID
        return _rp[RPROP_UUID]

    # Get configuration
    private_key = os.path.expanduser(_np[PROP_PRIVATE_KEY])
    private_key_exists = os.path.isfile(private_key)
    user = _np[PROP_USER]
    global_ = _np[PROP_GLOBAL]

    # Get public key, generate private key if necessary
    if not private_key_exists:
        key = RSA.generate(2048)
        with open(private_key, 'w') as f:
            os.chmod(private_key, 0600)
            f.write(key.exportKey())
    else:
        with open(private_key, 'r') as f:
            key = RSA.importKey(f.read())
    public_key = key.publickey()

    key_name = '{}{}_{}'.format(ctx.bootstrap_context.resources_prefix,
                                ctx.deployment.id, ctx.instance.id)

    key_uuid = create_ssh_key(fco_api, public_key, user, global_, key_name)

    _rp[RPROP_UUID] = key_uuid

    return key_uuid


@operation
@with_fco_api
@with_exceptions_handled
def delete(fco_api, *args, **kwargs):
    key_uuid = ctx.instance.runtime_properties.get(RPROP_UUID)
    job_uuid = delete_resource(fco_api, key_uuid, RT.SERVER, True).resourceUUID
    if not wait_for_status(fco_api, job_uuid, enums.JobStatus.SUCCESSFUL,
                           RT.JOB):
        raise Exception('Failed to delete SSH key')


@operation
@with_fco_api
@with_exceptions_handled
def creation_validation(fco_api, *args, **kwargs):
    key_uuid = ctx.instance.runtime_properties.get(RPROP_UUID)
    try:
        get_resource(fco_api, key_uuid, RT.SSHKEY)
    except Exception:
        return False
    return True
