import re
from datetime import date, timedelta
import json

from bs4 import BeautifulSoup
import dateparser

from webparser.base import BaseParser, module_logger


class ProfileParser(BaseParser):
    site = 'profile.ru'
    url_list_articles = 'https://profile.ru/wp-admin/admin-ajax.php?id=tag_request&slug=rasteniya' \
                        '&canonical_url=https://profile.ru/tag/rasteniya/&posts_per_page=50&offset=0' \
                        '&post_type=profile_article,anew&repeater=default&seo_start_page=1&preloaded=false' \
                        '&preloaded_amount=0&tag__and=102439&order=DESC&orderby=date&action=alm_get_posts' \
                        '&query_type=standard'

    def collect_list_urls(self, parse_for_days=-1):
        list_urls = []
        current_date = date.today()
        if parse_for_days>=0:
            parse_to_date = current_date - timedelta(parse_for_days)
            message = ' for last %s days' % parse_for_days
        else:
            parse_to_date = None
            message = ''

        num_page = 0
        get_query = '&page=%s' % num_page
        # request return json data
        json_data = self.get_page(self.url_list_articles + get_query)
        json_data = json.loads(json_data)
        post_count = json_data['meta']['postcount']
        total_post = json_data['meta']['totalposts']

        last_article_date = current_date
        while post_count>0:
            if parse_to_date:
                if last_article_date<parse_to_date:
                    break

            get_query = '&page=%s' % num_page
            json_data = self.get_page(self.url_list_articles + get_query)
            json_data = json.loads(json_data)
            html_data = json_data['html']
            post_count = json_data['meta']['postcount']
            if post_count<0 or not html_data:
                break

            links_to_articles, last_article_date = self.process_parse_list_articles(html_data, parse_to_date)
            list_urls.extend(links_to_articles)
            num_page += 1

        # return unique values
        list_urls = list(set(list_urls))
        if len(list_urls)!=total_post and not parse_to_date:
            module_logger.warning('[%s] The number of collected articles (%s) '
                                  'does not correspond to the expected (%s).'
                           % (self.site, len(list_urls), total_post))
        else:
            module_logger.info('On the site %s found %s links to articles%s.'
                           % (self.site, len(list_urls), message))
        return list_urls

    def process_parse_list_articles(self, html_data, parse_to_date=None, *args, **kwargs):
        soup = BeautifulSoup(html_data, 'lxml')
        links_to_articles = []
        last_date = None

        for article in soup.find_all('div', {'class': 'newslist__item'}):
            link = article.find('h2', {'class': 'newslist__title'}).find('a').attrs['href']
            last_date = article.find('div', {'class': 'publication__data'}).text
            last_date = dateparser.parse(last_date,
                                         settings={'PREFER_DATES_FROM': 'past'},
                                         date_formats=['%d.%m.%Y %H:%M'])
            last_date = last_date.date()

            if parse_to_date:
                if last_date<parse_to_date:
                    break
            links_to_articles.append(link)

        return links_to_articles, last_date

    def process_parse_page(self, html_data, source_url=None):
        soup = BeautifulSoup(html_data, 'lxml')
        json_data = {'content': []}
        article_body = soup.find('div', {'class': 'onenews__body'}).find('div', {'class': 'micromarking'})

        announce = soup.find('figure')
        if announce:
            # logg news with video
            if announce.find('div', {'class': 'audioplayer'})\
                    or announce.find('video') or announce.find('iframe'):
                module_logger.info('Found articles with video %s' % source_url)

            announce_image = announce.find('img', {'class': 'wp-post-image'})
            if announce_image:
                try:
                    title = announce_image.attrs['title']
                except KeyError:
                    title = ''
                announce_image = {'image':
                                      {'source': announce_image.attrs['src'],
                                       'title': title}}
                json_data['content'].append(announce_image)


        publication_date = soup.find('div', {'class': 'publication__data'}).find('span', {'class': 'publication__number'})
        publication_date = publication_date.get_text()
        publication_date = dateparser.parse(publication_date, date_formats=['%d.%m.%Y %H:%M'])

        json_data['publication_date'] = {'year': publication_date.year,
                                         'month': publication_date.month,
                                         'day': publication_date.day,
                                         'hour': publication_date.hour,
                                         'minute': publication_date.minute}

        title = soup.find(re.compile("\w"), {'class': 'onenews__title'})
        title = title.get_text()
        json_data['title'] = title

        header_tags = ['h1', 'h2', 'h3', 'h4', 'h5']
        for block in article_body.find_all(re.compile("\w"), recursive=False):
            if block.name in header_tags:
                data_type = block.name
                content = block.get_text()

            elif block.name=='p':
                data_type = 'text'
                content = block.get_text()

            elif block.name == 'ul':
                data_type = 'list'
                content = []
                list_items = block.find_all('li')
                for item in list_items:
                    content.append(item.get_text())

            elif block.name == 'div':
                if 'swiper-container-bg' in block['class']:
                    for image in block.find_all('img'):
                        data_type = 'image'
                        try:
                            title = image.attrs['title']
                        except KeyError:
                            title = ''
                        content = {'source': image.attrs['src'], 'title': title}
                        json_data['content'].append({data_type: content})
                else:
                    module_logger.warning('Find unknown div block for %s' % (source_url))
                continue

            else:
                # logging something strange
                module_logger.warning('Find unknown data type %s for %s' % (block.name, source_url))
                continue

            json_data['content'].append({data_type: content})
        return json_data
