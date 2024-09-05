#!/usr/bin/env python
import requests
import urllib3
import argparse
import json
import yaml
from pprint import pprint
import os
from dotenv import load_dotenv

from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
import ssl


class AioSeedISOManager(object):
    """
    Demonstrates create/list/get/set/delete customizationSpecs in vCenter
    Sample Prerequisites: 1 vcenter, no ESXi nor VM needed
    """

    def __init__(self):
        load_dotenv()
        # Disable SSL certificate verification
        session = ssl._create_unverified_context()
        # Disable the secure connection warning for demo purpose.
        # This is not recommended in a production environment.
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.client = SmartConnect(host=os.getenv("VCENTER"),
                                    user=os.getenv("USERNAME"),
                                    pwd=os.getenv("PASSWORD"),
                                    sslContext=session)
        self.datacenter = None
        self.vm = None
        self.datestore = None
        self.iso_folder = os.getenv("FOLDER")
        self.iso_name = None

    def find_vm_by_name_recursive(self, folder, vm_name):
        """
        Recursively search for a VM by name in a folder and its subfolders.
        :param folder: The current folder or container being searched.
        :param vm_name: The name of the VM to search for.
        :return: The VM object if found, otherwise None.
        """
        for child in folder.childEntity:
            if isinstance(child, vim.VirtualMachine):
                # If the child is a VM, check its name
                if child.name == vm_name:
                    return child
            elif isinstance(child, vim.Folder):
                # If child is a folder, recursively search in the folder
                vm = self.find_vm_by_name_recursive(child, vm_name)
                if vm:
                    return vm
            elif isinstance(child, vim.Datacenter):
                # If child is a Data Center, recursively search in the Data Center
                vm = self.find_vm_by_name_recursive(child, vm_name)
                if vm:
                    return vm
        return None

    def createSeedISOAndAddToVM(self, vm_name, ip_addr):
        """
        create a seed iso of static IP configuration for the VM in datastiore and add it to VM
        """
        # call shell to delete existing seed iso
        os.system("rm -f seed.iso")

        # read meta-data file as yaml
        with open("meta-data.tmp", 'r') as stream:
            try:
                meta_data = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        meta_data['local-hostname'] = vm_name
        meta_data['instance-id'] = vm_name
        # write meta-data to file
        with open("meta-data", 'w') as stream:
            try:
                yaml.dump(meta_data, stream)
            except yaml.YAMLError as exc:
                print(exc)
        # read network-config file as yaml
        with open("network-config.sj", 'r') as stream:
            try:
                network_config = yaml.safe_load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        network_config['network']['ethernets']['ens192']['addresses'][0] = ip_addr+"/24"
        # write network-config to file
        with open("network-config", 'w') as stream:
            try:
                yaml.dump(network_config, stream)
            except yaml.YAMLError as exc:
                print(exc)
        # Call the shell script to create the seed iso
        os.system("genisoimage -output seed.iso -volid cidata -joliet -rock user-data meta-data network-config")

        # Retrieve content
        content = self.client.RetrieveContent()

        # check if VM exists
        for dc in content.rootFolder.childEntity:
            vm_folder = dc.vmFolder
            self.vm = self.find_vm_by_name_recursive(vm_folder, vm_name)
            if self.vm is not None:
                self.datacenter = dc
                break
        if self.vm is None:
            print("VM not found")
            Disconnect(self.client)
            exit(1)

        # Get the datastore by name
        datastore_name = os.getenv("DATASTORE")

        datastores = self.datacenter.datastoreFolder.childEntity
        for ds in datastores:
            if ds.name == datastore_name:
                self.datastore = ds
                break

        if self.datastore is None:
            print("Datastore not found")
            Disconnect(self.client)
            exit(1)

        # Construct the URL for the upload
        self.iso_name = vm_name + "_seed.iso"  # Name of the ISO file to upload

        # Example URL format:
        # https://<vcenter_ip>/folder/<upload_folder>/<iso_filename>?dcPath=<datacenter_name>&dsName=<datastore_name>
        url = f"https://{self.client._stub.host}/folder/{self.iso_folder}/{self.iso_name}?dcPath={self.datacenter.name}&dsName={datastore_name}"
        # pprint(url)

        # Read the ISO file content
        iso_file_path = "seed.iso"

        with open(iso_file_path, 'rb') as iso_file:
            headers = {
                'Content-Type': 'application/octet-stream'
            }
            response = requests.put(url, data=iso_file, headers=headers, verify=False,
                                    auth=(os.getenv("USERNAME"), os.getenv("PASSWORD")))

        if 200 <= response.status_code < 300:
            print("ISO file uploaded successfully.")
        else:
            print(f"Failed to upload ISO file. Status code: {response.status_code}, Response: {response.text}")

        # Check if the VM already has a CD/DVD drive
        cdrom_device = None

        for device in self.vm.config.hardware.device:
            if isinstance(device, vim.vm.device.VirtualCdrom):
                cdrom_device = device
                break

        # If the VM does not have a CD/DVD drive, create one
        if cdrom_device is None:
            controller = None
            for device in self.vm.config.hardware.device:
                if isinstance(device, vim.vm.device.VirtualIDEController):
                    controller = device
                    break

            if controller is None:
                print("No suitable IDE controller found.")
                Disconnect(self.client)
                exit(1)

            cdrom_spec = vim.vm.device.VirtualDeviceSpec()
            cdrom_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.add
            cdrom_spec.device = vim.vm.device.VirtualCdrom()
            cdrom_spec.device.backing = vim.vm.device.VirtualCdrom.IsoBackingInfo()
            cdrom_spec.device.controllerKey = controller.key
            cdrom_spec.device.unitNumber = 0
            cdrom_spec.device.deviceInfo = vim.Description()

            # Create a new device change specification for the CD-ROM
            dev_changes = []
            dev_changes.append(cdrom_spec)

            # Create a VM config spec to add the CD-ROM
            vm_config_spec = vim.vm.ConfigSpec()
            vm_config_spec.deviceChange = dev_changes

            # Reconfigure the VM
            task = self.vm.ReconfigVM_Task(vm_config_spec)
            while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
                pass

            if task.info.state == vim.TaskInfo.State.success:
                print("CD/DVD drive added successfully.")
                # Re-fetch the VM's hardware devices
                self.vm = content.searchIndex.FindByUuid(None, self.vm.config.uuid, True)
                for device in self.vm.config.hardware.device:
                    if isinstance(device, vim.vm.device.VirtualCdrom):
                        cdrom_device = device
                        break
            else:
                print("Failed to add CD/DVD drive.")
                Disconnect(self.client)
                exit(1)
        # Set the ISO file location on the datastore
        iso_path = f"[{datastore_name}] {self.iso_folder}/{self.iso_name}"

        # Create a specification to set the CD-ROM device to use the ISO file
        cdrom_spec = vim.vm.device.VirtualDeviceSpec()
        cdrom_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
        cdrom_spec.device = cdrom_device
        cdrom_spec.device.backing = vim.vm.device.VirtualCdrom.IsoBackingInfo()
        cdrom_spec.device.backing.fileName = iso_path

        # Create a VM config spec
        vm_config_spec = vim.vm.ConfigSpec()
        vm_config_spec.deviceChange = [cdrom_spec]

        # Apply the reconfiguration
        task = self.vm.ReconfigVM_Task(vm_config_spec)
        while task.info.state not in [vim.TaskInfo.State.success, vim.TaskInfo.State.error]:
            pass

        if task.info.state == vim.TaskInfo.State.success:
            print("ISO file mounted successfully.")
        else:
            print(f"Failed to mount ISO file. Error: {task.info.error}")

        # Disconnect from vCenter
        Disconnect(self.client)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create seed iso for AIO static IP configuration')
    parser.add_argument('-C', '--create-iso', dest='create_iso', action='store_true', help='Create AIO Customization Spec, please use -N to specify AIO VM name, -A to specify AIO VM IP Address')
    parser.set_defaults(create_spec=False)
    parser.add_argument('-N', '--vm-name', dest='vm_name', default=None, help='AIO VM name')
    parser.add_argument('-A', '--ip-addr', dest='ip_addr', default=None, help='AIO VM IP Address')
    args = parser.parse_args()
    myCustSpecMgr = AioSeedISOManager()
    if args.create_iso:
        if args.vm_name is None:
            print("Please provide AIO VM name to create the seed iso")
        if args.ip_addr is None:
            print("Please provide AIO VM IP Address to create the seed iso")
        myCustSpecMgr.createSeedISOAndAddToVM(args.vm_name, args.ip_addr)
    else:
        parser.print_help()
