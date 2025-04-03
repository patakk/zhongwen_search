import string
import re
import regex
from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from hanziconv import HanziConv
from hanzipy.dictionary import HanziDictionary
from nltk.stem import WordNetLemmatizer
import logging

app = Flask(__name__)
application = app

lemmatizer = WordNetLemmatizer()
lemmatizer.lemmatize('jeans')

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
)


dictionary = HanziDictionary()

def load_secrets(secrets_file):
    secrets = {}
    try:
        with open(secrets_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    secrets[key.strip()] = value.strip()
    except Exception as e:
        print(f"Warning: Could not load secrets file: {e}")
    return secrets

auth_keys = load_secrets('/home/patakk/.zhongweb-secrets')


def remove_tones(pinyin):
    return re.sub(r'[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ]', lambda m: 'aeiouü'['āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ'.index(m.group()) // 4], pinyin)


def remove_all_numbers(pinyin):
    return re.sub(r'\d', '', pinyin)


def normalize_query(text):
    text = text.lower()
    text = text.strip(string.punctuation)
    text = lemmatizer.lemmatize(text)
    return text


@app.route('/search', methods=['GET'])
def search():
    api_key = request.headers.get('X-API-Key')
    if api_key != auth_keys.get('ZHONGWEN_SEARCH_KEY', ''):
        return jsonify({"error": "Unauthorized"}), 401
    query = request.args.get('query', '')
    query = query.strip().lower()
    results = []
    logger.debug("Received search request")
    logger.debug(f"Query: {query}")
    only_hanzi = all(regex.match(r'\p{Han}', char) for char in query if char.strip())
    if only_hanzi:
        exact_matches = []
        other_matches = []
        res = dictionary.get_examples(query)
        for fr in res:
            for idx, r in enumerate(res[fr]):
                if r['simplified'] == query:
                    exact_matches.append({'hanzi': r['simplified'], 'pinyin': r['pinyin'], 'english': r['definition'], 'match_type': 'hanzi', 'order': idx})
                elif r['traditional'] == query:
                    exact_matches.append({'hanzi': r['traditional'], 'pinyin': r['pinyin'], 'english': r['definition'], 'match_type': 'hanzi', 'order': idx})
                else:
                    if query == HanziConv.toSimplified(query):
                        other_matches.append({'hanzi': r['simplified'], 'pinyin': r['pinyin'], 'english': r['definition'], 'match_type': 'hanzi', 'order': idx})
                    else:
                        other_matches.append({'hanzi': r['traditional'], 'pinyin': r['pinyin'], 'english': r['definition'], 'match_type': 'hanzi', 'order': idx})
        results += exact_matches + other_matches
    else:
        res = dictionary.search_by_pinyin(query)
        hard_results = []
        for r in res:
            dd = dictionary.definition_lookup(r)
            for idx, d in enumerate(dd):
                order = idx
                piny_removed = remove_tones(d['pinyin'].lower())
                piny_removed_numbers = remove_all_numbers(d['pinyin'].lower())
                if d and query in piny_removed:
                    if 'surname' in d['definition']:
                        order = 1000
                    hard_results.append({'hanzi': r, 'pinyin': d['pinyin'], 'english': d['definition'], 'match_type': 'english', 'order': order})
                if d and query in piny_removed_numbers:
                    if 'surname' in d['definition']:
                        order = 1000
                    results.append({'hanzi': r, 'pinyin': d['pinyin'], 'english': d['definition'], 'match_type': 'english', 'order': order})
        if len(results) == 0:
            results = hard_results
        if len(results) == 0:
            original_query = query
            query = normalize_query(query)
            res = dictionary.search_by_english(query)
            for r in res:
                dd = dictionary.definition_lookup(r)
                for idx, d in enumerate(dd): # here i take into account the order of the definitions
                    if d and query in d['definition'].lower():
                        results.append({'hanzi': r, 'pinyin': d['pinyin'], 'english': d['definition'], 'match_type': 'english', 'order': idx})
            qwords = query.split(" ") 
            if len(qwords) > 1:
                fresults = []
                for r in results:
                    definition = r['english'].lower()
                    if all(qw in definition for qw in qwords):
                        if r not in fresults:
                            fresults.append(r)
                def order_key(r):
                    definition = r['english']
                    indices = [definition.find(qw) for qw in qwords]
                    return [i if i != -1 else float('inf') for i in indices]  # Handle missing words
                results = sorted(fresults, key=order_key)
    return jsonify(results)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8001, debug=True)