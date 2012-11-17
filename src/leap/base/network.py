# -*- coding: utf-8 -*-
from __future__ import (print_function)
import logging
import threading

from leap.eip import config as eipconfig
from leap.base.checks import LeapNetworkChecker
from leap.base.constants import ROUTE_CHECK_INTERVAL
from leap.base.exceptions import TunnelNotDefaultRouteError
from leap.util.misc import null_check
from leap.util.coroutines import (launch_thread, process_events)

from time import sleep

logger = logging.getLogger(name=__name__)

#EVENTS OF NOTE
EVENT_CONNECT_REFUSED = "[ECONNREFUSED]: Connection refused (code=111)"


class NetworkCheckerThread(object):
    """
    Manages network checking thread that makes sure we have a working network
    connection.
    """
    def __init__(self, *args, **kwargs):
        self.status_signals = kwargs.pop('status_signals', None)
        #self.watcher_cb = kwargs.pop('status_signals', None)
        self.error_cb = kwargs.pop(
            'error_cb',
            lambda exc: logger.error("%s", exc.message))
        self.shutdown = threading.Event()

        # XXX get provider passed here
        provider = kwargs.pop('provider', None)
        null_check(provider, 'provider')

        eipconf = eipconfig.EIPConfig(domain=provider)
        eipconf.load()
        eipserviceconf = eipconfig.EIPServiceConfig(domain=provider)
        eipserviceconf.load()

        gw = eipconfig.get_eip_gateway(
            eipconfig=eipconf,
            eipserviceconfig=eipserviceconf)
        self.checker = LeapNetworkChecker(
            provider_gw=gw)

    def start(self):
        self.process_handle = self._launch_recurrent_network_checks(
            (self.error_cb,))

    def stop(self):
        self.shutdown.set()
        logger.debug("network checked stopped.")

    def run_checks(self):
        pass

    def parse_log(self, log):
        for line in log:
            if EVENT_CONNECT_REFUSED in line:
                #fire cb to stop openvpn server
                pass

    #private methods

    #here all the observers in fail_callbacks expect one positional argument,
    #which is exception so we can try by passing a lambda with logger to
    #check it works.
    def _network_checks_thread(self, fail_callbacks):
        #TODO: replace this with waiting for a signal from openvpn
        while True:
            try:
                self.checker.check_tunnel_default_interface()
                break
            except TunnelNotDefaultRouteError:
                # XXX ??? why do we sleep here???
                # aa: If the openvpn isn't up and running yet,
                # let's give it a moment to breath.
                sleep(1)

        fail_observer_dict = dict(((
            observer,
            process_events(observer)) for observer in fail_callbacks))
        while not self.shutdown.is_set():
            try:
                self.checker.check_tunnel_default_interface()
                self.checker.check_internet_connection()
                sleep(ROUTE_CHECK_INTERVAL)
            except Exception as exc:
                for obs in fail_observer_dict:
                    fail_observer_dict[obs].send(exc)
                sleep(ROUTE_CHECK_INTERVAL)
        #reset event
        self.shutdown.clear()

    def _launch_recurrent_network_checks(self, fail_callbacks):
        #we need to wrap the fail callback in a tuple
        watcher = launch_thread(
            self._network_checks_thread,
            (fail_callbacks,))
        return watcher
