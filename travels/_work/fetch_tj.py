import json, re, sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))
import requests
from bs4 import BeautifulSoup

RAW = Path('raw')
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

def slug(url):
    import urlparse_  # noqa
