import os, configparser

metadata = configparser.ConfigParser()
metadata.read(os.path.join(os.path.dirname(__file__), "metadata.txt"))

TTP_VERSION = metadata["general"]["version"]
DEFAULT_ENDPOINT = "https://api.traveltimeapp.com"
