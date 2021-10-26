import importlib.util
from functools import reduce
from io import UnsupportedOperation
from pathlib import Path
from typing import List, Dict, Any

from dataclasses import dataclass

from poetry.core.pyproject.tables import PROPERTIES_TABLE, DEPENDENCIES_TABLE
from poetry.core.utils import toml

PROFILE_TABLE = "tool.relaxed-poetry.profile".split(".")


@dataclass
class ProfilesActivationRequest:
    requested_profiles: Dict[str, bool]
    command_name: str

    @classmethod
    def from_commandline(cls, command: str, profiles: List[str]) -> "ProfilesActivationRequest":
        requested_profiles = {}
        for profile in profiles:
            if profile.startswith("!"):
                requested_profiles[profile[1:]] = False
            else:
                requested_profiles[profile] = True

        return cls(requested_profiles, command)


class _Properties:
    def __init__(self, props: Dict[str, Any]):
        self._props = props

    def __getitem__(self, item: str):
        return self._props[item]

    def __setitem__(self, key: str, value):
        self._props[key] = value

    def update(self, props: Dict[str, Any]):
        self._props.update(props)


class _Dependencies:
    def __init__(self, new_deps: Dict[str, Any]):
        self.new_deps: Dict[str, Any] = new_deps

    def add(self, name: str, specification: Any):
        self.new_deps[name] = specification


class _Execution:
    def __init__(self, activation: ProfilesActivationRequest):
        self._activation = activation

    @property
    def command_name(self):
        return self._activation.command_name


def _should_activate(activate_spec: Any, exec: _Execution):
    if isinstance(activate_spec, bool):
        return activate_spec
    elif isinstance(activate_spec, dict):
        if 'commands' in activate_spec:
            commands: List[str] = activate_spec['commands']
            if isinstance(commands, str):
                commands = [commands]

            default_accept = '*' in commands

            for command in commands:
                accept = default_accept

                if command == '*':
                    continue

                if command.startswith('!'):
                    accept = False
                    command = command[1:]

                if exec.command_name == command:
                    return accept

            return False

    raise UnsupportedOperation(f"unsupported profile activation spec: {activate_spec}")


def _activate_static_profile(profile_path: Path, props: _Properties, deps: _Dependencies, exec: _Execution):
    profile_data,_ = toml.load(profile_path)

    profile_def = _lookup(profile_data, PROFILE_TABLE) or {}

    # check activation:
    activate_spec = profile_def.get('activate', False)
    if not _should_activate(activate_spec, exec):
        return

    print(f"Activating Static Profile: {profile_path.stem}")

    props_overrides = _lookup(profile_data, PROPERTIES_TABLE) or {}
    props.update(props_overrides)

    new_deps = _lookup(profile_data, DEPENDENCIES_TABLE) or {}
    for name, spec in new_deps.items():
        deps.add(name, spec)


def _activate_dynamic_profile(profile_path: Path, props: _Properties, dependencies: _Dependencies, exec: _Execution):
    print(f"Activating Dynamic Profile: {profile_path.stem}")
    try:
        spec = importlib.util.spec_from_file_location("__PROFILE__", profile_path)
        module = importlib.util.module_from_spec(spec)
        module.props = props
        module.execution = exec
        module.deps = dependencies

        spec.loader.exec_module(module)
    except Exception as e:
        raise RuntimeError(f"Error while evaluating profile: {profile_path.stem}") from e


def apply_profiles(
        properties: Dict[str, Any],
        new_deps: Dict[str, Any],
        profiles_dirs: List[Path],
        activation_data: ProfilesActivationRequest
):
    dependencies = _Dependencies(new_deps)
    properties = _Properties(properties)
    execution = _Execution(activation_data)

    # activate automatic profiles
    for profiles_dir in profiles_dirs:
        if profiles_dir.exists():
            for profile in profiles_dir.iterdir():
                if activation_data.requested_profiles.get(profile.stem, True):
                    if profile.name.endswith(".py"):
                        _activate_dynamic_profile(profile, properties, dependencies, execution)
                    elif profile.name.endswith(".toml"):
                        _activate_static_profile(profile, properties, dependencies, execution)


def _lookup(d: Dict, path: List[str]) -> Any:
    try:
        return reduce(lambda m, k: m[k], path, d)
    except KeyError:
        return None
