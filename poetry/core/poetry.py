from __future__ import absolute_import
from __future__ import unicode_literals

from typing import TYPE_CHECKING
from typing import Any
from poetry.core.pyproject.toml import PyProject


if TYPE_CHECKING:
    from pathlib import Path

    from poetry.core.packages import ProjectPackage  # noqa
    from poetry.core.pyproject.toml import PyProject  # noqa
    from poetry.core.pyproject.toml import PyProjectTOMLFile  # noqa


class Poetry(object):
    def __init__(
        self,
        file: "Path",
        pyproject: PyProject,
        package: "ProjectPackage",
    ) -> None:
        from poetry.core.pyproject.toml import PyProject  # noqa

        self._pyproject = pyproject
        self._package = package
        self._local_config = pyproject.poetry_config

    @property
    def pyproject(self) -> "PyProject":
        return self._pyproject

    @property
    def file(self) -> "PyProjectTOMLFile":
        return self._pyproject.file

    @property
    def package(self) -> "ProjectPackage":
        return self._package

    @property
    def local_config(self) -> dict:
        return self._local_config

    def get_project_config(self, config: str, default: Any = None) -> Any:
        return self._local_config.get("config", {}).get(config, default)

