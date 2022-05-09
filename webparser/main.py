import json
from datetime import date, timedelta

from webparser.base import *
from site_parsers.RIA_parser import RIA_Parser
from site_parsers.MIR24_parser import MIR24_Parser

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36"}



url = 'https://mir24.tv/economy/super/list/filter/all'


parser = MIR24_Parser(headers=HEADERS, verbosity='debug', timeout=5, pause_between_requests=0.5)
parser.collect_list_urls(parse_for_days=20)

# with open('news.json', 'w', encoding='utf-8') as file:
#     json.dump(json_data, file, indent=4, ensure_ascii=False)

