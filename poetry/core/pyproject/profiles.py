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
    for manually_activated_profile in manually_activated_profiles:
        profile_path = profiles_dir.joinpath(manually_activated_profile + ".toml")
        if not profile_path.exists():
            raise ValueError(f"cannot activate requested profile, {profile_path} not found")

        _apply_profile(project, profile_path)

    for profile_file in profiles_dir.iterdir():
        if profile_file.name.endswith(".py"):
            import_profile(profile_file)(project)


if __name__ == '__main__':
    from poetry.core.pyproject.toml import PyProjectTOML

    proj = PyProjectTOML("/home/bennyl/projects/poetry-core/workspace/test.toml")
    apply_profiles(proj.data, Path("/home/bennyl/projects/poetry-core/workspace/profiles"), ["xxx", "yyy"])

    print(proj.data)
