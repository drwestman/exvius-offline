"""Pure LAN access policy and an injected macOS network-discovery boundary."""
from dataclasses import asdict, dataclass
from ipaddress import IPv4Address, IPv4Network
import re
import subprocess

_PRIVATE = tuple(IPv4Network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


@dataclass(frozen=True)
class Network:
    address: str
    subnet: str
    upstream: str
    local_addresses: tuple[str, ...] = ()
    bind: str = '0.0.0.0'
    dns_port: int = 53
    http_port: int = 80
    https_port: int = 443

    def __post_init__(self):
        address, subnet, upstream = IPv4Address(self.address), IPv4Network(self.subnet), IPv4Address(self.upstream)
        if not any(address in scope and subnet.subnet_of(scope) for scope in _PRIVATE) or address not in subnet:
            raise ValueError('Choose the Mac’s private home-network IPv4 address and subnet.')
        if (upstream.is_loopback or upstream.is_unspecified or upstream.is_multicast or upstream.is_link_local
                or str(upstream) in (*self.local_addresses, str(address))):
            raise ValueError('Upstream DNS points back to this Mac or an invalid address; use --upstream-dns.')
        for port in (self.dns_port, self.http_port, self.https_port):
            if type(port) is not int or not 0 <= port <= 65535:
                raise ValueError('Listener ports must be between 1 and 65535 (0 is reserved for tests).')
        object.__setattr__(self, 'address', str(address))
        object.__setattr__(self, 'subnet', str(subnet))
        object.__setattr__(self, 'upstream', str(upstream))

    def allows(self, address: str) -> bool:
        try:
            peer = IPv4Address(address)
            return peer.is_loopback or peer in IPv4Network(self.subnet)
        except ValueError:
            return False

    def configuration(self) -> dict:
        return asdict(self)


def _read(args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=5)
    if result.returncode:
        raise ValueError(f'Cannot read Mac network configuration: {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout


def discover(*, address=None, upstream=None, read=_read, **ports) -> Network:
    """Read-only discovery, called by serve; ordinary status/preview never needs subprocesses."""
    interfaces, interface = {}, None
    for line in read(['/sbin/ifconfig']).splitlines():
        header = re.match(r'^(\w+):', line)
        if header:
            interface = header[1]
        row = re.search(r'\binet\s+(\d+\.\d+\.\d+\.\d+)\s+netmask\s+(0x[0-9a-fA-F]+)', line)
        if interface and row:
            mask = str(IPv4Address(int(row[2], 16)))
            interfaces.setdefault(interface, []).append((row[1], mask))
    local = tuple(ip for rows in interfaces.values() for ip, _ in rows)
    if address:
        selected = next(((ip, mask) for rows in interfaces.values() for ip, mask in rows if ip == address), None)
        if selected is None:
            raise ValueError(f'LAN address {address} is not configured on this Mac.')
    else:
        route = read(['/sbin/route', '-n', 'get', 'default'])
        device = re.search(r'\binterface:\s*(\w+)', route)
        rows = interfaces.get(device[1], []) if device else []
        selected = rows[0] if rows else None
        if selected is None:
            raise ValueError('Cannot discover the home-network address. Specify --lan-address.')
    address, mask = selected
    subnet = str(IPv4Network(f'{address}/{mask}', strict=False))
    candidates = [upstream] if upstream else re.findall(
        r'nameserver\[\d+\]\s*:\s*(\S+)', read(['/usr/sbin/scutil', '--dns']))
    for candidate in dict.fromkeys(candidates):
        try:
            return Network(address, subnet, candidate, local, **ports)
        except ValueError:
            if upstream:
                raise
    raise ValueError('No usable upstream IPv4 DNS resolver found. Specify --upstream-dns with the router’s DNS address.')
