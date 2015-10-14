# AWS Route Monitor
Script that monitors AWS routes for black-hole routes, and corrects the situation if detected

## Usage
```
Usage: aws_route_mon.py [-r route table] [-i interface] [-c cidr] [-R aws region] [-P aws profile] [-I aws id] [-K aws key]
Options:
  -h, --help            show this help message and exit
  -r ROUTE_TABLE, --route-table=ROUTE_TABLE
                        AWS route table ID
  -i INTERFACE, --interface=INTERFACE
                        AWS interface ID to use as next-hop
  -c CIDR, --cidr=CIDR  CIDR to check in the route table (will be created if
                        it doesn't exist) - Default: 0.0.0.0/0
  -R REGION, --region=REGION
                        AWS region to connect to
  -P PROFILE, --profile=PROFILE
                        Boto profile to use
  -I ACCESS_ID, --access-id=ACCESS_ID
                        AWS access ID to use
  -K ACCESS_KEY, --access-key=ACCESS_KEY
                        AWS access key to use
  -L LOGGING_TO, --logging-to=LOGGING_TO
                        Send logs to: console, or, syslog
```

In production - it's expected that `ACCESS_ID`, `ACCESS_KEY` and `PROFILE` are not used, as these can be sourced automatically from an EC2 instance profile/role.

Hence a hypothetical cronjob might look like this:
```
* * * * *  root  /usr/local/sbin/aws_route_mon.py -r rtb-1234abcd -i eni-45ef67ab -R ap-southeast-2 -L syslog
```

# Why?
Inspired by these AWS re:invent & summit presentations:
* Slide 41: [High Availability Application Architectures in Amazon VPC](http://www.slideshare.net/AmazonWebServices/high-availability-application-architectures-in-amazon-vpc-arc202-aws-reinvent-2013)
* Slide 167: [AWS Blackbelt NINJA Dojo](http://www.slideshare.net/AmazonWebServices/aws-blackbelt-ninja-dojo-dean-samuels)

This script can be (but doesn't have to be) deployed on an auto-scale group of Squid proxies to make these proxies also perform a NAT function.

Due to how routing tables work, only one machine can claim the default route for a route-table - but at least we can still combine the self-healing capabilities of auto-scaling with routing.

# Example use: Squid ASG + NAT
In this case, we're going to have an auto-scale group that provides EC2 instances running Squid for HTTP/HTTPS proxy.  This can scale up / down as the proxy load dictates.

In addition to the proxy functionality, we'll also make these EC2 instance provide the NAT function to allow non-proxy traffic to flow out from the VPC.  For example, NTP and SMTP traffic.

The `aws_route_mon.py` script shall be run on each EC2 instance, monitoring the private subnet's routing table.  The role of the script is to replace the next-hop on the 0.0.0.0/0 entry in the routing table if it detects a black-hole route.

![Squid ASG + NAT diagram](https://raw.githubusercontent.com/auspost/aws-route-mon/master/images/squid_nat.png)

## Auto-detection of ENI ID
Here's a snippet of bash code to get the (primary) ENI of an EC2 instance:

```
MAC=`curl -m 1 http://169.254.169.254/latest/meta-data/mac/ 2>/dev/null`
ENI=`curl -m 1 http://169.254.169.254/latest/meta-data/network/interfaces/macs/${MAC}/interface-id/ 2>/dev/null`
```

This can be used as an input to the `--interface` argument of the `aws_route_mon.py` script.
