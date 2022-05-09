import re
from datetime import date, timedelta

from bs4 import BeautifulSoup
from bs4.element import NavigableString

import dateparser

from webparser.base import BaseParser, module_logger

class MIR24_Parser(BaseParser):
    site = 'mir24.tv'
    url_list_articles = 'https://mir24.tv/rasteniya/simple/list/filter/all'

    #  Getting all links to articles works in sync mode, which slows down the parsing speed,
    #  but on the other hand, does not load the site with requests, which reduces the likelihood of blocking
    def collect_list_urls(self, parse_for_days=-1):
        list_urls = []
        current_date = date.today()
        if parse_for_days>=0:
            parse_to_date = current_date - timedelta(parse_for_days)
            message = ' for last %s days' % parse_for_days
        else:
            parse_to_date = None
            message = ''

        last_article_date = current_date
        penult_article_date = last_article_date + timedelta(days=1)
        # while last_article_date != penult_article_date:
        #     if parse_to_date:
        #         if last_article_date<parse_to_date:
        #             break
        #     penult_article_date = last_article_date
        #
        #     get_query = str(last_article_date).replace('-', '')
        #     html_data = self.get_page(self.url_list_articles+get_query)
        #     links_to_articles, last_article_date = self.process_parse_list_articles(html_data, parse_to_date)
        #     list_urls.extend(links_to_articles)
        #
        # # return unique values
        # list_urls = list(set(list_urls))
        # module_logger.info('On the site %s found %s links to articles%s.'
        #                    % (self.site, len(list_urls), message))
        return list_urls

    def process_parse_list_articles(self, html_data, parse_to_date=None, *args, **kwargs):
        soup = BeautifulSoup(html_data, 'lxml')
        links_to_articles = []
        last_date = None

        for article in soup.find('div', {'class': 'pd'}).find_all('div', {'class': 'ncl-cont'}):
            link = article.find('a', {'class': 'nc-link'}).attrs['href']
            last_date = article.find('span', {'class': 'date-block'}).text
            last_date = dateparser.parse(last_date,
                                         settings={'PREFER_DATES_FROM': 'past'},
                                         date_formats=['%H %M %d %m %Y'])
            last_date = last_date.date()

            if parse_to_date:
                if last_date<parse_to_date:
                    break
            links_to_articles.append(link)

        return links_to_articles, last_date

    def process_parse_page(self, html_data, source_url=None):
        soup = BeautifulSoup(html_data, 'lxml')
        json_data = {'content': []}

        # interesting, what means article-first? article-second exist?
        if soup.find('div', {'class': 'article-second'}):
            module_logger.info('[%s] Found something interesting. Class article-second exists. %s'
                               % (self.__class__.__name__, source_url))

        main_frame = soup.find('div', {'class': 'postcontent'})
        article_header = main_frame.find('div', {'class': 'head-cell-s'})
        article_body = main_frame.find_all('article')

        title = article_header.find(re.compile("\w"), {'class': 'post-title'}).get_text()
        json_data['title'] = title

        publication_date = article_header.find(re.compile("\w"), {'class': 'date-span'}).get_text()
        # TODO check this (date created right)
        publication_date = dateparser.parse(publication_date, date_formats=['%H %M %d %m %Y'])
        json_data['publication_date'] = str(publication_date)

        announce_image = main_frame.find('div', {'class': 'postimage-block'})
        if announce_image:
            announce_image = announce_image.find('img')
            announce_image = {'image':
                                  {'source': announce_image.attrs['src']}}
            json_data['content'].append(announce_image)

        num_articles = 0
        ignored_data_types = ['em', 'style', 'a']
        processed_data_types = ['p', 'blockquote']
        # I hope they don't nest the <ul> tag in div. There are a lot of empty divs on the site
        ignore_wrap = ['xcr', 'div', 'script']
        for article in article_body:
            num_articles += 1
            # log if we have 2+ articles
            if num_articles>1:
                module_logger.info('[%s] Found extra articles in news. %s'
                               % (self.__class__.__name__, source_url))

            content_tag = article.find('div', {'class': 'article-content'})

            # log if content not wrapped in element from proccessed_data_type
            for tag in content_tag.children:
                if tag.__class__==NavigableString:
                    continue
                else:
                    if not tag.name in ignore_wrap and not tag.name in processed_data_types:
                        module_logger.warning('[%s] Content wrapped unknown tag. Tag: %s. Url: %s'
                                              % (self.__class__.__name__, f'<{tag.name}>', source_url))

            # parse content
            search_expr = '(%s)' % "\\b|".join(processed_data_types)
            for item in content_tag.find_all(re.compile(search_expr), recursive=False):
                text_content = item.get_text()
                if text_content:
                    if item.name=='p':
                        data_type = 'text'
                    elif item.name=='blockquote':
                        data_type = 'quote'
                    json_data['content'].append({data_type: text_content})

                # log if found new data type
                for elem in item.children:
                    if elem.__class__==NavigableString:
                        continue
                    if elem.name not in ignored_data_types and elem.name not in processed_data_types:
                        module_logger.warning('[%s] Found unknown data type %s for %s'
                                              % (self.__class__.__name__, f'<{elem.name}>', source_url))

        return json_data