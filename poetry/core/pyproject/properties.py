from typing import Dict, Any, Optional

import tomlkit.items
from dataclasses import dataclass
from tomlkit.toml_document import TOMLDocument
import os


def substitute_toml(doc: TOMLDocument) -> TOMLDocument:
    table = _PropertiesTable.read(doc)

    # first override table keys via environment variables
    properties = {pkey: os.environ.get(pkey, pval) for pkey, pval in table.properties.items()}
    # next try to perform substitution within the properties themselves
    properties = _substitute_properties(properties)
    # now that we resolved all the property values we can resolve the document itself
    return tomlkit.items.item(_substitute_obj(properties, doc))


@dataclass
class _PropertiesTable:
    properties: Dict[str, Any]

    @staticmethod
    def read(doc: TOMLDocument) -> "_PropertiesTable":
        try:
            properties = doc["tool"]["relaxed"]["poetry"]["properties"] or {}
        except KeyError:
            properties = {}

        return _PropertiesTable(properties)


def _substitute_properties(properties: Dict[str, Any]) -> Dict[str, Any]:
    sub_properties = {}
    cur_round_unsub_keys = {p for p in properties.keys()}
    cur_round_changes = 0
    next_round_unsub_keys = set()

    while True:
        for pkey in cur_round_unsub_keys:
            pval = properties[pkey]
            try:
                sub_properties[pkey] = _substitute_obj(sub_properties, pval)
                cur_round_changes += 1
            except KeyError:
                next_round_unsub_keys.add(pkey)

        if len(next_round_unsub_keys) == 0:
            break

        if cur_round_changes == 0:
            raise ValueError(f"Circular property references detected: {next_round_unsub_keys}")

        cur_round_changes = 0
        cur_round_unsub_keys = next_round_unsub_keys
        next_round_unsub_keys = set()

    return sub_properties


def _substitute_obj(props: Dict[str, Any], o: Any) -> Any:
    if isinstance(o, list):
        return [_substitute_obj(props, item) for item in o]
    elif isinstance(o, dict):
        if len(o) == 1 and "prop" in o:
            return props[o["prop"]]

        return {k: _substitute_obj(props, v) for k, v in o.items()}
    elif isinstance(o, str):
        s = o.strip()
        if len(s) > 1 and s[0] == '$':
            return props[s[1:]]
        return o
    else:
        return o


