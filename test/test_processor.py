import unittest
import re, glob
from pprint import pprint
from test.helpers import build_station, stations
from ocr_machine.processor import process_station
from json import dump, dumps


class TestProcessor(unittest.TestCase):
    def setUp(self):
        pass

    def test_processor_petrol(self):
        path = "./data-test/petrol*.jpg"
        path = "./data-test/petrol-bigger-2.jpg"
        # path = "./data/full/*.jpg"
        stations_data = [station for station in stations(path)]
        results = [process_station(station) for station in stations_data]
        first_result = results[0]

        self.assertEqual(first_result['Q Max 95'], 1.206)
        self.assertEqual(first_result['Q Max 100'], 1.289)
        self.assertEqual(first_result['Q Max Diesel'], 1.110)

    def test_processor_omv(self):
        path = "./data-test/omv*.jpg"
        path = "./data-test/omv-complex*"
        stations_data = [station for station in stations(path, options={'scraper': 'omv'})]
        results = [process_station(station) for station in stations_data]

        first_result = results[0]
        self.assertEqual(first_result['OMV Avtoplin (LPG)'], 0.613)
        self.assertEqual(first_result['OMV Diesel'], 1.110)

    def test_processor_with_merge(self):
        path = "./data-test/omv*.jpg"
        station = build_station({
            'scraper': 'omv',
            'images': [{'path': f_path} for f_path in glob.glob(path)]
        })

        prices = process_station(station)
        self.assertEqual(prices['OMV Diesel'], 1.110)


if __name__ == '__main__':
    unittest.main()
