# -*- coding: utf-8 -*-
"""A model of an Infrastructure PhysicalServer in CFME."""
import attr
import requests
from navmazing import NavigateToSibling, NavigateToAttribute
from cached_property import cached_property
from wrapanapi.lenovo import LenovoSystem

from cfme.common import PolicyProfileAssignable, Taggable
from cfme.common.physical_server_views import (
    PhysicalServerDetailsView,
    PhysicalServerManagePoliciesView,
    PhysicalServersView,
    PhysicalServerProvisionView,
    PhysicalServerTimelinesView
)
from cfme.exceptions import (
    ItemNotFound,
    StatsDoNotMatch,
    HostStatsNotContains,
    ProviderHasNoProperty
)
from cfme.modeling.base import BaseEntity, BaseCollection
from cfme.utils.appliance.implementations.ui import CFMENavigateStep, navigate_to, navigator
from cfme.utils.log import logger
from cfme.utils.pretty import Pretty
from cfme.utils.providers import get_crud_by_name
from cfme.utils.update import Updateable
from cfme.utils.varmeth import variable
from cfme.utils.wait import wait_for


@attr.s
class PhysicalServer(BaseEntity, Updateable, Pretty, PolicyProfileAssignable, Taggable):
    """Model of an Physical Server in cfme.

    Args:
        name: Name of the physical server.
        hostname: hostname of the physical server.
        ip_address: The IP address as a string.
        custom_ident: The custom identifiter.

    Usage:

        myhost = PhysicalServer(name='vmware')
        myhost.create()

    """
    pretty_attrs = ['name', 'hostname', 'ip_address', 'custom_ident']

    name = attr.ib()
    provider = attr.ib(default=None)
    hostname = attr.ib(default=None)
    ip_address = attr.ib(default=None)
    custom_ident = attr.ib(default=None)
    db_id = None
    mgmt_class = LenovoSystem

    INVENTORY_TO_MATCH = ['power_state']
    STATS_TO_MATCH = ['cores_capacity', 'memory_capacity']

    def load_details(self, refresh=False):
        """To be compatible with the Taggable and PolicyProfileAssignable mixins.

        Args:
            refresh (bool): Whether to perform the page refresh, defaults to False
        """
        view = navigate_to(self, "Details")
        if refresh:
            view.browser.refresh()
            view.flush_widget_cache()

    def _execute_button(self, button, option, handle_alert=False):
        view = navigate_to(self, "Details")
        view.toolbar.custom_button(button).item_select(option, handle_alert=handle_alert)
        return view

    def _execute_action_button(self, button, option, handle_alert=True, **kwargs):
        target = kwargs.get("target", None)
        provider = kwargs.get("provider", None)
        desired_state = kwargs.get("desired_state", None)
        timeout = kwargs.get("timeout", 300)
        delay = kwargs.get("delay", 10)

        view = self._execute_button(button, option, handle_alert=handle_alert)

        if desired_state:
            self.wait_for_state_change(desired_state, target, provider, view, timeout, delay)
        elif handle_alert:
            wait_for(
                lambda: view.flash.is_displayed,
                message="Wait for the handle alert to appear...",
                num_sec=5,
                delay=2
            )

    def power_on(self, **kwargs):
        self._execute_action_button("Power", "Power On", **kwargs)

    def power_off(self, **kwargs):
        self._execute_action_button("Power", "Power Off", **kwargs)

    def power_off_now(self, **kwargs):
        self._execute_action_button("Power", "Power Off Immediately", **kwargs)

    def restart(self, **kwargs):
        self._execute_action_button("Power", "Restart", **kwargs)

    def restart_now(self, **kwargs):
        self._execute_action_button("Power", "Restart Immediately", **kwargs)

    def restart_to_sys_setup(self, **kwargs):
        self._execute_action_button("Power", "Restart to System Setup", **kwargs)

    def restart_management_controller(self, wait_restart_bmc=False, **kwargs):
        self._execute_action_button("Power", "Restart Management Controller",
                                    **kwargs)
        if wait_restart_bmc:
            self._wait_restart_bmc()

    def refresh(self, provider, handle_alert=False):
        last_refresh = provider.last_refresh_date()
        self._execute_button("Configuration", "Refresh Relationships and Power States",
                             handle_alert)
        wait_for(
            lambda: last_refresh != provider.last_refresh_date(),
            message="Wait for the server to be refreshed...",
            num_sec=300,
            delay=30
        )

    def turn_on_loc_led(self, **kwargs):
        self._execute_action_button('Identify', 'Turn On LED', **kwargs)

    def turn_off_loc_led(self, **kwargs):
        self._execute_action_button('Identify', 'Turn Off LED', **kwargs)

    def blink_loc_led(self, **kwargs):
        self._execute_action_button('Identify', 'Blink LED', **kwargs)

    @variable(alias='ui')
    def power_state(self):
        view = navigate_to(self, "Details")
        return view.entities.power_management.get_text_of("Power State")

    @variable(alias='ui')
    def location_led_state(self):
        view = navigate_to(self, "Details")
        return view.entities.properties.get_text_of("Identify LED State")

    @variable(alias='ui')
    def cores_capacity(self):
        view = navigate_to(self, "Details")
        return view.entities.properties.get_text_of("CPU total cores")

    @variable(alias='ui')
    def memory_capacity(self):
        view = navigate_to(self, "Details")
        return view.entities.properties.get_text_of("Total memory (mb)")

    def wait_for_state_change(self, desired_state, target, provider, view, timeout=300, delay=10):
        """Wait for PhysicalServer to come to desired state. This function waits just the needed amount of
           time thanks to wait_for.

        Args:
            desired_state (str): 'on' or 'off'
            target (str): The name of the method that most be used to compare with the desired_state
            view (object): The view that most be refreshed to verify if the value was changed
            provider (object): 'LenovoProvider'
            timeout (int): Specify amount of time (in seconds) to wait until TimedOutError is raised
            delay (int): Specify amount of time (in seconds) to repeat each time.
        """

        def _is_state_changed():
            self.refresh(provider, handle_alert=True)
            view.browser.refresh()
            return desired_state == getattr(self, target)()

        wait_for(_is_state_changed, num_sec=timeout, delay=delay)

    @property
    def exists(self):
        """Checks if the physical_server exists in the UI.

        Returns: :py:class:`bool`
        """
        view = navigate_to(self.parent, "All")
        try:
            view.entities.get_entity(name=self.name, surf_pages=True)
        except ItemNotFound:
            return False
        else:
            return True

    @cached_property
    def get_db_id(self):
        if self.db_id is None:
            self.db_id = self.appliance.physical_server_id(self.name)
            return self.db_id
        else:
            return self.db_id

    def wait_to_appear(self):
        """Waits for the server to appear in the UI."""
        view = navigate_to(self.parent, "All")
        logger.info("Waiting for the server to appear...")
        wait_for(
            lambda: self.exists,
            message="Wait for the server to appear",
            num_sec=1000,
            fail_func=view.browser.refresh
        )

    def wait_for_delete(self):
        """Waits for the server to remove from the UI."""
        view = navigate_to(self.parent, "All")
        logger.info("Waiting for the server to delete...")
        wait_for(
            lambda: not self.exists,
            message="Wait for the server to disappear",
            num_sec=500,
            fail_func=view.browser.refresh
        )

    def _wait_restart_bmc(self, delay=5, num_sec=300, verify_ssl=False):
        url = "https://{}".format(self.ip_address)

        def _send_request():
            try:
                return requests.get(url, verify=verify_ssl).ok
            except requests.exceptions.ConnectionError:
                return False

        wait_for(
            lambda: not _send_request(),
            message="Wait for the BMC to stop...",
            num_sec=num_sec,
            delay=delay
        )

        wait_for(
            _send_request,
            message="Wait for the BMC to start...",
            num_sec=num_sec,
            delay=delay
        )

    def validate_stats(self, ui=False):
        """ Validates that the detail page matches the physical server's information.

        This method logs into the provider using the mgmt_system interface and collects
        a set of statistics to be matched against the UI. An exception will be raised
        if the stats retrieved from the UI do not match those retrieved from wrapanapi.
        """

        # Make sure we are on the physical server detail page
        if ui:
            self.load_details()

        # Retrieve the client and the stats and inventory to match
        client = self.provider.mgmt
        stats_to_match = self.STATS_TO_MATCH
        inventory_to_match = self.INVENTORY_TO_MATCH

        # Retrieve the stats and inventory from wrapanapi
        server_stats = client.stats(*stats_to_match, requester=self)
        server_inventory = client.inventory(*inventory_to_match, requester=self)

        # Refresh the browser
        if ui:
            self.browser.selenium.refresh()

        # Verify that the stats retrieved from wrapanapi match those retrieved
        # from the UI
        for stat in stats_to_match:
            try:
                cfme_stat = int(getattr(self, stat)(method='ui' if ui else None))
                server_stat = int(server_stats[stat])

                if server_stat != cfme_stat:
                    msg = "The {} stat does not match. (server: {}, server stat: {}, cfme stat: {})"
                    raise StatsDoNotMatch(msg.format(stat, self.name, server_stat, cfme_stat))
            except KeyError:
                raise HostStatsNotContains(
                    "Server stats information does not contain '{}'".format(stat))
            except AttributeError:
                raise ProviderHasNoProperty("Provider does not know how to get '{}'".format(stat))

        # Verify that the inventory retrieved from wrapanapi match those retrieved
        # from the UI
        for inventory in inventory_to_match:
            try:
                cfme_inventory = getattr(self, inventory)(method='ui' if ui else None)
                server_inventory = server_inventory[inventory]

                if server_inventory != cfme_inventory:
                    msg = "The {} inventory does not match. (server: {}, server inventory: {}, " \
                          "cfme inventory: {})"
                    raise StatsDoNotMatch(msg.format(inventory, self.name, server_inventory,
                                                     cfme_inventory))
            except KeyError:
                raise HostStatsNotContains(
                    "Server inventory information does not contain '{}'".format(inventory))
            except AttributeError:
                msg = "Provider does not know how to get '{}'"
                raise ProviderHasNoProperty(msg.format(inventory))


@attr.s
class PhysicalServerCollection(BaseCollection):
    """Collection object for the :py:class:`cfme.infrastructure.host.PhysicalServer`."""

    ENTITY = PhysicalServer

    def select_entity_rows(self, physical_servers):
        """ Select all physical server objects """
        physical_servers = list(physical_servers)
        checked_physical_servers = list()
        view = navigate_to(self, 'All')

        for physical_server in physical_servers:
            view.entities.get_entity(name=physical_server.name, surf_pages=True).check()
            checked_physical_servers.append(physical_server)
        return view

    def all(self, provider):
        """returning all physical_servers objects"""
        physical_server_table = self.appliance.db.client['physical_servers']
        ems_table = self.appliance.db.client['ext_management_systems']
        network_table = self.appliance.db.client['networks']
        hardware_table = self.appliance.db.client['hardwares']
        computer_sys_table = self.appliance.db.client['computer_systems']
        physical_server_query = (
            self.appliance.db.client.session
                .query(physical_server_table.name, ems_table.name,
                       network_table.ipaddress)
                .join(ems_table, physical_server_table.ems_id == ems_table.id)
                .join(computer_sys_table,
                      physical_server_table.id == computer_sys_table.managed_entity_id)
                .join(hardware_table, computer_sys_table.id == hardware_table.computer_system_id)
                .join(network_table, hardware_table.id == network_table.id))
        provider = None

        if self.filters.get('provider'):
            provider = self.filters.get('provider')
            physical_server_query = physical_server_query.filter(ems_table.name == provider.name)
        physical_servers = []
        for name, ems_name, ip_address in physical_server_query.all():
            physical_servers.append(self.instantiate(name=name, ip_address=ip_address,
                                    provider=provider or get_crud_by_name(ems_name)))
        return physical_servers

    def find_by(self, provider, ph_name):
        """returning all physical_servers objects"""
        physical_server_table = self.appliance.db.client['physical_servers']
        ems_table = self.appliance.db.client['ext_management_systems']
        network_table = self.appliance.db.client['networks']
        hardware_table = self.appliance.db.client['hardwares']
        computer_sys_table = self.appliance.db.client['computer_systems']
        physical_server_query = (
            self.appliance.db.client.session
                .query(physical_server_table.name, ems_table.name,
                       network_table.ipaddress)
                .join(ems_table, physical_server_table.ems_id == ems_table.id)
                .join(computer_sys_table,
                      physical_server_table.id == computer_sys_table.managed_entity_id)
                .join(hardware_table, computer_sys_table.id == hardware_table.computer_system_id)
                .join(network_table, hardware_table.id == network_table.id))
        provider = None

        if self.filters.get('provider'):
            provider = self.filters.get('provider')
            physical_server_query = physical_server_query.filter(ems_table.name == provider.name)

        for name, ems_name, ip_address in physical_server_query.all():
            if ph_name == name:
                return self.instantiate(name=name,
                                        ip_address=ip_address,
                                        provider=provider or get_crud_by_name(ems_name))

    def power_on(self, *physical_servers):
        view = self.select_entity_rows(physical_servers)
        view.toolbar.power.item_select("Power On", handle_alert=True)

    def power_off(self, *physical_servers):
        view = self.select_entity_rows(physical_servers)
        view.toolbar.power.item_select("Power Off", handle_alert=True)


@navigator.register(PhysicalServerCollection)
class All(CFMENavigateStep):
    VIEW = PhysicalServersView
    prerequisite = NavigateToAttribute("appliance.server", "LoggedIn")

    def step(self):
        self.prerequisite_view.navigation.select("Compute", "Physical Infrastructure", "Servers")


@navigator.register(PhysicalServer)
class Details(CFMENavigateStep):
    VIEW = PhysicalServerDetailsView
    prerequisite = NavigateToAttribute("parent", "All")

    def step(self):
        self.prerequisite_view.entities.get_entity(name=self.obj.name, surf_pages=True).click()


@navigator.register(PhysicalServer)
class ManagePolicies(CFMENavigateStep):
    VIEW = PhysicalServerManagePoliciesView
    prerequisite = NavigateToSibling("Details")

    def step(self):
        self.prerequisite_view.toolbar.policy.item_select("Manage Policies")


@navigator.register(PhysicalServer)
class Provision(CFMENavigateStep):
    VIEW = PhysicalServerProvisionView
    prerequisite = NavigateToSibling("Details")

    def step(self):
        self.prerequisite_view.toolbar.lifecycle.item_select("Provision Physical Server")


@navigator.register(PhysicalServer)
class Timelines(CFMENavigateStep):
    VIEW = PhysicalServerTimelinesView
    prerequisite = NavigateToSibling("Details")

    def step(self):
        self.prerequisite_view.toolbar.monitoring.item_select("Timelines")
