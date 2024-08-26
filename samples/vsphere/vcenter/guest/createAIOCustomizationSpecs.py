#!/usr/bin/env python
import requests
import urllib3
import argparse
from pprint import pprint
import configparser
import os
from dotenv import load_dotenv

from vmware.vapi.vsphere.client import create_vsphere_client

from com.vmware.vcenter.guest_client import (CustomizationSpec,
                                             HostnameGenerator,
                                             LinuxConfiguration,
                                             ConfigurationSpec,
                                             GlobalDNSSettings,
                                             AdapterMapping,
                                             IPSettings,
                                             Ipv4,
                                             Ipv6,
                                             Ipv6Address)


class AioCustomizationSpecManager(object):
    """
    Demonstrates create/list/get/set/delete customizationSpecs in vCenter
    Sample Prerequisites: 1 vcenter, no ESXi nor VM needed
    """

    def __init__(self):
        load_dotenv()
        session = requests.session()

        # Disable cert verification for demo purpose.
        # This is not recommended in a production environment.
        session.verify = False

        # Disable the secure connection warning for demo purpose.
        # This is not recommended in a production environment.
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.client = create_vsphere_client(server=os.getenv("VCENTER"),
                                            username=os.getenv("USERNAME"),
                                            password=os.getenv("PASSWORD"),
                                            session=session)
        self.specs_svc = self.client.vcenter.guest.CustomizationSpecs
        # get customization config
        self.config = configparser.ConfigParser()
        self.linCfgPath = os.path.join(os.path.dirname(
                                       os.path.realpath(__file__)),
                                       'aioSpec.cfg')
        self.specsAdded = []

    # common method to parse specInfo for linux/windows spec
    def parseSpecInfo(self):
        self.specName = self.config['CREATESPEC']['specName']
        self.specDesc = self.config['CREATESPEC']['specDesc']

    # common method to parse network cfg for linux/windows spec
    def parseNetwork(self):
        # parse macAddress
        self.macAddress = self.config['NETWORK'].get('macAddress')
        # parse ipv4
        self.ipv4Type = self.config['NETWORK'].get('ipv4Type', 'DHCP')
        if self.ipv4Type == 'STATIC':
            self.ipv4_prefix = self.config['NETWORK'].getint('ipv4_prefix')
            self.ipv4_gateways = self.config['NETWORK'].get('ipv4_gateways')
            if self.ipv4_gateways is not None:
                self.ipv4_gateways = self.ipv4_gateways.split(',')
            self.ipv4_ip = self.config['NETWORK'].get('ipv4_ip')
        elif (self.ipv4Type == 'DHCP' or
              self.ipv4Type == 'USER_INPUT_REQUIRED'):
            self.ipv4_prefix = None
            self.ipv4_gateways = None
            self.ipv4_ip = None
        else:
            raise Exception('Wrong ipv4Type "{}"'.format(self.ipv4Type))
        # parse ipv6
        self.ipv6Type = self.config['NETWORK'].get('ipv6Type')
        if self.ipv6Type == 'STATIC':
            self.ipv6_prefix = self.config['NETWORK'].getint('ipv6_prefix')
            self.ipv6_gateways = self.config['NETWORK'].get('ipv6_gateways')
            if self.ipv6_gateways is not None:
                self.ipv6_gateways = self.ipv6_gateways.split(',')
            self.ipv6_ip = self.config['NETWORK'].get('ipv6_ip')
        elif ((self.ipv6Type is None) or (self.ipv4Type == 'DHCP') or
                (self.ipv4Type == 'USER_INPUT_REQUIRED')):
            self.ipv6_prefix = None
            self.ipv6_ip = None
            self.ipv6_gateways = None
        else:
            raise Exception('Wrong ipv6Type "{}"'.format(self.ipv6Type))

    # common method to parse hostname cfg for linux/windows spec
    def parseHostname(self):
        # parse hostname generator type
        self.hostnameType =\
            self.config['HOSTNAME'].get('hostnameGeneratorType',
                                        'VIRTUAL_MACHINE')
        if (self.hostnameType == 'VIRTUAL_MACHINE' or
           self.hostnameType == 'USER_INPUT_REQUIRED'):
            self.prefix = None
            self.fixedName = None
        elif self.hostnameType == 'PREFIX':
            self.prefix = self.config['HOSTNAME'].get('prefix')
            self.fixedName = None
        elif self.hostnameType == 'FIXED':
            self.fixedName = self.config['HOSTNAME'].get('fixedName')
            self.prefix = None
        else:
            raise Exception('Wrong hostnameGeneratorType "{}"'.format(
                            self.hostnameType))

    # common method to parse DNS cfg for linux/windows spec
    def parseDns(self):
        self.globalDnsServers = self.config['DNS'].get('dnsServers')
        if self.globalDnsServers is not None:
            self.globalDnsServers = self.globalDnsServers.split(',')
        self.globalDnsSuffixs = self.config['DNS'].get('dnsSuffixs')
        if self.globalDnsSuffixs is not None:
            self.globalDnsSuffixs = self.globalDnsSuffixs.split(',')

    def parseLinuxCfg(self):
        self.config.read(self.linCfgPath)
        self.parseSpecInfo()
        self.linSpecName = self.specName
        self.parseNetwork()
        self.parseHostname()
        self.domainName = self.config['LINUXCONFIG'].get('domainName')
        self.timezone = self.config['LINUXCONFIG'].get('timezone')
        self.script_text = self.config['LINUXCONFIG'].get('script_text')
        self.parseDns()


    def listCustomizationSpecs(self):
        """
        List CustomizationSpecs present in vc server
        """
        print("------------list--------------")
        print("List Of  CustomizationSpecs:")
        list_of_specs = self.specs_svc.list()
        self.specCount = len(list_of_specs)
        pprint(list_of_specs)

    def createLinuxSpec(self):
        print("------------create 1 linux Customizationpec----------------")
        self.parseLinuxCfg()
        computerName = HostnameGenerator(prefix=self.prefix,
                                         fixed_name=self.fixedName,
                                         type=HostnameGenerator.Type(
                                             self.hostnameType))
        spec_linuxConfig = LinuxConfiguration(domain=self.domainName,
                                              hostname=computerName,
                                              time_zone=self.timezone,
                                              script_text=self.script_text)
        spec_configSpec = ConfigurationSpec(linux_config=spec_linuxConfig)
        # AdapterMapping
        ipv4Cfg = Ipv4(type=Ipv4.Type(self.ipv4Type), prefix=self.ipv4_prefix,
                       gateways=self.ipv4_gateways, ip_address=self.ipv4_ip)
        if self.ipv6Type is not None:
            ipv6addr = [Ipv6Address(prefix=self.ipv6_prefix,
                                    ip_address=self.ipv6_ip)]
            ipv6Cfg = Ipv6(gateways=self.ipv6_gateways, ipv6=ipv6addr,
                           type=Ipv6.Type(self.ipv6Type))
        else:
            ipv6Cfg = None
        ipSettings = IPSettings(windows=None, ipv4=ipv4Cfg, ipv6=ipv6Cfg)
        adapterMappingList = [AdapterMapping(adapter=ipSettings,
                                             mac_address=self.macAddress)]
        # dns_settings
        dns_settings = GlobalDNSSettings(dns_servers=self.globalDnsServers,
                                         dns_suffix_list=self.globalDnsSuffixs)
        # CreateSpec
        linspec_spec = CustomizationSpec(configuration_spec=spec_configSpec,
                                         interfaces=adapterMappingList,
                                         global_dns_settings=dns_settings)
        lin_create_spec = self.specs_svc.CreateSpec(name=self.specName,
                                                    description=self.specDesc,
                                                    spec=linspec_spec)
        # svc Create
        self.specs_svc.create(spec=lin_create_spec)
        # append it to existing list, for delete and cleanup
        self.specsAdded.append(self.specName)
        # list after create
        self.listCustomizationSpecs()
        print("----------------------------")


    def getSpec(self, name):
        print("-----------Get existing Spec------------")
        # Get created specs, modify timezone and description of the linSpec
        linSpec = self.specs_svc.get(name)
        pprint(linSpec)
        print("----------------------------")

    def deleteSpec(self, name):
        print("-----------Delete created spec for cleanup------------")
        print("-----------before delete------------")
        self.listCustomizationSpecs()
        print("-----------Spec to be delete------------")
        linSpec = self.specs_svc.get(name)
        pprint(linSpec)
        self.specs_svc.delete(name)
        # list again, there should be []
        print("-----------after delete------------")
        self.listCustomizationSpecs()
        print("----------------------------")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AIO Customization Spec Manager')
    parser.add_argument('-C', '--create-spec', dest='create_spec', action='store_true', help='Create AIO Customization Spec')
    parser.set_defaults(create_spec=False)
    parser.add_argument('-L', '--list-spec', dest='list_spec', action='store_true', help='List AIO Customization Specs')
    parser.set_defaults(list_spec=False)
    parser.add_argument('-G', '--get-spec', dest='get_spec', action='store_true', help='Get AIO Customization Specs, please use -N to specify spec name')
    parser.set_defaults(get_spec=False)
    parser.add_argument('-D', '--delete-spec', dest='delete_spec', action='store_true', help='Delete AIO Customization Spec, please use -N to specify spec name')
    parser.set_defaults(delete_spec=False)
    parser.add_argument('-N', '--spec-name', dest='spec_name', default=None, help='Customization Spec Name')
    parser.set_defaults(delete_spec=False)
    args = parser.parse_args()
    myCustSpecMgr = AioCustomizationSpecManager()
    if args.list_spec:
        myCustSpecMgr.listCustomizationSpecs()
    elif args.create_spec:
        myCustSpecMgr.createLinuxSpec()
    elif args.get_spec:
        if args.spec_name is None:
            print("Please provide spec name to get")
            parser.print_help()
        else:
            myCustSpecMgr.getSpec(args.spec_name)
    elif args.delete_spec:
        if args.spec_name is None:
            print("Please provide spec name to delete")
            parser.print_help()
        else:
            myCustSpecMgr.deleteSpec(args.spec_name)
    else:
        parser.print_help()
