# -*- coding:utf-8 -*-

from os import getenv
import re
from json import loads, dumps
from ocr_machine.ocr import ocr_pipeline
from utils.meta import PETROL_FUEL_NAMES, OMV_FUEL_NAMES, FUEL_NAMES, FUEL_CODES, REVERSED_FUEL_CODES, ALL_FUEL_NAMES
from os.path import realpath, dirname, join, exists
from pprint import pprint
from datetime import datetime
from collector.settings import MONGO_URL, REDIS_PUBSUB_URL
from utils.dict import flatten_dict
from pymongo import MongoClient, ASCENDING, DESCENDING, GEOSPHERE, HASHED
from rq import use_connection, get_current_connection
from redis import from_url, Redis, ConnectionPool, StrictRedis


# MongoDB
db = MongoClient(MONGO_URL, connect=False)['bm']
if getenv('DROP_STATIONS') == '1': db['stations'].drop()
create_index_key = db['stations'].ensure_index([('key', ASCENDING)], unique=True, cache_for=4000)
create_index_loc = db['stations'].ensure_index([('loc', GEOSPHERE)], cache_for=4000)
db['stations'].ensure_index([('company', ASCENDING)], cache_for=4000)
db['stations'].ensure_index([('prices', ASCENDING)], cache_for=4000)
# db['stations'].ensure_index([('prices_yearly', ASCENDING)], cache_for=4000)
# db['stations'].ensure_index([('prices_last_24h', ASCENDING)], cache_for=4000)
# db['stations'].ensure_index([('services', ASCENDING)], cache_for=4000)

# Redis Connection pool
redis_pool = ConnectionPool.from_url(REDIS_PUBSUB_URL)

def process_station(station_as_string):
    station = loads(station_as_string, encoding='utf8')
    station['prices'] = compute_prices(station)
    saved_station, result = save_station(station)
    publish_result = publish_to_eventbus(saved_station, result)
    return {'key': station['key'], 'prices': station['prices'], 'publish_result': publish_result}

def publish_to_eventbus(saved_station, result):
    r = Redis(connection_pool=redis_pool)
    publish_result= None
    meta = {'matched_count': result.matched_count, 'modified_count': result.modified_count}

    if result.modified_count == 0 and result.matched_count == 0 and result.upserted_id is not None:
        meta['upserted_id'] = str(result.upserted_id)
        publish_result= r.publish("events.station_insert", dumps({
            'type': 'station_insert',
            'meta': meta,
            'record': saved_station
        }, ensure_ascii=False))
    else:
        publish_result= r.publish("events.station_update", dumps({
            'type': 'station_update',
            'meta': meta,
            'record': saved_station
        }, ensure_ascii=False))

    return publish_result

def save_station(station):
    key = station['key']
    name = station['name']
    scraped_at = datetime.strptime(station['scraped_at'], '%Y-%m-%d %H:%M:%S')
    timestamp = int(scraped_at.timestamp())
    hour = scraped_at.hour
    minute = scraped_at.minute
    day_of_the_year = scraped_at.timetuple().tm_yday
    prices_dict = generalize_prices({FUEL_CODES[k]: v for k, v in station['prices'].items()})

    meta = {}
    for k in ['services', 'services_humans', 'shopping_hours', 'shopping_hours_humans']: meta[k] = station.get(k, {})

    pre_normalize = {
        'prices': prices_dict,
        'prices_yearly': {
            str(scraped_at.year): {station: {
                str(day_of_the_year): price} for station, price in prices_dict.items()
                                   }
        },
        'prices_last_24h': {
            station: {
                str(scraped_at.hour): price} for station, price in prices_dict.items()
        },
        'meta': meta,
        'updated_at': datetime.utcnow(),
    }

    data_to_set = flatten_dict(pre_normalize, '.')

    result = db['stations'].update_one({'key': key}, {
        "$setOnInsert": {
            'key': key,
            'name': name,
            'address': station['address'],
            'company': station['scraper'],
            'xcode': station['xcode'],
            'xid': station['xid'],
            'scraped_at': scraped_at,
            'scraped_url': station['scraped_url'],
            'loc': {'type': 'Point', 'coordinates': [station['lon'], station['lat']]}
        },
        "$set": data_to_set
    }, upsert=True)

    return [station, result]


def fix_image_path(path):
    images_path = join(dirname(dirname(realpath(__file__))), "data")
    final_path = path

    if path.startswith("full/"):
        final_path = join(images_path, path)

    if not exists(final_path):
        raise Exception('Image path %s does NOT exist!' % final_path)

    return final_path


def compute_prices(station):
    result = ocr_pipeline([fix_image_path(image['path']) for image in station['images']])
    prices_list = [process_prices(station, out_text['out_text']) for out_text in result]
    prices = {k: v for d in prices_list for k, v in d.items()}
    return prices


def generalize_prices(prices):
    general_types = dict()
    for key, value in prices.items():
        general_type = ALL_FUEL_NAMES[REVERSED_FUEL_CODES[key]][2]
        general_types[general_type] = value
    return {**prices, **general_types}


def process_prices(station, text):
    if station['scraper'] == "petrol":
        return process_petrol_prices(station, text)
    elif station['scraper'] == "omv":
        return process_omv_prices(station, text)
    else:
        raise Exception('Processing of "%s" is not yet supported.' % station['scraper'])


def process_petrol_prices(station, text, names=PETROL_FUEL_NAMES):
    prices = [float(x.replace(",", ".", 1)) for x in re.findall(r"(\d{1},\d{3,3})", text)]
    labels = [k for k, (pattern, flags, type) in names if re.search(pattern, text, flags)]
    result = dict(zip(labels, prices))
    return result


def process_omv_prices(station, text, names=OMV_FUEL_NAMES):
    prices = [float(x.replace(",", ".", 1)) for x in re.findall(r"(\d{1},\d{3,3})", text)]
    labels = [k for k, (pattern, flags, type) in names if re.search(pattern, text, flags)]

    if len(labels) != len(prices):
        print("Station %s" % station['name'])
        print('Problem with "%s"' % (text))
        print("Lengths: %d %d" % (len(labels), len(prices)))
        print("Prices:", prices)
        print("Labels:", labels)
        return {}

    result = dict(zip(labels, prices))
    return result
