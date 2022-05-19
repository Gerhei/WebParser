import requests
import json
from datetime import date, timedelta

from webparser.base import *
from site_parsers.RIA_parser import RIA_Parser
from site_parsers.MIR24_parser import MIR24_Parser
from site_parsers.Profile_parser import ProfileParser


#url = 'https://cdn.profile.ru/wp-content/uploads/alm-cache/28513481751024391084611/page-17.html'
url = 'https://profile.ru/wp-admin/admin-ajax.php?id=tag_request&slug=rasteniya' \
      '&canonical_url=https://profile.ru/tag/rasteniya/&posts_per_page=50&offset=0' \
      '&post_type=profile_article,anew&repeater=default&seo_start_page=1&preloaded=false' \
      '&preloaded_amount=0&tag__and=102439&order=DESC&orderby=date&action=alm_get_posts' \
        '&query_type=standard&page=1'


HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36"}



parser = ProfileParser(headers=HEADERS, verbosity='debug', timeout=5, pause_between_requests=0.5)


json_data = parser.get_page(url)
json_data = json.loads(json_data)
html_data = json_data['html']
json_data = parser.collect_list_urls()
#
#
with open('news.json', 'w', encoding='utf-8') as file:
    json.dump(json_data, file, indent=4, ensure_ascii=False)

