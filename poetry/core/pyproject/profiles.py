from pathlib import Path
from typing import List, MutableMapping, Callable, Dict, Any

from dataclasses import dataclass
from tomlkit.toml_document import TOMLDocument

from poetry.core.pyproject.properties import PropertiesTable
from poetry.core.toml import TOMLFile
import importlib.util


@dataclass
class ProfilesActivationData:
    manual_profiles: List[str]
    command_name: str


class _Properties:
    def __init__(self, props: Dict[str, Any]):
        self._props = props

    def __getitem__(self, item: str):
        return self._props[item]

    def __setitem__(self, key: str, value):
        self._props[key] = value


class _Execution:
    def __init__(self, activation: ProfilesActivationData):
        self._activation = activation

    @property
    def command_name(self):
        return self._activation.command_name


def _activate_manual_profile(profile_path: Path, props: _Properties, exec: _Execution):
    print(f"Activating Manual Profile: {profile_path.stem}")

    overrides = PropertiesTable.read(TOMLFile(profile_path).read()).properties
    props._props.update(overrides)


def _activate_automatic_profile(profile_path: Path, props: _Properties, exec: _Execution):
    print(f"Activating Automatic Profile: {profile_path.stem}")
    try:
        spec = importlib.util.spec_from_file_location("__PROFILE__", profile_path)
        module = importlib.util.module_from_spec(spec)
        module.props = props
        module.execution = exec

        spec.loader.exec_module(module)
    except Exception as e:
        raise RuntimeError(f"Error while evaluating profile: {profile_path.stem}") from e


def _apply_profile(project: MutableMapping, profile: Path):
    profile_data = TOMLFile(path=profile).read()

    def override_values(original: MutableMapping, override: MutableMapping):
        for k, v in override.items():
            if isinstance(v, MutableMapping) and isinstance(original.get(k), MutableMapping):
                override_values(original[k], v)
            else:
                original[k] = v

    override_values(project, profile_data)


def apply_profiles(
        project: TOMLDocument,
        profiles_dir: Path,
        activation_data: ProfilesActivationData
):
    properties = _Properties(PropertiesTable.read(project).properties)
    execution = _Execution(activation_data)

    # activate automatic profiles
    if profiles_dir.exists():
        for profile in profiles_dir.iterdir():
            if profile.name.endswith(".py"):
                _activate_automatic_profile(profile, properties, execution)

    # activate manual profiles
    for profile_name in activation_data.manual_profiles:
        profile = profiles_dir.joinpath(f"{profile_name}.toml")
        if not profile.exists():
            FileNotFoundError(f"could not find profile: {profile}")

        _activate_manual_profile(profile, properties, execution)

