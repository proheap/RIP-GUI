import struct
import socket
from ipaddress import IPv4Network

RIP_MULTICAST			= "224.0.0.9"
RIP_UDP_PORT            = 520

RIP_COMMAND_REQUEST     = 0X01
RIP_COMMAND_RESPONSE    = 0X02

RIP_ADDRESS_FAMILY      = 0X02

RIP_METRIC_MIN 	        = 1
RIP_METRIC_MAX 	        = 15
RIP_METRIC_INFINITY     = 16

RIP_DEFAULT_UPDATE		= 30
RIP_DEFAULT_TIMEOUT		= 180
RIP_DEFAULT_GARBAGE		= 120

RIP_HEADER_SIZE         = 4
RIP_HEADER_PACK_FORMAT  = '!BBH'
RIP_ENTRY_SIZE          = 20
RIP_ENTRY_PACK_FORMAT   = '!HHIIII'

RIP_MAX_ROUTE_ENTRY     = 25
RIP_RECV_BUF_SIZE       = 41600

def Mask2Prefix(mask):
    return IPv4Network(f'0.0.0.0/{mask}').prefixlen

def Prefix2Mask(prefix):
    maskInt = 0xffffffff ^ (0xffffffff >> prefix)
    return socket.inet_ntoa(struct.pack("!I",maskInt))
