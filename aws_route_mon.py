#!/usr/bin/python
'''aws_nat_mon.py

This script checks for an active route on an AWS routing table.  If the route
is found to be non-active, then the route has its' next hop replaced.

#-------------------------------------------------------------------------------
# Copyright 2015:
# - Australian Postal Corporation
# - Odecee Pty Ltd
# - Philip Jay
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------------------
'''

import boto.exception
import boto.vpc
import logging
import optparse
import random
import sys
import time
import traceback


class EXIT_CODES(object): # pylint: disable=invalid-name,too-few-public-methods
    '''Class to provide an enum of exit codes for aws_nat_mon.py'''
    vpc_connection_failed = 110 # pylint: disable=bad-whitespace
    ec2_reponse_error     = 111 # pylint: disable=bad-whitespace
    route_table_not_found = 112 # pylint: disable=bad-whitespace
    route_not_found       = 113 # pylint: disable=bad-whitespace
    replace_route_failed  = 114 # pylint: disable=bad-whitespace
    create_route_failed   = 115 # pylint: disable=bad-whitespace


class AwsNatMon(object): # pylint: disable=too-many-instance-attributes
    '''Class to provide the majority of functionality to aws_nat_mon.py'''

    def __init__(self):
        self.BACKOFF_MIN = 1 # pylint: disable=invalid-name
        self.BACKOFF_MAX = 45 # pylint: disable=invalid-name

        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)

        self.parse_args()

        try:
            self.conn = boto.vpc.connect_to_region(
                self.aws_region,
                profile_name=self.aws_profile,
                aws_access_key_id=self.aws_access_id,
                aws_secret_access_key=self.aws_access_key,
            )
        except Exception, err: #pylint: disable=broad-except
            self.log.error("Exception occurred when "
                           "connecting to the AWS VPC API: %s",
                           str(err),
                          )
            self.log.error(traceback.format_exc())
            sys.exit(EXIT_CODES.vpc_connection_failed)

    def parse_args(self):
        '''Parse the args'''
        parser = optparse.OptionParser(
            usage="%prog [-r route table] [-i interface] [-c cidr] "
            "[-R aws region] [-P aws profile] [-I aws id] [-K aws key]"
        )
        parser.add_option("-r", "--route-table",
                          default=None,
                          help="AWS route table ID",
                         )
        parser.add_option("-i", "--interface",
                          default=None,
                          help="AWS interface ID to use as next-hop"
                         )
        parser.add_option("-c", "--cidr",
                          default='0.0.0.0/0',
                          help="CIDR to check in the route table (will "
                          "be created if it doesn't exist) - Default: "
                          "%default",
                         )
        parser.add_option("-R", "--region",
                          default=None,
                          help="AWS region to connect to"
                         )
        parser.add_option("-P", "--profile",
                          default=None,
                          help="Boto profile to use"
                         )
        parser.add_option("-I", "--access-id",
                          default=None,
                          help="AWS access ID to use"
                         )
        parser.add_option("-K", "--access-key",
                          default=None,
                          help="AWS access key to use"
                         )
        parser.add_option("-L", "--logging-to",
                          default='console',
                          help="Send logs to: console, or, syslog"
                         )
        (options, pargs) = parser.parse_args() # pylint: disable=unused-variable

        # Validate
        if (options.route_table is None) or \
           (options.interface is None) or \
           (options.region is None):
            parser.error(
                "Please specify mandatory options:\n"
                "- the route table\n"
                "- the interface\n"
                "- the aws region"
            )

        # Logging
        if options.logging_to == 'console':
            self.log.addHandler(logging.StreamHandler())
        elif options.logging_to == 'syslog':
            self.log.addHandler(
                logging.handlers.SysLogHandler(address='/dev/log')
            )
        else:
            parser.error("Logging to valid options are: 'console' or 'syslog'")

        # Variables
        self.route_table = options.route_table
        self.interface = options.interface
        self.cidr = options.cidr
        self.aws_region = options.region
        self.aws_profile = options.profile
        self.aws_access_id = options.access_id
        self.aws_access_key = options.access_key

    def get_route(self):
        '''Return the route object to be checked'''
        try:
            table = self.conn.get_all_route_tables(
                route_table_ids=[self.route_table,],
            )[0]
        except boto.exception.EC2ResponseError, err:
            self.log.error("Exception occurred when "
                           "getting route table %s: %s",
                           self.route_table,
                           str(err),
                          )
            self.log.error(traceback.format_exc())
            sys.exit(EXIT_CODES.ec2_reponse_error)
        except IndexError, err:
            self.log.error("Exception occurred when "
                           "getting route table %s: %s",
                           self.route_table,
                           str(err),
                          )
            self.log.error(traceback.format_exc())
            sys.exit(EXIT_CODES.route_table_not_found)

        found_route = None
        for route in table.routes:
            if route.destination_cidr_block == self.cidr:
                found_route = route

        return found_route

    def create_route(self):
        '''Create an entry in the route table for the CIDR with the interface
        as next hop'''
        try:
            return self.conn.create_route(
                self.route_table,
                self.cidr,
                interface_id=self.interface,
            )
        except boto.exception.EC2ResponseError, err:
            self.log.error("Exception occurred when "
                           "creating the default route on "
                           "table %s with interface %s: %s",
                           self.route_table,
                           self.interface,
                           str(err),
                          )
            self.log.error(traceback.format_exc())
            sys.exit(EXIT_CODES.ec2_reponse_error)

    def replace_route(self):
        '''Replace the route with interface_id as its' next hop'''
        try:
            return self.conn.replace_route(
                self.route_table,
                self.cidr,
                interface_id=self.interface,
            )
        except boto.exception.EC2ResponseError, err:
            self.log.error("Exception occurred when "
                           "replacing the default route in "
                           "table %s with interface %s: %s",
                           self.route_table,
                           self.interface,
                           str(err),
                          )
            self.log.error(traceback.format_exc())
            sys.exit(EXIT_CODES.ec2_reponse_error)

    def main(self):
        '''The main business logic function'''

        route_created = False
        route_replaced = False

        route = self.get_route()
        if route is None:
            # boot-strap issue, route doesn't exist on table: create it
            backoff = random.randint(self.BACKOFF_MIN, self.BACKOFF_MAX)
            self.log.debug("Route %s not found in route table %s, "
                           "rechecking in %d seconds",
                           self.cidr,
                           self.route_table,
                           backoff,
                          )
            time.sleep(backoff)
            route = self.get_route()
            if route is None:
                self.log.warning("Route %s not found in route table %s, creating "
                                 "route with next hop set to interface %s",
                                 self.cidr,
                                 self.route_table,
                                 self.interface,
                                )
                if not self.create_route():
                    self.log.error("Creating route %s on route table %s "
                                   "with interface %s failed",
                                   self.cidr,
                                   self.route_table,
                                   self.interface,
                                  )
                    sys.exit(EXIT_CODES.create_route_failed)
                route_created = True

        if route_created:
            self.log.info("Route with next-hop set to interface %s in "
                          "route table %s created",
                          self.interface,
                          self.route_table,
                         )
            sys.exit(0)

        if route.instance_id is None:
            # uh-oh! route doesn't have a machine attached
            # back-off a random about of time & check once more
            backoff = random.randint(self.BACKOFF_MIN, self.BACKOFF_MAX)
            self.log.debug("Route %s for route table %s has no instance "
                           "attached, rechecking in %d seconds",
                           self.cidr,
                           self.route_table,
                           backoff,
                          )
            time.sleep(backoff)

            route = self.get_route()
            if route.instance_id is None:
                # okay, the route still doesn't have a machine attached
                # time to claim the route
                self.log.warning("Route %s for route table %s has no instance "
                                 "attached, replacing next hop with interface %s",
                                 self.cidr,
                                 self.route_table,
                                 self.interface,
                                )
                if not self.replace_route():
                    self.log.error("Replacing route next hop on route "
                                   "table %s with interface %s failed",
                                   self.route_table,
                                   self.interface,
                                  )
                    sys.exit(EXIT_CODES.replace_route_failed)
                route_replaced = True

        if route_replaced:
            self.log.info("Route next-hop for route table %s replaced "
                          "with interface %s",
                          self.route_table,
                          self.interface,
                         )
            sys.exit(0)

        self.log.debug("Route %s on route table %s is okay, no action "
                       "taken",
                       self.cidr,
                       self.route_table,
                      )
        sys.exit(0)


if __name__ == '__main__':
    ANM = AwsNatMon()
    ANM.main()
