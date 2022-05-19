import re
from datetime import date, timedelta

from bs4 import BeautifulSoup
import dateparser

from news.parsers.base import BaseParser, module_logger


class RIA_Parser(BaseParser):
    site = 'ria.ru'
    # TODO Possible problem: if all the news on the page is dated one day, can't get pages for previous dates
    url_list_articles = 'https://ria.ru/services/tag_rastenija/more.html?date='

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
        while last_article_date != penult_article_date:
            if parse_to_date:
                if last_article_date<parse_to_date:
                    break
            penult_article_date = last_article_date

            get_query = str(last_article_date).replace('-', '')
            html_data = self.get_page(self.url_list_articles+get_query)
            links_to_articles, last_article_date = self.process_parse_list_articles(html_data, parse_to_date)
            list_urls.extend(links_to_articles)

        # return unique values
        list_urls = list(set(list_urls))
        module_logger.info('On the site %s found %s links to articles%s.'
                           % (self.site, len(list_urls), message))
        return list_urls

    def process_parse_list_articles(self, html_data, parse_to_date=None, *args, **kwargs):
        soup = BeautifulSoup(html_data, 'lxml')
        links_to_articles = []
        last_date = None

        for article in soup.find_all('div', {'class': 'list-item'}):
            link = article.find('a', {'class': 'list-item__title'}).attrs['href']
            last_date = article.find('div', {'class': 'list-item__date'}).text
            last_date = dateparser.parse(last_date,
                                         settings={'PREFER_DATES_FROM': 'past'})
            last_date = last_date.date()

            if parse_to_date:
                if last_date<parse_to_date:
                    break
            links_to_articles.append(link)

        return links_to_articles, last_date

    def process_parse_page(self, html_data, source_url=None):
        soup = BeautifulSoup(html_data, 'lxml')
        json_data = {'content': []}
        article_header = soup.find('div', {'class': 'article__header'})
        article_body = soup.find('div', {'class': 'article__body'})

        announce = article_header.find('div', {'class': 'article__announce'})
        if announce:
            # Skip news with video, because in most cases they do not carry useful information
            if announce.find('div', {'class': 'audioplayer'})\
                    or announce.find('video') or announce.find('iframe'):
                module_logger.info('Skip articles with video %s' % source_url)
                return None

            announce_image = announce.find('img')
            if announce_image:
                announce_image = {'image':
                                      {'source': announce_image.attrs['src'],
                                       'title': announce_image.attrs['title']}}
                json_data['content'].append(announce_image)


        publication_date = article_header.find('div', {'class': 'article__info-date'}).find('a')
        publication_date = publication_date.get_text()
        publication_date = dateparser.parse(publication_date, date_formats=['%H:%M %d.%m.%Y'])

        json_data['publication_date'] = {'year': publication_date.year,
                                         'month': publication_date.month,
                                         'day': publication_date.day,
                                         'hour': publication_date.hour,
                                         'minute': publication_date.minute}

        title = article_header.find(re.compile("\w"), {'class': 'article__title'})
        title = title.get_text()
        json_data['title'] = title

        ignored_types = ['article', 'banner', 'social', 'audio']
        header_tags = ['h1', 'h2', 'h3', 'h4', 'h5']
        for block in article_body.find_all('div', {'class': 'article__block'}):
            data_type = block['data-type']
            content = None
            if data_type in ignored_types:
                # skip banner ads and links on other articles
                continue

            elif data_type in header_tags:
                header_content = block.get_text()
                content = header_content

            elif data_type == 'text':
                text_content = block.get_text()
                # skip ads telegram channel
                if 'нашем Телеграм-канале'.lower() in text_content.lower():
                    continue
                content = text_content

            elif data_type == 'list':
                content = []
                list_items = block.find_all('li')
                for item in list_items:
                    item_text = ""
                    for item_data in item.children:
                        if item_data.name == 'div':
                            # skip list label
                            if 'article__list-label' in item_data.attrs['class']:
                                continue
                        item_text += item_data.get_text()
                    content.append(item_text)

            elif data_type == 'media':
                # processing only images
                image = block.find('img')
                if not image:
                    continue
                data_type = 'image'

                src = image.attrs['src']
                if not src.startswith('http'):
                    if image.attrs['data-src']:
                        src = image.attrs['data-src']
                    else:
                        module_logger.warning('Don\'t find src attr for image "%s" for %s'
                                              % (image.attrs['title'], source_url))

                content = {'source': src, 'title': image.attrs['title']}

            elif data_type == 'quote':
                content = block.get_text()

            elif data_type == 'table':
                head = block.find('table').find('thead')
                table_body = block.find('table').find_all('tr')
                content = {'head': [], 'body': []}

                for row in head.find_all('tr'):
                    for column in row.find_all('td'):
                        content['head'].append(column.get_text())

                for row in table_body:
                    table_row = []
                    for column in row.find_all('td'):
                        table_row.append(column.get_text())
                    if table_row == content['head']:
                        continue
                    content['body'].append(table_row)

            elif data_type == 'infographics':
                image = block.find('img')
                if not image:
                    continue
                data_type = 'image'
                content = {'source': image.attrs['src'], 'title': image.attrs['title']}

            elif data_type == 'photolenta':
                for item in block.find_all('div', {'class': 'article__photo-item'}):
                    image = item.find('div', {'class': 'article__photo-item-image'}).find('img')
                    content = {'source': image.attrs['src'], 'title': image.attrs['title']}
                    json_data['content'].append({'image': content})

                    item = item.find('div', {'class': 'article__photo-inner-desc'})\
                        .find('div', {'class': 'article__photo-item-text'})

                    for paragraph in item.find_all('p'):
                        text_content = paragraph.get_text()
                        json_data['content'].append({'text': text_content})

                continue

            elif data_type == 'recipe':
                title = block.find('div', {'class': 'article__recipe-title'})
                if title:
                    json_data['content'].append({'h3': title.get_text()})

                text_content = block.find('div', {'class': 'article__recipe-desc'})
                if text_content:
                    text_content = text_content.get_text()
                else:
                    text_content = ''

                text_details = block.find('div', {'class': 'article__recipe-details'})
                if text_details:
                    for item in text_details.find_all('div', {'class': 'article__recipe-details-item'}):
                        detail_title = item.find('div', {'class': 'article__recipe-details-title'}).get_text()
                        detail_value = item.find('div', {'class': 'article__recipe-details-value'}).get_text()
                        text_content += f'\n{detail_title}: {detail_value}'
                if text_content:
                    json_data['content'].append({'text': text_content})

                subtitle = block.find('div', {'class': 'article__recipe-subtitle'})
                if subtitle:
                    json_data['content'].append({'h3': subtitle.get_text()})

                instructions = block.find('div', {'class': 'article__recipe-instruction'})
                if instructions:
                    content = []
                    for elem in instructions.find_all('div', {'class': 'article__recipe-instruction-text'}):
                        content.append(elem.get_text())
                    json_data['content'].append({'list': content})

                continue

            else:
                # logging something strange
                module_logger.warning('Find unknown data type %s for %s' % (data_type, source_url))
                continue

            json_data['content'].append({data_type: content})
        return json_data