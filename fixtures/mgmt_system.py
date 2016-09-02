import pytest

from cfme.common.provider import BaseProvider
from utils import providers


@pytest.fixture
def setup_providers(uses_providers):
    """Adds all providers listed in cfme_data.yaml

    This includes both cloud and infra provider types.
    """
    providers.setup_providers(validate=True, check_existing=True)


@pytest.fixture
def setup_infrastructure_providers(uses_infra_providers):
    """Adds all infrastructure providers listed in cfme_data.yaml

    This includes ``rhev`` and ``virtualcenter`` provider types
    """
    providers._setup_providers('infra', validate=True, check_existing=True)


@pytest.fixture
def setup_cloud_providers(uses_cloud_providers):
    """Adds all cloud providers listed in cfme_data.yaml

    This includes ``ec2`` and ``openstack`` provider types
    """
    providers._setup_providers('cloud', validate=True, check_existing=True)


@pytest.fixture
def setup_container_providers(uses_container_providers):
    """Adds all container providers listed in cfme_data.yaml

    This includes ``kubernetes`` and ``openshift`` provider types
    """
    providers._setup_providers('container', validate=True, check_existing=True)


@pytest.fixture(scope='module')  # IGNORE:E1101
def mgmt_sys_api_clients(cfme_data, uses_providers):
    """Returns a list of management system api clients"""
    clients = {}
    for provider_key in cfme_data['management_systems']:
        clients[provider_key] = providers.get_mgmt(provider_key)
    return clients


@pytest.fixture
def has_no_providers():
    """ Clears all management systems from an applicance

    This is a destructive fixture. It will clear all managements systems from
    the current appliance.
    """
    BaseProvider.clear_providers()


@pytest.fixture
def has_no_cloud_providers():
    """ Clears all cloud providers from an appliance

    This is a destructive fixture. It will clear all cloud managements systems from
    the current appliance.
    """
    BaseProvider.clear_provider_by_type(BaseProvider.type_mapping['cloud'], validate=True)


@pytest.fixture
def has_no_infra_providers():
    """ Clears all infrastructure providers from an appliance

    This is a destructive fixture. It will clear all infrastructure managements systems from
    the current appliance.
    """
    BaseProvider.clear_provider_by_type(BaseProvider.type_mapping['infra'], validate=True)


@pytest.fixture
def has_no_container_providers():
    """ Clears all container providers from an appliance

    This is a destructive fixture. It will clear all container managements systems from
    the current appliance.
    """
    BaseProvider.clear_provider_by_type(BaseProvider.type_mapping['container'], validate=True)


@pytest.fixture
def has_no_middleware_providers():
    """Clear all middleware providers."""
    BaseProvider.clear_provider_by_type(BaseProvider.type_mapping['middleware'], validate=True)
