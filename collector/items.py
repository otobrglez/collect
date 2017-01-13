# -*- coding: utf-8 -*-
import scrapy
from uuid import uuid4


class Station(scrapy.Item):
    scraped_at = scrapy.Field()
    scraped_url = scrapy.Field()
    scraper = scrapy.Field()
    images = scrapy.Field()
    image_urls = scrapy.Field()
    name = scrapy.Field()
    address = scrapy.Field()
    lon = scrapy.Field()
    lat = scrapy.Field()
    xid = scrapy.Field()  # ID on page
    xcode = scrapy.Field()  # Internal ID if possible
    key = scrapy.Field()

    # TODO: services
    # TODO: schedule

    @staticmethod
    def generate_key():
        return uuid4()
