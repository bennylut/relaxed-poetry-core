from contextlib import contextmanager
from io import UnsupportedOperation
from pathlib import Path
from typing import Optional, Dict, Any, Union, List, Sequence, Mapping, ContextManager

from poetry.core.pyproject.profiles import ProfilesActivationRequest, apply_profiles
from poetry.core.pyproject.properties import substitute_toml
from poetry.core.pyproject.tables import BuildSystem, PROPERTIES_TABLE, DEPENDENCIES_TABLE, SUBPROJECTS_TABLE, \
    POETRY_TABLE
from poetry.core.utils.props_ext import cached_property
import poetry.core.utils.toml as toml

_PY_PROJECT_CACHE = {}

_PROJECT_MANAGEMENT_FILES_SUBDIR = "etc/rp"

_PARENT_KEY = "tool.relaxed-poetry.parent-project".split(".")
_RELATIVE_PROFILES_DIR = f"{_PROJECT_MANAGEMENT_FILES_SUBDIR}/profiles"
_NAME_KEY = "tool.poetry.name".split(".")
_VERSION_KEY = "tool.poetry.version".split(".")


class Project:
    def __init__(
            self, data: Dict[str, Any], file: Optional[Path],
            parent: Optional["Project"] = None,
            profiles: Optional[ProfilesActivationRequest] = None):

        self._data = data
        self._file = file
        self.parent = parent

        self._is_parent = None
        self._build_system: Optional["BuildSystem"] = None
        self._profiles = profiles

    def __getitem__(self, item: Union[str, List[str]]) -> Any:
        """
        :param item: table key like "tool.relaxed-poetry.properties" or ["tool", "relaxed-poetry", "properties"]
        :return: the value if it exists otherwise None
        """

        return _get(self._data, item)

    def is_stored(self):
        return self.path is not None

    @property
    def path(self) -> Optional[Path]:
        return self._file

    @property
    def data(self) -> Dict[str, Any]:
        return self._data

    @property
    def name(self) -> str:
        return self[_NAME_KEY]

    @property
    def version(self) -> str:
        return self[_VERSION_KEY]

    @property
    def properties(self) -> Dict[str, Any]:
        return self[PROPERTIES_TABLE]

    # TODO: probably belongs to managed project
    @cached_property
    def project_management_files(self) -> Optional[Path]:
        if not self.is_stored():
            return None

        return self.path.parent / _PROJECT_MANAGEMENT_FILES_SUBDIR

    @cached_property
    def dependencies(self):
        return self[DEPENDENCIES_TABLE]

    def reload(self) -> None:
        # noinspection PyProtectedMember
        self._data = Project.read(self.path, self._profiles, invalidate_cache=True)._data

    @contextmanager
    def edit(self) -> ContextManager[Dict[str, Any]]:
        if self._file:
            data, dumps = toml.load(self._file)
            yield data
            self._file.write_text(dumps(data))
            self.reload()
        else:
            yield self._data

    @cached_property
    def requires_python(self):
        deps = self[DEPENDENCIES_TABLE] or {}
        return 'python' in deps

    @cached_property
    def sub_projects(self) -> Optional[Dict[str, "Project"]]:
        sub_project_defs: Dict[str, str] = self[SUBPROJECTS_TABLE]
        if not sub_project_defs:
            return {}

        return {name: Project.read(_relativize(self.path.parent, path) / "pyproject.toml", None) for name, path in
                sub_project_defs.items()}

    @property
    def build_system(self) -> "BuildSystem":
        from poetry.core.pyproject.tables import BuildSystem

        if self._build_system is None:
            build_backend = None
            requires = None

            container = self.data.get("build-system", {})
            self._build_system = BuildSystem(
                build_backend=container.get("build-backend", build_backend),
                requires=container.get("requires", requires),
            )

        return self._build_system

    @property
    def poetry_config(self) -> Optional[Dict[str, Any]]:
        return self[POETRY_TABLE]

    def is_parent(self):
        if self._is_parent is None:
            self._is_parent = self[SUBPROJECTS_TABLE] is not None

        return self._is_parent

    def lookup_sibling(self, name: str) -> Optional["Project"]:
        p = self
        while p:
            sibling = p.sub_projects.get(name)
            if sibling:
                return sibling
            p = p.parent

        return None

    def is_poetry_project(self) -> bool:
        return self[POETRY_TABLE] is not None

    @staticmethod
    def _lookup_parent(path: Path) -> Optional[Path]:
        path = path.absolute().resolve()
        p = path.parent
        while p:
            parent_project_file = p / "pyproject.toml"
            if parent_project_file.exists():
                parent_data,_ = toml.load(parent_project_file)
                sub_projects = _get(parent_data,SUBPROJECTS_TABLE)
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

        data,_ = toml.load(path)
        return _get(data, POETRY_TABLE) is not None

    @staticmethod
    def create(path: Union[Path, str], exists_ok: bool = False):
        if path.exists() and not exists_ok:
            raise FileExistsError()

        path.write_text('')
        return Project({}, path)

    @staticmethod
    def read(path: Union[Path, str], profiles: Optional[ProfilesActivationRequest] = None, *,
             invalidate_cache: bool = False) -> "Project":
        path = Path(path) if not isinstance(path, Path) else path

        cache_key = f"{path}/{profiles}"
        if invalidate_cache or not cache_key in _PY_PROJECT_CACHE:
            if path.exists():
                toml_data,_ = toml.load(path)
            else:
                toml_data = {}

            # first find parent if such exists..
            parent_path = _relativize(path, _get(toml_data, _PARENT_KEY))

            if not parent_path:
                parent_path = Project._lookup_parent(path.parent)

            parent = None
            if parent_path:
                parent = Project.read(parent_path, None)

            parent_props = (parent.properties if parent is not None else None) or {}
            my_props = {**parent_props, **(_get(toml_data, PROPERTIES_TABLE) or {})}

            # apply profiles if requested
            new_deps = {}
            if profiles:
                profiles_dirs = [path.parent / _RELATIVE_PROFILES_DIR]
                p = parent
                while p:
                    profiles_dirs.append(p.path.parent / _RELATIVE_PROFILES_DIR)
                    p = p.parent

                apply_profiles(my_props, new_deps, profiles_dirs, profiles)

            # add new dependencies
            deps = _put_if_absent(toml_data, DEPENDENCIES_TABLE, {})
            for name, spec in new_deps.items():
                if name not in deps:
                    deps[name] = spec
                else:
                    raise UnsupportedOperation(
                        f"profile attempted to overwrite dependency that was specified in pyproject: {name}")

            # substitute properties
            substitute_toml(toml_data, my_props)

            _PY_PROJECT_CACHE[cache_key] = Project(toml_data, path, parent, profiles)

        return _PY_PROJECT_CACHE[cache_key]

    @classmethod
    def new_in_mem(
            cls, name: str,
            version: str = "0.0.1", authors: List[str] = None):

        data = {
            "tool": {
                "poetry": {
                    "name": name,
                    "version": version,
                    "authors": authors or []
                }}}

        return Project(data, None, None, None)


def _relativize(path: Path, relative: Optional[str]):
    if not relative:
        return None

    p = Path(relative)
    if p.is_absolute():
        return p.resolve()

    return (path / p).resolve()


def _put_if_absent(d: Dict[str, Any], path: Sequence[str], value: Any) -> Any:
    r = d
    for p in path[:-1]:
        try:
            r = r[p]
        except KeyError:
            r[p] = {}
            r = r[p]

    lp = path[-1]
    if lp not in r:
        r[lp] = value

    return r[lp]


def _get(data: Dict[str, Any], item: Union[str, List[str]]):
    if isinstance(item, str):
        item = list(toml.key2path(item))

    r = data
    for p in item:
        if not r:
            return None
        if not isinstance(r, Mapping):
            raise ValueError(f"in path: {item}, {p} does not lead to dict")

        r = r.get(p)

    return r
