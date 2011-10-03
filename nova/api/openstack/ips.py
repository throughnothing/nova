# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from lxml import etree

from webob import exc

import nova
from nova.api.openstack import common
from nova.api.openstack.views import addresses as views_addresses
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova import log as logging
from nova import flags


LOG = logging.getLogger('nova.api.openstack.ips')
FLAGS = flags.FLAGS


class Controller(object):
    """The servers addresses API controller for the Openstack API."""

    def __init__(self):
        self.compute_api = nova.compute.API()

    def _get_instance(self, context, server_id):
        try:
            instance = self.compute_api.get(context, server_id)
        except nova.exception.NotFound:
            msg = _("Instance does not exist")
            raise exc.HTTPNotFound(explanation=msg)
        return instance

    def create(self, req, server_id, body):
        raise exc.HTTPNotImplemented()

    def delete(self, req, server_id, id):
        raise exc.HTTPNotImplemented()


class ControllerV10(Controller):

    def index(self, req, server_id):
        context = req.environ['nova.context']
        instance = self._get_instance(context, server_id)
        networks = common.get_networks_for_instance(context, instance)
        builder = self._get_view_builder(req)
        return {'addresses': builder.build(networks)}

    def show(self, req, server_id, id):
        context = req.environ['nova.context']
        instance = self._get_instance(context, server_id)
        networks = common.get_networks_for_instance(context, instance)
        builder = self._get_view_builder(req)
        if id == 'private':
            view = builder.build_private_parts(networks)
        elif id == 'public':
            view = builder.build_public_parts(networks)
        else:
            msg = _("Only private and public networks available")
            raise exc.HTTPNotFound(explanation=msg)

        return {id: view}

    def _get_view_builder(self, req):
        return views_addresses.ViewBuilderV10()


class ControllerV11(Controller):

    def index(self, req, server_id):
        context = req.environ['nova.context']
        instance = self._get_instance(context, server_id)
        networks = common.get_networks_for_instance(context, instance)
        return {'addresses': self._get_view_builder(req).build(networks)}

    def show(self, req, server_id, id):
        context = req.environ['nova.context']
        instance = self._get_instance(context, server_id)
        networks = common.get_networks_for_instance(context, instance)
        network = self._get_view_builder(req).build_network(networks, id)

        if network is None:
            msg = _("Instance is not a member of specified network")
            raise exc.HTTPNotFound(explanation=msg)

        return network

    def _get_view_builder(self, req):
        return views_addresses.ViewBuilderV11()


class IPXMLSerializer(wsgi.XMLDictSerializer):

    NSMAP = {None: xmlutil.XMLNS_V11}

    def __init__(self, xmlns=wsgi.XMLNS_V11):
        super(IPXMLSerializer, self).__init__(xmlns=xmlns)

    def populate_addresses_node(self, addresses_elem, addresses_dict):
        for (network_id, ip_dicts) in addresses_dict.items():
            network_elem = self._create_network_node(network_id, ip_dicts)
            addresses_elem.append(network_elem)

    def _create_network_node(self, network_id, ip_dicts):
        network_elem = etree.Element('network', nsmap=self.NSMAP)
        network_elem.set('id', str(network_id))
        for ip_dict in ip_dicts:
            ip_elem = etree.SubElement(network_elem, 'ip')
            ip_elem.set('version', str(ip_dict['version']))
            ip_elem.set('addr', ip_dict['addr'])
        return network_elem

    def show(self, network_dict):
        (network_id, ip_dicts) = network_dict.items()[0]
        network = self._create_network_node(network_id, ip_dicts)
        return self._to_xml(network)

    def index(self, addresses_dict):
        addresses = etree.Element('addresses', nsmap=self.NSMAP)
        self.populate_addresses_node(addresses,
                                     addresses_dict.get('addresses', {}))
        return self._to_xml(addresses)


def create_resource(version):
    controller = {
        '1.0': ControllerV10,
        '1.1': ControllerV11,
    }[version]()

    metadata = {
        'list_collections': {
            'public': {'item_name': 'ip', 'item_key': 'addr'},
            'private': {'item_name': 'ip', 'item_key': 'addr'},
        },
    }

    xml_serializer = {
        '1.0': wsgi.XMLDictSerializer(metadata=metadata, xmlns=wsgi.XMLNS_V11),
        '1.1': IPXMLSerializer(),
    }[version]

    serializer = wsgi.ResponseSerializer({'application/xml': xml_serializer})

    return wsgi.Resource(controller, serializer=serializer)
