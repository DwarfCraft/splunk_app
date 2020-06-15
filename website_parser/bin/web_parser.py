#!/usr/bin/python3
import requests
import time
import re
from bs4 import BeautifulSoup
#import pandas as pd

def get_html(url):
    requests.get(url)
    page = requests.get(url)
    soup = BeautifulSoup(page.text, 'lxml')
    return soup
#END get_html

# Laser Printer
url = 'http://192.168.1.100/general/status.html'
soup = get_html(url)
data_list = soup.find_all('img', class_ = 'tonerremain')
for data in data_list:
    ts = time.time()
    #print(data)
    match = re.match(r".*height\=\"(\d+)\"\s.*", str(data))
    #print(match)
    if match:
        str_data = str(ts) + ", printer=\"Laser\", type\"toner\", ink_level=" + str(match.group(1))
        print(str_data)

# Inkjet Printer
url = 'http://192.168.1.102/PRESENTATION/ADVANCED/INFO_PRTINFO/TOP'
soup = get_html(url)
data_list = soup.find_all('img', class_ = "color")
for data in data_list:
    ts = time.time()
    match = re.match(r".*height\=\"(\d+)\"\ssrc\=.+Ink_(\w)\.PNG.*", str(data))
    if match:
        str_data = str(ts) + ", printer=\"color\", type=\"" + str(match.group(2)) + "\", ink_level=" + str(match.group(1))
        print(str_data)

# MyCloud
url = 'http://192.168.1.150/api/2.1/rest/storage_usage'
soup = get_html(url)
data_list = soup.find_all('storage_usage')
for data in data_list:
    ts = time.time()
    match = re.match(r".*\<size\>(\d+)..size..usage.(\d+)..usage..video.(\d+)..video..photos.(\d+)..photos..music.(\d+)..music..other.(\d+)\<\/other\>.*", str(data))
    if match:
        str_data = str(ts) + ", total_size=" + str(match.group(1)) + ", used=" + str(match.group(2)) + ", video=" + str(match.group(3)) + ", photos=" + str(match.group(4)) + ", music=" + str(match.group(5)) + ", other=" + str(match.group(6))
        print(str_data)
