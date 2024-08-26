#!/usr/bin/env python
import requests
import urllib3
import argparse
import json
import yaml
from pprint import pprint
import os
from dotenv import load_dotenv

from vmware.vapi.vsphere.client import create_vsphere_client

from com.vmware.vcenter.guest_client import (CustomizationSpec,
                                             CloudConfiguration,
                                             CloudinitConfiguration,
                                             ConfigurationSpec,
                                             GlobalDNSSettings
                                             )


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
        self.metadata = None
        self.userdata = None
        # get customization config
        self.jsonCfgPath = os.path.join(os.path.dirname(
            os.path.realpath(__file__)),
            'aio_metadata.json')
        self.yamlCfgPath = os.path.join(os.path.dirname(
            os.path.realpath(__file__)),
            'aio_metadata.yaml')
        self.userDataPath = os.path.join(os.path.dirname(
            os.path.realpath(__file__)),
            'aio_userdata')
        self.specsAdded = []

    def createCloudinitDataSpec(self, specName, specDesc):
        """
        create a cloud-init data customizationSpec
        """
        print('------create 1 linux cloud-init data CustomizationSpec-------')
        cloudinitConfig = CloudinitConfiguration(metadata=self.metadata,
                                                 userdata=self.userdata)
        cloudConfig =\
            CloudConfiguration(cloudinit=cloudinitConfig,
                               type=CloudConfiguration.Type('CLOUDINIT'))
        configSpec = ConfigurationSpec(cloud_config=cloudConfig)
        globalDnsSettings = GlobalDNSSettings()
        adapterMappingList = []
        customizationSpec =\
            CustomizationSpec(configuration_spec=configSpec,
                              global_dns_settings=globalDnsSettings,
                              interfaces=adapterMappingList)
        createSpec = self.specs_svc.CreateSpec(name=specName,
                                               description=specDesc,
                                               spec=customizationSpec)
        self.specs_svc.create(spec=createSpec)
        print('{} has been created'.format(specName))
        print('-------------------------------------------------------------')

    def createSpecWithMetadataInJson(self):
        """
        create a linux cloud-init data customizationSpec with metadata in json
        format and userdata
        """
        with open(self.userDataPath, "r") as fp:
            self.userdata = fp.read().rstrip('\n')
        with open(self.jsonCfgPath, "r") as fp:
            self.metadata = fp.read().rstrip('\n')
            data = json.loads(self.metadata)
            self.createCloudinitDataSpec('cloud-init-' + data['local-hostname'],
                                         'linux cloud-init data customization spec for ' +
                                         data['local-hostname'])

    def createSpecWithMetadataInYaml(self):
        """
        create a linux cloud-init data customizationSpec with metadata in json
        format and userdata
        """
        with open(self.userDataPath, "r") as fp:
            self.userdata = fp.read().rstrip('\n')
        with open(self.yamlCfgPath, "r") as fp:
            self.metadata = fp.read().rstrip('\n')
            data = yaml.safe_load(self.metadata)
            self.createCloudinitDataSpec('cloud-init-' + data['local-hostname'],
                                         'linux cloud-init data customization spec for ' +
                                         data['local-hostname'])

    def listCustomizationSpecs(self):
        """
        List CustomizationSpecs present in vc server
        """
        print("------------list--------------")
        print("List Of  CustomizationSpecs:")
        list_of_specs = self.specs_svc.list()
        self.specCount = len(list_of_specs)
        pprint(list_of_specs)


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
    parser = argparse.ArgumentParser(description='AIO Cloud-init Customization Spec Manager')
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
        myCustSpecMgr.createSpecWithMetadataInJson()
        # myCustSpecMgr.createSpecWithMetadataInYaml()
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
