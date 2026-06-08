import requests

def translate_text(text):

    try:

        url = "https://translate.googleapis.com/translate_a/single"

        params = {
            "client": "gtx",
            "sl": "auto",
            "tl": "zh-CN",
            "dt": "t",
            "q": text
        }

        r = requests.get(
            url,
            params=params,
            timeout=10
        )

        result = r.json()

        return result[0][0][0]

    except:

        return text
