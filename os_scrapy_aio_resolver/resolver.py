import logging
import socket
import time

import aiodns
import async_timeout
from scrapy.resolver import dnscache
from scrapy.utils.defer import maybeDeferred_coro
from scrapy.utils.reactor import is_asyncio_reactor_installed
from twisted.internet import defer
from twisted.internet.error import DNSLookupError
from twisted.internet.interfaces import IResolverSimple
from zope.interface import implementer

logger = logging.getLogger(__name__)


@implementer(IResolverSimple)
class AsyncResolver(object):
    def __init__(self, reactor, cache_size, timeout):
        self.reactor = reactor
        dnscache.limit = cache_size
        self.timeout = sum(timeout) if isinstance(timeout, tuple) else timeout
        self.reslover = aiodns.DNSResolver()

    def getHostByName(self, name, timeout=()):
        if name in dnscache:
            result = dnscache[name]
            logger.debug(f"using cache {name} {result}")
            return defer.succeed(result)
        timeout = sum(timeout) if timeout else self.timeout
        d = maybeDeferred_coro(self._getHostByName, name, timeout)
        return d

    async def _getHostByName(self, name, timeout):
        s = time.time()
        try:
            if timeout and timeout > 0:
                with async_timeout.timeout(timeout):
                    r = await self.reslover.gethostbyname(name, socket.AF_INET)
            else:
                r = await self.reslover.gethostbyname(name, socket.AF_INET)
        except aiodns.error.DNSError as e:
            logger.error(f"resolve {name} {e} {time.time()-s:.2f}")
            raise DNSLookupError()
        result = r.addresses[0]
        logger.debug(f"resolve {name} {result} {time.time()-s:.2f}")
        dnscache[name] = result
        return result

    def install_on_reactor(self):
        self.reactor.installResolver(self)

    @classmethod
    def from_crawler(cls, crawler, reactor):
        assert is_asyncio_reactor_installed()
        if crawler.settings.getbool("DNSCACHE_ENABLED"):
            cache_size = crawler.settings.getint("DNSCACHE_SIZE")
        else:
            cache_size = 0
        return cls(reactor, cache_size, crawler.settings.getfloat("DNS_TIMEOUT"))
