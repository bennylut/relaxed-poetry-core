from __future__ import absolute_import
from __future__ import unicode_literals

from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

from poetry.core.pyproject.project import Project

if TYPE_CHECKING:
    from poetry.core.packages.project_package import ProjectPackage  # noqa


class Poetry(object):
    def __init__(
        self,
        pyproject: Project,
        package: "ProjectPackage",
    ) -> None:
        self._pyproject = pyproject
        self._package = package
        self._local_config = pyproject.poetry_config

    @property
    def pyproject(self) -> "Project":
        return self._pyproject

    @property
    def file(self) -> Path:
        return self._pyproject.path

    @property
    def package(self) -> "ProjectPackage":
        return self._package

    @property
    def local_config(self) -> dict:
        return self._local_config

    def get_project_config(self, config: str, default: Any = None) -> Any:
        return self._local_config.get("config", {}).get(config, default)

