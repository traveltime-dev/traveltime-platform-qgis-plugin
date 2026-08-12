import configparser
import os

metadata = configparser.ConfigParser()
metadata.read(os.path.join(os.path.dirname(__file__), "metadata.txt"))

TTP_VERSION = metadata["general"]["version"]
DEFAULT_ENDPOINT = "https://api.traveltimeapp.com"

# Must be kept out of logs and out of the response cache
CREDENTIAL_HEADERS = ("X-Application-Id", "X-Api-Key")
