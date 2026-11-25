"""LAN-restricted DNS policy using dnslib's server framework and packet validation."""
import socket
import struct
import threading

from dnslib import A, CLASS, DNSHeader, DNSRecord, DNSError, OPCODE, QTYPE, RCODE, RR
from dnslib.server import DNSHandler, TCPServer, UDPServer

from ios_server.certificates import DOMAINS


class Resolver:
    def __init__(self, network, *, forward=None, log=lambda message: None):
        self.network = network
        self.forward = forward or self._forward
        self.log = log
        self.failures = 0
        self._lock = threading.Lock()

    def _forward(self, request, tcp):
        raw = request.send(self.network.upstream, port=53, tcp=tcp, timeout=2)
        response = DNSRecord.parse(raw)
        if response.header.tc and not tcp:
            response = DNSRecord.parse(request.send(self.network.upstream, port=53, tcp=True, timeout=2))
        return response

    def answer(self, request, peer, tcp=False):
        reply = request.reply()
        if not self.network.allows(peer):
            reply.header.rcode = RCODE.REFUSED
            return reply
        if request.header.qr or len(request.questions) != 1:
            reply.header.rcode = RCODE.FORMERR
            return reply
        if request.header.opcode != OPCODE.QUERY or request.q.qclass != CLASS.IN:
            reply.header.rcode = RCODE.NOTIMP
            return reply
        name = str(request.q.qname).rstrip('.').lower()
        if any(name == domain or name.endswith('.' + domain) for domain in DOMAINS):
            if request.q.qtype in (QTYPE.A, QTYPE.ANY):
                reply.add_answer(RR(request.q.qname, QTYPE.A, ttl=30, rdata=A(self.network.address)))
            return reply  # AAAA/HTTPS/etc stay empty, so the client uses the Mac IPv4 address.
        try:
            response = self.forward(request, tcp)
            if (not response.header.qr or response.header.id != request.header.id
                    or response.questions != request.questions):
                raise ValueError('Upstream DNS returned a mismatched response.')
            return response
        except (OSError, ValueError, DNSError) as exc:
            with self._lock:
                self.failures += 1
            self.log(f'Upstream DNS failed ({type(exc).__name__}); returning SERVFAIL.')
            reply.header.rcode = RCODE.SERVFAIL
            reply.header.aa = 0
            return reply

    def resolve(self, request, handler):
        return self.answer(request, handler.client_address[0], handler.protocol == 'tcp')


class Handler(DNSHandler):
    """Bounded TCP framing, including split prefixes; malformed requests get FORMERR."""
    def _read_exact(self, count):
        data = bytearray()
        while len(data) < count:
            part = self.request.recv(count - len(data))
            if not part:
                raise ValueError('Truncated DNS request')
            data.extend(part)
        return bytes(data)

    def handle(self):
        self.protocol = 'tcp' if self.server.socket_type == socket.SOCK_STREAM else 'udp'
        if not self.server.resolver.network.allows(self.client_address[0]):
            return
        try:
            if self.protocol == 'tcp':
                self.request.settimeout(3)
                length = struct.unpack('!H', self._read_exact(2))[0]
                if not 12 <= length <= 4096:
                    raise ValueError('Invalid DNS frame length')
                data = self._read_exact(length)
            else:
                data, connection = self.request
            try:
                request = DNSRecord.parse(data)
                reply = self.server.resolver.resolve(request, self)
            except (DNSError, ValueError):
                identity = int.from_bytes(data[:2], 'big')
                reply = DNSRecord(DNSHeader(id=identity, qr=1, rcode=RCODE.FORMERR))
            body = reply.pack()
            if self.protocol == 'tcp':
                self.request.sendall(struct.pack('!H', len(body)) + body)
            else:
                if len(body) > 1232:
                    body = reply.truncate().pack()
                connection.sendto(body, self.client_address)
        except (OSError, ValueError) as exc:
            self.server.logger.log_error(self, str(exc))


class RestrictedTCP(TCPServer):
    def verify_request(self, request, address):
        return self.resolver.network.allows(address[0])


class RestrictedUDP(UDPServer):
    allow_reuse_address = False  # an occupied UDP 53 must fail, never share datagrams

    def verify_request(self, request, address):
        return self.resolver.network.allows(address[0])
