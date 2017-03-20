# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import third_party.parse_events


def set_in_nested_dict(dictionary, path, value):
    keys = path.split('/')
    for k in keys[:-1]:
        dictionary = dictionary[k]
    dictionary[keys[-1]] = value


def extract_events_data(e):
    props = {
        # source_field: target_field

        # TODO: extract description.
        "description": "description",
        "expiry_version": "expiry_version",
        "expiry_day": "expiry_day",
        "cpp_guard": "cpp_guard",

        "methods": "details/methods",
        "objects": "details/objects",
        "record_in_processes": "details/record_in_processes",
        # TODO: extract key descriptions too.
        "extra_keys": "details/extra_keys",
    }

    defaults = {
        "expiry_version": "never",
        "expiry_day": "never",
        "name": e.methods[0],
        "description": "<TODO>",
        "cpp_guard": None,
    }

    data = {
        "details": {}
    }

    for source_field, target_field in props.iteritems():
        value = None
        if getattr(e, source_field, None):
            value = getattr(e, source_field)
        elif source_field in defaults:
            value = defaults[source_field]
        set_in_nested_dict(data, target_field, value)

    # We only care about opt-out or opt-in really.
    optout = getattr(e, "dataset", "").endswith('_OPTOUT')
    data["optout"] = optout

    # Normalize some field values.
    if data["expiry_version"] == "default":
        data["expiry_version"] = "never"

    return data


class EventsParser:
    def parse(self, filenames, version):
        # Events.yaml had a format change in 53, see bug 1329620.
        # We don't have important event usage yet, so lets skip
        # backwards compatibility for now.
        if int(version) < 53:
            return {}

        if len(filenames) > 1:
            raise Exception('We don\'t support loading from more than one file.')

        events = third_party.parse_events.load_events(filenames[0], strict_type_checks=False)

        # Get the probe information in a standard format.
        out = {}
        for e in events:
            full_name = e.category + "." + e.methods[0]
            if getattr(e, "name", None):
                full_name += "#" + e.name
            out[full_name] = extract_events_data(e)

        return out
