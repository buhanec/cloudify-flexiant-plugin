cloudify-flexiant-plugin
========================

A [Cloudify](http://getcloudify.org/) plugin for [Flexiant](https://www.flexiant.com/)'s cloud platform. Currently supports spawning instances and semi-automagically assigning them all the necessary devices.

Currently supports provisioning unconnected server instances, and has been designed to used and tested with an IP network type.

Additionally provides a framework upon which to build a more complete Flexiant plugin, with support for almost all REST API endpoints.

Installation
------------

The plugin is currently designed to be compatible with Cloudify 3.3, though it should work with any 3.x release. To use the plugin in a blueprint simply import the `plugin.yaml` from the `master` branch at the top of your blueprint:

```yaml
tosca_definitions_version: cloudify_dsl_1_0

imports:
  - http://www.getcloudify.org/spec/cloudify/3.3m4/types.yaml
  - https://raw.githubusercontent.com/buhanec/cloudify-flexiant-plugin/master/plugin.yaml
...
```

Once included in the blueprint, Flexiant Server instances can be provisioned using the `cloudify.flexiant.nodes.Server` type.

`cloudify.flexiant.nodes.Server` Properties
-------------------------------------------

Any instance of `cloudify.flexiant.nodes.Server` accepts the following properties in order to determine its configuration correctly:

* `auth`: An object/mapping containing authentication parameters for the FCO platform. The values required can all be gathered from the FCO CP. The available authentication methods are:
    * Username & password authentication, required keys: `username`, `password`, `customer` (as a UUID) and `url` (base URL pointing to the API)
    * API user authentication, required keys: `api_uuid`, `password`, `customer` (as a UUID) and `url` (base URL pointing to the API)
    * API token authentication, required keys: `token`, `url` (base URL pointing to the API)
    * All the API authentication methods also accept the optional boolean `ca_cert` (defaults to `True`) which determines whether the CA certificate should be checked when making API requests. Set to `False` if the CA certificate is not trusted on the Cloudify Manager instance.
* `image_uuid`: UUID of the image to be used.
* `key_uuid`: UUID of the key the manager should provision to gain access to instances (this key should most likely be the public key of the Cloudify Manager).
* `net_uuid`: UUID of the network to be used. Not absolutely necessary since the plugin makes an attempt to find a suitable network itself, but the search may fail. In such a case, or when you need to use a specific network, specify this manually.
* `net_type`: Type of network to search for, if `net_uuid` is not given. Defaults to `IP`.
* `cpu_count`: Number of CPUs to be passed to the API Server request; accepts integers. Defaults to `2`.
* `ram_amount`: Amount of RAM to be passed to the API Server request; accepts integers representing MB of ram Defaults to `2048`.
* `server_type`: Server type / offer to use when provisioning the instance. Should be named Defaults to `Standard Server`.
* `install_agent`: Boolean whether the Cloudify agent should be installed. Defaults to `true`.
* `cloudify_agent`: An object/mapping containing additional Cloudify agent installation parameters. Defaults to an empty object.
* `os`: A legacy property used for compatibility. A dict with the only key `type` containing valid OS types is required, by default the type is `linux`

An example configuration of a node would luck like the following:
```yaml
node_templates:
  fco_instance:
    type: cloudify.flexiant.nodes.Server
    properties:
      auth:
        api_uuid: 'api_user_uuid_goes_here'
        password: 'api_password_goes_here'
        customer: 'customer_uuid_goes_here'
        url: 'https://cp.yourname.flexiant.net'
        ca_cert: False
      image_uuid: 'image_uuid_goes_here'
      net_uuid: 'network_uuid_goes_here'
      server_type: 'My Server Offer'
      cpu_count: 4
      ram_amount: 4096
      key_uuid: 'manager_public_key_uuid_goes_here'
      cloudify_agent:  # As an example, if the Server instance is timing out with the lower default timeout
          wait_started_timeout: 60
          wait_started_interval: 3
```

Determining UUIDs and Other Values
----------------------------------

Using the CP, you can generally view the UUID by selecting the appropriate object type in the sidebar and then finding the exact object in the list:

![Sidebar Image](https://i.imgur.com/XyUZJaL.png)

And then checking the Information page for all the UUIDs under Related Resources & UUIDs:

![UUID Image](https://i.imgur.com/v4PhoYk.png)

The following UUIDs can be determined using this method:

* `api_uuid` - find your API user under Users
* `image_uuid`: find your image under Images
* `key_uuid`: find your public key under SSH Keys
* `net_uuid`: find your network under Networks

These UUIDs are generally related and can be found referenced multiple times across different pages.

The following have to be determined using a different procedure:

* `username`: your CP login username
* `customer`: can be found under related resources on e.g. your image Information page, or go to My Account > Settings > Account Details in the CP and find the Customer UUID in the Your API Details section (no, this is not the actual UUID):

![Account Image](https://i.imgur.com/M7En9W4.png)

* `net_type`: check [Flexiant documentation](http://docs.flexiant.com/display/DOCS/Introduction+to+Flexiant+Cloud+Orchestrator) for available types, currently only `IP` is supported without manual configuration and without tweaks to the plugin.
* `server_type`: on the CP select Add Server and select the VDC in which your image is contained. The `server_type` can be any of your Configuration options (in the given image it is `0.5 GB / 1 CPU`:

![Configuration Image](https://i.imgur.com/Sl6cwVF.png)

Contributing to the Plugin
--------------------------

To easily extend the plugin, the entire [FCO REST API](http://docs.flexiant.com/display/DOCS/REST+documentation) is exposed at a low level in the `api` module of the `fcoclient` package, drawing information from the `resttypes` package. To refer to available endpoints, objects and enums look inside the `resttypes` package.

The API is hidden is auto-configured and exposed to higher-level plugin operations in the `cfy` package, where most of the expansion should theoretically take place. Ideally every type provided by Flexiant should have a matching entry in the plugin definition (`plugin.yaml`), with related operations being defined in the `cfy` package.

The biggest drawbacks currently include the unfriendly UUID-filled configuration, lack of being able to reuse components an inability to create instances of anything but servers. Ideally lookups would be created using names, with fallbacks to UUIDs - more information should be, ideally, automagically determined, and manual settings only required when conflicts arise.

Updating the Defintions
-----------------------

When updating the definitions, care must be taken to ensure that:

* `GenericObject` is used in place of `object`
* `QueryField` operations match available operations in the `Condition` enum
