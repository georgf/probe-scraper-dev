# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import os
import json
import tempfile
import requests
import requests_cache

requests_cache.install_cache('probe_scraper_cache')
from collections import defaultdict


REGISTRY_FILES = {
    'histograms': [
        'toolkit/components/telemetry/Histograms.json',
        'dom/base/UseCounters.conf',
        'dom/base/nsDeprecatedOperationList.h',
    ],
    'scalars': [
        'toolkit/components/telemetry/Scalars.yaml',
    ],
    'events': [
        'toolkit/components/telemetry/Events.yaml',
    ],
}

CHANNELS = {
    'nightly': {
        'base_uri': 'https://hg.mozilla.org/mozilla-central/',
        'tag_regex': '^FIREFOX_AURORA_[0-9]+_BASE$',
    },
    'aurora': {
        'base_uri': 'https://hg.mozilla.org/releases/mozilla-aurora/',
        'tag_regex': '^FIREFOX_AURORA_[0-9]+_BASE$',
    },
    'beta': {
        'base_uri': 'https://hg.mozilla.org/releases/mozilla-beta/',
        'tag_regex': '^FIREFOX_BETA_[0-9]+_BASE$',
    },
    'release': {
        'base_uri': 'https://hg.mozilla.org/releases/mozilla-release/',
        'tag_regex': '^FIREFOX_[0-9]+_0_RELEASE$',
    },
}

MIN_FIREFOX_VERSION = 30
ERROR_CACHE_FILENAME = 'probe_scraper_errors_cache.json'


def load_tags(channel):
    uri = CHANNELS[channel]['base_uri'] + "json-tags"
    r = requests.get(uri)
    if r.status_code != requests.codes.ok:
        raise Exception("Request returned status " + str(r.status_code) + " for " + uri)

    ctype = r.headers['content-type']
    if ctype != 'application/json':
        raise Exception("Request didn't return JSON: " + ctype + " (" + uri + ")")

    data = r.json()
    if not data or "tags" not in data:
        raise Exception("Result JSON doesn't have the right format for " + uri)

    return data["tags"]


def extract_tag_data(tags, channel):
    tag_regex = CHANNELS[channel]['tag_regex']
    tags = filter(lambda t: re.match(tag_regex, t["tag"]), tags)
    results = []

    for tag in tags:
        version = ""
        if channel == "release":
            version = tag["tag"].split('_')[1]
        elif channel in ["beta", "aurora", "nightly"]:
            version = tag["tag"].split('_')[2]
        else:
            raise Exception("Unsupported channel " + channel)

        # Nightly only has tags of the type FIREFOX_AURORA_NN_BASE.
        if channel == "nightly":
            version = str(int(version) + 1)

        if int(version) >= MIN_FIREFOX_VERSION:
            results.append({
                "node": tag["node"],
                "version": version,
            })

    results = sorted(results, key=lambda r: int(r["version"]))
    return results


def download_files(channel, node, temp_dir, error_cache):
    base_uri = CHANNELS[channel]['base_uri'] + 'raw-file/' + node + '/'
    node_path = os.path.join(temp_dir, 'hg', node)

    results = {}

    def add_result(ptype, disk_path):
        if ptype not in results:
            results[ptype] = []
        results[ptype].append(disk_path)

    all_files = [(k, x) for k, l in REGISTRY_FILES.items() for x in l]
    for (ptype, rel_path) in all_files:
        disk_path = os.path.join(node_path, rel_path)
        if os.path.exists(disk_path):
            add_result(ptype, disk_path)
            continue

        uri = base_uri + rel_path
        # requests_cache doesn't cache on error status codes.
        # We just use our own cache for these for now.
        if uri in error_cache:
            continue

        req = requests.get(uri)
        if req.status_code != requests.codes.ok:
            if os.path.basename(rel_path) == 'Histograms.json':
                raise Exception("Request returned status " + str(req.status_code) + " for " + uri)
            else:
                error_cache[uri] = req.status_code
                continue

        dir = os.path.split(disk_path)[0]
        if not os.path.exists(dir):
            os.makedirs(dir)
        with open(disk_path, 'wb') as f:
            for chunk in req.iter_content(chunk_size=128):
                f.write(chunk)

        add_result(ptype, disk_path)

    return results


def load_error_cache():
    if not os.path.exists(ERROR_CACHE_FILENAME):
        return {}
    with open(ERROR_CACHE_FILENAME, 'r') as f:
        return json.load(f)


def save_error_cache(error_cache):
        with open(ERROR_CACHE_FILENAME, 'w') as f:
            json.dump(error_cache, f, sort_keys=True, indent=2)


# returns:
# node_id -> {
#    channels: [channel_name, ...],
#    version: string,
#    registries: {
#      histograms: [path, ...]
#      events: [path, ...]
#      scalars: [path, ...]
#    }
# }
def scrape(dir=tempfile.mkdtemp()):
    error_cache = load_error_cache()
    results = defaultdict(dict)

    for channel in CHANNELS.iterkeys():
        tags = load_tags(channel)
        versions = extract_tag_data(tags, channel)
        save_error_cache(error_cache)

        print "\n" + channel + " - extracted version data:"
        for v in versions:
            print "  " + str(v)

        print "\n" + channel + " - loading files:"
        for v in versions:
            print "  from: " + str(v)
            files = download_files(channel, v['node'], dir, error_cache)
            results[channel][v['node']] = {
                'version': v['version'],
                'registries': files,
            }
            save_error_cache(error_cache)

    return results


if __name__ == "__main__":
    results = scrape('_tmp')

    if False:
        for node, data in results.iteritems():
            print data['channel'] + ", " + data['version'] + ", " + node + ":"
            for ptype, paths in data['registries'].iteritems():
                print "  " + ptype + ":"
                print "    " + "\n    ".join(paths)
