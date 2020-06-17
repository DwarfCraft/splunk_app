####
## TA-pihole
## v 1.0.0
## 8/13/2018
## Dan Potter
## @dpotter on slack
####
This app was built for analyzing data from piHole and other dnsmasq based logs for DHCP/dns data. It is CIM compliant with the Network Resolution (DNS) data model

No support is assumed or provided beyond this README. Please be sure to set the correct onboard sourcetype (pihole), or associate the appropriate log with the correct sourcetype from /default/props.conf

**For the best visibility, please ensure you use 
	log-queries=extra
**In your dnsmasq.conf file or advanced configuration options. This ensures we have complete query/response data
