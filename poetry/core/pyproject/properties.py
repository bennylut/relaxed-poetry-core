import json
from typing import Dict, Any

import tomlkit.items
from tomlkit.toml_document import TOMLDocument
import os


def substitute_toml(doc: TOMLDocument, props: Dict[str, Any]) -> TOMLDocument:

    # first override table keys with environment variables
    # this means that environment variables overrides profiles changes
    properties = {pkey: _merge_env(pkey, pval) for pkey, pval in props.items()}
    # next try to perform substitution within the properties themselves
    properties = _substitute_properties(properties)
    # now that we resolved all the property values we can find the document itself
    return tomlkit.items.item(_substitute_obj(properties, doc))


def _merge_env(property: str, default_value: Any) -> Any:
    env_value = os.environ.get(property.replace('-','_'))
    if env_value is None:
        return default_value
    return json.loads(env_value)



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
        return {k: _substitute_obj(props, v) for k, v in o.items()}
    elif isinstance(o, str):
        s = o.strip()
        if len(s) > 1 and s[0] == '$':
            return props.get(s[1:], s)
        return o
    else:
        return o
