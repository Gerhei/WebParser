import logging
import requests
from requests.exceptions import RequestException, HTTPError, ConnectionError, Timeout

from time import sleep
from datetime import datetime
import random

import asyncio
import aiohttp
from aiohttp.client_exceptions import ClientConnectorError, ClientResponseError
from asyncio.exceptions import TimeoutError

# https://github.com/aio-libs/aiohttp/issues/6635
from functools import wraps
from asyncio.proactor_events import _ProactorBasePipeTransport

def silence_event_loop_closed(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except RuntimeError as e:
            if str(e) != 'Event loop is closed':
                raise
    return wrapper

_ProactorBasePipeTransport.__del__ = silence_event_loop_closed(_ProactorBasePipeTransport.__del__)


class RequestFailed(Exception):
    def __init__(self, message, url):
        self.url = url
        self.message = 'Request failed for %s. %s' \
                  % (url, message)
        super().__init__(self.message)


class ReturnNotHTML(Exception):
    def __init__(self, url, html_data):
        self.url = url
        self.message = 'Request returned non-html data. Url: %s. Type data: %s' \
                       % url, type(html_data)
        super().__init__(self.message)


# TODO return links that could not be parsed
#   fake user agent, proxy
#   read from file
#   add async mode with _get_page problem
class BaseParser():
    site = None
    url_list_articles = None
    headers = None

    _json_list_pages = None

    def __init__(self, headers, verbosity='warning', pause_between_requests=1, timeout=3, *log_handlers):
        self.headers = headers
        self._time_out = timeout
        self._pause_between_requests = pause_between_requests

        self.module_logger = logging.getLogger(self.__class__.__name__)
        self.module_logger.setLevel(logging.DEBUG)
        self._setup_loggers(verbosity, *log_handlers)

    def _setup_loggers(self, verbosity, *log_handlers):
        console_log_level = getattr(logging, verbosity.upper())
        console_format = logging.Formatter('%(levelname)s: %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_log_level)
        console_handler.setFormatter(console_format)
        self.module_logger.addHandler(console_handler)

        if len(log_handlers)>0:
            for handler in log_handlers:
                self.module_logger.addHandler(handler)
        else:
            file_format = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
            file_handler = logging.FileHandler('webparser.log')
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(file_format)
            self.module_logger.addHandler(file_handler)

    async def _parse_list_pages(self, list_urls):
        """ For a given list of urls, return parsed data for each of the pages """
        self.module_logger.info('[%s] Started parsing pages from the list of urls.' % self.__class__.__name__)
        self.parse_info = {'num_pages': len(list_urls), 'processed': 0, 'collected': 0, 'skipped': 0}
        with requests.Session() as session:
            json_page_data_list = await asyncio.gather(*[self._parse_page(links, session)
                                                         for links in list_urls])

        json_data = {}
        for (links, json_page_data) in zip(list_urls, json_page_data_list):
            if isinstance(json_page_data, dict):
                json_data[links] = json_page_data
        self._json_list_pages = json_data
        self.module_logger.info('[%s] Finished parsing pages from the list of urls. Successfully collected '
                           '%s pages out of %s (%s skipped).'
                           % (self.__class__.__name__, self.parse_info['collected'],
                              self.parse_info['num_pages'], self.parse_info['skipped']))

    async def _parse_page(self, url, session):
        pause = self._pause_between_requests + random.random() / 5 if self._pause_between_requests else 0
        # FIXME what's the point in async parsing if we need have pause between requests?
        sleep(pause)

        try:
            html_data = self.get_page(url, session)
            if not isinstance(html_data, str):
                raise ReturnNotHTML(url, html_data)
        except RequestFailed as ex:
            self.module_logger.error(ex.__str__())
            return None
        except ReturnNotHTML as ex:
            self.module_logger.error(ex.__str__())
            return None
        else:
            json_data = self.process_parse_page(html_data, source_url=url)
            if isinstance(json_data, dict):
                self.parse_info['collected'] += 1
            else:
                self.parse_info['skipped'] += 1
            return json_data
        finally:
            self.parse_info['processed'] += 1
            self.module_logger.debug('[%s] Processed pages: %s/%s'
                                % (self.__class__.__name__, self.parse_info['processed'], self.parse_info['num_pages']))

    def parse(self, list_urls):
        """ For a given urls return parsed data in format: {url: page_content} """
        random.shuffle(list_urls)
        asyncio.run(self._parse_list_pages(list_urls))
        return self._json_list_pages

    def collect_list_urls(self, parse_for_days=-1):
        """
         Finds all links to articles on site and returns them.
         parse_for_days means parses data for a certain number of days
         parse_for_days<0 means parse all data from site
         parse_for_days=0 means to parse the data for the current day
        """
        raise NotImplementedError('Subclasses must implement this method')

    def process_parse_list_articles(self, html_data, *args, **kwargs):
        """ For a given html page, finds all links to articles in it and returns a list of urls """
        raise NotImplementedError('Subclasses must implement this method')

    def process_parse_page(self, html_data, source_url=None):
        """
         For a given html page return parsed data in json.
         Source urls optional and needs only for logging.
        """
        raise NotImplementedError('Subclasses must implement this method')

    # FIXME during async parsing, the site blocks access, the reason is unknown
    async def _get_page(self, url, session):
        try:
            async with session.get(url=url, headers=self.headers, ssl=True,
                                       timeout=self._time_out) as response:
                response_text = await response.text()
                status_code = response.status
                response.raise_for_status()

        except ClientResponseError as ex:
            raise RequestFailed('Get status code %s.' % status_code, url) from ex

        except TimeoutError as ex:
            raise RequestFailed('Timeout (%s sec) expired.' % self._time_out, url) from ex

        except ClientConnectorError as ex:
            raise RequestFailed('ConnectionError.', url) from ex

        except Exception as ex:
            raise RequestFailed('Exception %s.' % ex, url) from ex

        else:
            return response_text

    # Sync version _get_page for outer use
    def get_page(self, url, session=None):
        """ Make a request by applying all the request parameters specified in the class (headers for example) """
        try:
            if session:
                request_object = session
            else:
                request_object = requests
            response = request_object.get(url, headers=self.headers, timeout=self._time_out)
            response.raise_for_status()
            response.encoding = 'utf-8'
            response_text = response.text
        except HTTPError as ex:
            raise RequestFailed('Get status code %s.' % response.status_code, url) from ex
        except Timeout as ex:
            raise RequestFailed('Timeout (%s sec) expired.' % self._time_out, url) from ex
        except ConnectionError as ex:
            raise RequestFailed('ConnectionError.', url) from ex
        except RequestException as ex:
            raise RequestFailed('RequestException %s.' % ex, url) from ex
        else:
            return response_text
