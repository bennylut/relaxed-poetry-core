from pathlib import Path
from typing import TYPE_CHECKING, List, Dict
from typing import Any
from typing import Optional
from typing import Union

from poetry.core.pyproject.profiles import ProfilesActivationData, apply_profiles
from poetry.core.pyproject.properties import substitute_toml
from poetry.core.utils.collections_ext import nesteddict_lookup, nesteddict_put, nesteddict_put_if_absent
from tomlkit.toml_document import TOMLDocument
from poetry.core.toml import TOMLFile
from poetry.core.pyproject.tables import BuildSystem, PROPERTIES_TABLE, POETRY_TABLE, SUBPROJECTS_TABLE, \
    DEPENDENCIES_TABLE
from poetry.core.utils.props_ext import cached_property
from tomlkit.items import Item

if TYPE_CHECKING:
    from tomlkit.container import Container

_PY_PROJECT_CACHE = {}

_PROJECT_MANAGEMENT_FILES_SUBDIR = "etc/rp"

_PARENT_KEY = "tool.relaxed-poetry.parent-project".split(".")
_RELATIVE_PROFILES_DIR = f"{_PROJECT_MANAGEMENT_FILES_SUBDIR}/profiles"
_NAME_KEY = "tool.poetry.name".split(".")
_VERSION_KEY = "tool.poetry.version".split(".")


class PyProject:
    def __init__(self, path: Path, data: TOMLDocument, parent: Optional["PyProject"]):
        self._file = TOMLFile(path=path)  # here to support original poetry interface

        self.path = path
        self.data = data
        self.parent = parent

        self._is_parent = None
        self._build_system: Optional["BuildSystem"] = None

    @property
    def name(self) -> str:
        return self[_NAME_KEY]

    @property
    def version(self) -> str:
        return self[_VERSION_KEY]

    @property
    def file(self) -> "TOMLFile":
        return self._file

    @property
    def properties(self) -> Dict[str, Any]:
        return self[PROPERTIES_TABLE]

    @cached_property
    def project_management_files(self) -> Path:
        return self.path.parent / _PROJECT_MANAGEMENT_FILES_SUBDIR

    @cached_property
    def requires_python(self):
        deps = self[DEPENDENCIES_TABLE] or {}
        return 'python' in deps

    @cached_property
    def sub_projects(self) -> Optional[Dict[str, "PyProject"]]:
        sub_project_defs: Dict[str, str] = self[SUBPROJECTS_TABLE]
        if not sub_project_defs:
            return {}

        return {name: PyProject.read(_relativize(self.path.parent, path) / "pyproject.toml", None) for name, path in
                sub_project_defs.items()}

    @property
    def build_system(self) -> "BuildSystem":
        from poetry.core.pyproject.tables import BuildSystem

        if self._build_system is None:
            build_backend = None
            requires = None

            if not self._file.exists():
                build_backend = "poetry.core.masonry.api"
                requires = ["poetry-core"]

            container = self.data.get("build-system", {})
            self._build_system = BuildSystem(
                build_backend=container.get("build-backend", build_backend),
                requires=container.get("requires", requires),
            )

        return self._build_system

    @property
    def poetry_config(self) -> Optional[Union["Item", "Container"]]:
        config = self[POETRY_TABLE]
        if config is None:
            from poetry.core.pyproject.exceptions import PyProjectException
            raise PyProjectException(f"[tool.poetry] section not found in {self._file}")

        return config

    def is_parent(self):
        if self._is_parent is None:
            self._is_parent = self[SUBPROJECTS_TABLE] is not None

        return self._is_parent

    def lookup_sibling(self, name: str) -> Optional["PyProject"]:
        p = self
        while p:
            sibling = p.sub_projects.get(name)
            if sibling:
                return sibling
            p = p.parent

        return None

    def is_poetry_project(self) -> bool:
        return self[POETRY_TABLE] is not None

    def __getitem__(self, item: Union[str, List[str]]) -> Any:
        """
        :param item: table key like "tool.relaxed-poetry.properties" or ["tool", "relaxed-poetry", "properties"]
        :return: the table if it exists otherwise None
        """
        path = item.split(".") if not isinstance(item, List) else item
        return nesteddict_lookup(self.data, path)

    def __setitem__(self, key: Union[str, List[str]], value: Dict):
        """
        :param key: table key like "tool.relaxed-poetry.properties" or ["tool", "relaxed-poetry", "properties"]
        :param value: a dictionary to set as the table content
        """
        path = key.split(".") if not isinstance(key, List) else key
        nesteddict_put(self.data, path, value)

    def get_or_create_table(self, table_key: Union[str, List[str]]):
        """
        :param table_key: table key like "tool.relaxed-poetry.properties" or ["tool", "relaxed-poetry", "properties"]
        :return: the existing table dictionary if it exists, otherwise, add a new table dictionary and return it
        """
        path = table_key.split(".") if not isinstance(table_key, List) else table_key
        result = nesteddict_put_if_absent(self.data, path, {})
        # result = nesteddict_lookup(self.data, path)
        if result and not isinstance(result, dict):
            raise ValueError(f"{table_key} is not a table")

        # if not result:
        #     result = table()
        #     self.data[".".join(path)] = result
        #
        return result

    def save(self) -> None:
        """
        save the pyproject changes back to the file it was read from
        """
        from tomlkit.container import Container

        data = self.data

        if self._build_system is not None:
            if "build-system" not in data:
                data["build-system"] = Container()

            data["build-system"]["requires"] = self._build_system.requires
            data["build-system"]["build-backend"] = self._build_system.build_backend

        self.file.write(data=data)

    def reload(self) -> None:
        self.data = None
        self._build_system = None

    @staticmethod
    def _lookup_parent(path: Path) -> Optional[Path]:
        path = path.absolute().resolve()
        p = path.parent
        while p:
            parent_project_file = p / "pyproject.toml"
            if parent_project_file.exists():
                parent_data = TOMLFile(path=parent_project_file).read()
                sub_projects = nesteddict_lookup(parent_data, SUBPROJECTS_TABLE, None)
                if sub_projects:
                    for sub_project_path in sub_projects.values():
                        sub_project_path = _relativize(p, sub_project_path)
                        if sub_project_path == path:
                            return parent_project_file

            p = p.parent if p.parent != p else None

        return None

    @staticmethod
    def has_poetry_section(path: Path) -> bool:
        if not path.exists():
            return False

        data = TOMLFile(path=path).read()
        return nesteddict_lookup(data, POETRY_TABLE) is not None

    @staticmethod
    def read(path: Union[Path, str], profiles: Optional[ProfilesActivationData]) -> "PyProject":
        path = Path(path) if not isinstance(path, Path) else path

        cache_key = f"{path}/{profiles}"
        if not cache_key in _PY_PROJECT_CACHE:
            data = TOMLFile(path=path).read()

            # first find parent if such exists..
            parent_path = _relativize(path, nesteddict_lookup(data, _PARENT_KEY, None))

            if not parent_path:
                parent_path = PyProject._lookup_parent(path.parent)

            parent = None
            if parent_path:
                parent = PyProject.read(parent_path, None)

            parent_props = (parent.properties if parent is not None else None) or {}
            my_props = {**parent_props, **nesteddict_lookup(data, PROPERTIES_TABLE, {})}

            # apply profiles if requested
            if profiles:
                profiles_dirs = [path.parent / _RELATIVE_PROFILES_DIR]
                p = parent
                while p:
                    profiles_dirs.append(p.path.parent / _RELATIVE_PROFILES_DIR)
                    p = p.parent

                apply_profiles(my_props, profiles_dirs, profiles)

            # substitute properties
            data = substitute_toml(data, my_props)
            _PY_PROJECT_CACHE[cache_key] = PyProject(path, data, parent)

        return _PY_PROJECT_CACHE[cache_key]


def _relativize(path: Path, relative: Optional[str]):
    if not relative:
        return None

    p = Path(relative)
    if p.is_absolute():
        return p.resolve()

    return (path / p).resolve()
