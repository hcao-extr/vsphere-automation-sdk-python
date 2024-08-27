network:
  version: 2
  ethernets:
    ens192:
      nameservers:
        addresses:
        - "134.141.121.33"
        - "134.141.79.201"
        search:
        - "extremenetworks.com"
        - "corp.extremenetworks.com"
      gateway4: "10.16.118.1"
      dhcp4: "false"
      addresses:
      - "10.16.118.255/24"
