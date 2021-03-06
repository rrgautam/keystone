# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from oslo_config import cfg
from oslo_log import log

from keystone.common import dependency
from keystone.contrib import federation
from keystone import exception
from keystone.token.providers import common
from keystone.token.providers.fernet import token_formatters as tf


CONF = cfg.CONF
LOG = log.getLogger(__name__)


@dependency.requires('trust_api')
class Provider(common.BaseProvider):
    def __init__(self, *args, **kwargs):
        super(Provider, self).__init__(*args, **kwargs)

        self.token_formatter = tf.TokenFormatter()

    def needs_persistence(self):
        """Should the token be written to a backend."""
        return False

    def issue_v2_token(self, token_ref, roles_ref=None, catalog_ref=None):
        """Issue a V2 formatted token.

        :param token_ref: reference describing the token
        :param roles_ref: reference describing the roles for the token
        :param catalog_ref: reference describing the token's catalog
        :raises keystone.exception.NotImplemented: when called

        """
        raise exception.NotImplemented()

    def _build_federated_info(self, token_data):
        """Extract everything needed for federated tokens.

        This dictionary is passed to the FederatedPayload token formatter,
        which unpacks the values and builds the Fernet token.

        """
        group_ids = token_data.get('user', {}).get(
            federation.FEDERATION, {}).get('groups')
        idp_id = token_data.get('user', {}).get(
            federation.FEDERATION, {}).get('identity_provider', {}).get('id')
        protocol_id = token_data.get('user', {}).get(
            federation.FEDERATION, {}).get('protocol', {}).get('id')
        if not group_ids:
            group_ids = list()
        federated_dict = dict(group_ids=group_ids, idp_id=idp_id,
                              protocol_id=protocol_id)
        return federated_dict

    def _rebuild_federated_info(self, federated_dict, user_id):
        """Format federated information into the token reference.

        The federated_dict is passed back from the FederatedPayload token
        formatter. The responsibility of this method is to format the
        information passed back from the token formatter into the token
        reference before constructing the token data from the
        V3TokenDataHelper.

        """
        g_ids = federated_dict['group_ids']
        idp_id = federated_dict['idp_id']
        protocol_id = federated_dict['protocol_id']
        federated_info = dict(groups=g_ids,
                              identity_provider=dict(id=idp_id),
                              protocol=dict(id=protocol_id))
        token_dict = {'user': {federation.FEDERATION: federated_info}}
        token_dict['user']['id'] = user_id
        token_dict['user']['name'] = user_id
        return token_dict

    def issue_v3_token(self, user_id, method_names, expires_at=None,
                       project_id=None, domain_id=None, auth_context=None,
                       trust=None, metadata_ref=None, include_catalog=True,
                       parent_audit_id=None):
        """Issue a V3 formatted token.

        Here is where we need to detect what is given to us, and what kind of
        token the user is expecting. Depending on the outcome of that, we can
        pass all the information to be packed to the proper token format
        handler.

        :param user_id: ID of the user
        :param method_names: method of authentication
        :param expires_at: token expiration time
        :param project_id: ID of the project being scoped to
        :param domain_id: ID of the domain being scoped to
        :param auth_context: authentication context
        :param trust: ID of the trust
        :param metadata_ref: metadata reference
        :param include_catalog: return the catalog in the response if True,
                                otherwise don't return the catalog
        :param parent_audit_id: ID of the patent audit entity
        :returns: tuple containing the id of the token and the token data

        """
        token_ref = None
        # NOTE(lbragstad): This determines if we are dealing with a federated
        # token or not. The groups for the user will be in the returned token
        # reference.
        federated_dict = None
        if auth_context and self._is_mapped_token(auth_context):
            token_ref = self._handle_mapped_tokens(
                auth_context, project_id, domain_id)
            federated_dict = self._build_federated_info(token_ref)

        token_data = self.v3_token_data_helper.get_token_data(
            user_id,
            method_names,
            auth_context.get('extras') if auth_context else None,
            domain_id=domain_id,
            project_id=project_id,
            expires=expires_at,
            trust=trust,
            bind=auth_context.get('bind') if auth_context else None,
            token=token_ref,
            include_catalog=include_catalog,
            audit_info=parent_audit_id)

        token = self.token_formatter.create_token(
            user_id,
            token_data['token']['expires_at'],
            token_data['token']['audit_ids'],
            methods=method_names,
            domain_id=domain_id,
            project_id=project_id,
            trust_id=token_data['token'].get('OS-TRUST:trust', {}).get('id'),
            federated_info=federated_dict)
        return token, token_data

    def validate_v2_token(self, token_ref):
        """Validate a V2 formatted token.

        :param token_ref: reference describing the token to validate
        :returns: the token data
        :raises keystone.exception.NotImplemented: when called

        """
        raise exception.NotImplemented()

    def validate_v3_token(self, token):
        """Validate a V3 formatted token.

        :param token: a string describing the token to validate
        :returns: the token data
        :raises: keystone.exception.Unauthorized

        """
        (user_id, methods, audit_ids, domain_id, project_id, trust_id,
            federated_info, created_at, expires_at) = (
                self.token_formatter.validate_token(token))

        token_dict = None
        if federated_info:
            token_dict = self._rebuild_federated_info(federated_info, user_id)
        trust_ref = self.trust_api.get_trust(trust_id)

        return self.v3_token_data_helper.get_token_data(
            user_id,
            method_names=methods,
            domain_id=domain_id,
            project_id=project_id,
            issued_at=created_at,
            expires=expires_at,
            trust=trust_ref,
            token=token_dict,
            audit_info=audit_ids)

    def _get_token_id(self, token_data):
        """Generate the token_id based upon the data in token_data.

        :param token_data: token information
        :type token_data: dict
        :raises keystone.exception.NotImplemented: when called
        """
        raise exception.NotImplemented()
