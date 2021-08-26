from pathlib import Path
from typing import List, MutableMapping, Callable
from tomlkit.toml_document import TOMLDocument

from poetry.core.toml import TOMLFile
import importlib.util


def _apply_profile(project: MutableMapping, profile: Path):
    profile_data = TOMLFile(path=profile).read()

    def override_values(original: MutableMapping, override: MutableMapping):
        for k, v in override.items():
            if isinstance(v, MutableMapping) and isinstance(original.get(k), MutableMapping):
                override_values(original[k], v)
            else:
                original[k] = v

    override_values(project, profile_data)


def import_profile(profile_path: Path) -> Callable[[MutableMapping], None]:
    spec = importlib.util.spec_from_file_location("__PROFILE__", profile_path)
    profile_code = spec.loader.exec_module(importlib.util.module_from_spec(spec))
    return profile_code.apply_profile


def apply_profiles(
        project: TOMLDocument,
        profiles_dir: Path,
        manually_activated_profiles: List[str]
):
    try:
        profile_mapping = project["tool"]["relaxed-poetry"]["profiles"]
    except KeyError:
        profile_mapping = {}

    activated_profiles = set()

    for manually_activated_profile in manually_activated_profiles:
        optional = manually_activated_profile[0] == '?'
        if optional:
            manually_activated_profile = manually_activated_profile[1:]

        profiles_to_activate = profile_mapping.get(manually_activated_profile, manually_activated_profile)
        if not isinstance(profiles_to_activate, list):
            profiles_to_activate = [profiles_to_activate]

        for profile in profiles_to_activate:
            if profile in activated_profiles:
                continue

            activated_profiles.add(profile)

            profile_path = profiles_dir.joinpath(profile + ".toml")
            if not profile_path.exists():
                if not optional:
                    raise ValueError(f"cannot activate requested profile, {profile_path} not found")
                else:
                    continue

            print(f"Activating profile: {profile}")
            _apply_profile(project, profile_path)

    for profile_file in profiles_dir.iterdir():
        if profile_file.name.endswith(".py"):
            try:
                import_profile(profile_file)(project)
            except Exception as e:
                raise RuntimeError(f"Error while evaluating profile: {profile_file.stem}") from e


if __name__ == '__main__':
    from poetry.core.pyproject.toml import PyProjectTOML

    proj = PyProjectTOML("/home/bennyl/projects/poetry-core/workspace/test.toml")
    apply_profiles(proj.data, Path("/home/bennyl/projects/poetry-core/workspace/profiles"), ["xxx", "yyy"])

    print(proj.data)
