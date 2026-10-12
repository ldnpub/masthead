"""Lance edge-tts en essayant d'abord le nouveau serveur Microsoft (api.msedgeservices.com),
puis l'ancien (speech.platform.bing.com). Contournement du 403 apparu le 10/10/2026
(cf. github.com/rany2/edge-tts/issues/490). Mêmes arguments que la commande edge-tts."""
import sys
from aiohttp import WSServerHandshakeError
import edge_tts.communicate as communicate
from edge_tts.constants import TRUSTED_CLIENT_TOKEN, WSS_URL as LEGACY_WSS_URL
from edge_tts.util import main

URLS = [
    f"wss://api.msedgeservices.com/tts/cognitiveservices/websocket/v1?Ocp-Apim-Subscription-Key={TRUSTED_CLIENT_TOKEN}",
    LEGACY_WSS_URL,
]
for i, url in enumerate(URLS):
    communicate.WSS_URL = url
    try:
        main()
        break
    except WSServerHandshakeError as e:
        if e.status != 403 or i == len(URLS) - 1:
            raise
        print(f"{url.split('?')[0]} : 403, essai du serveur suivant", file=sys.stderr)
