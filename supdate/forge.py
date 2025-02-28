import subprocess
from enum import Enum
from pathlib import Path
from typing import Optional

import attr
import requests

from .profile import Profile, InstallProfile
from .utils import load_json_from_jar as in_jar
from .vanilla import fetch_vanilla_profile

VERSION_JSON = "version.json"
INSTALL_JSON = "install_profile.json"

FORGE_MAVEN = "files.minecraftforge.net/maven"
FORGE_URI = "net/minecraftforge/forge"


class ForgeType(Enum):
    INSTALLER = "installer"
    UNIVERSAL = "universal"


@attr.s(auto_attribs=True)
class ForgeBase:
    mc_version: str
    forge_version: str
    directory: Path

    form: str
    type: ForgeType

    @property
    def vanilla_version(self):
        return self.mc_version

    @property
    def _basic_name(self):
        return self.form.replace("{mc}", self.mc_version)       \
                        .replace("{forge}", self.forge_version)

    @property
    def standard_name(self):
        return self._basic_name.replace("(-{type})", "")

    @property
    def full_name(self):
        return self._basic_name.replace("(-{type})", f"-{self.type.value}")

    @property
    def jar(self) -> Path:
        return self.directory / f"{self.full_name}.jar"

    @property
    def universal(self):
        std_file = self.directory / f"{self.standard_name}.jar"
        if std_file.exists():
            return std_file

        univ_file = self.directory / f"{self._basic_name}.jar".replace("(-{type})", f"-{ForgeType.UNIVERSAL.value}")
        if univ_file.exists():
            return univ_file

        raise FileNotFoundError("Forge universal jar file has not been found.")

    def load_version(self):
        return Profile.from_json(in_jar(self.jar, VERSION_JSON))

    @property
    def forge_profile(self) -> Profile:
        return self.load_version()

    @property
    def vanilla_profile(self) -> Profile:
        return fetch_vanilla_profile(self.mc_version)

    @property
    def full_profile(self) -> Profile:
        fp = self.forge_profile
        assert fp.inheritsFrom == self.mc_version, (
            fp.inheritsFrom, self.mc_version
        )

        profile = self.vanilla_profile
        profile.merge(fp)
        profile.inheritsFrom = None

        return profile

    @property
    def url(self):
        return f"https://{FORGE_MAVEN}/{FORGE_URI}/{self.standard_name}/{self.full_name}.jar"


@attr.s(auto_attribs=True)
class ForgeInstaller(ForgeBase):
    type: ForgeType = ForgeType.INSTALLER

    @property
    def install_profile(self) -> Optional[InstallProfile]:
        try:
            return InstallProfile.from_json(in_jar(self.jar, INSTALL_JSON))
        except FileNotFoundError:
            return None

    def load_version(self):
        # installer.jar에는 version.json 파일이 존재하지 않습니다.
        # universal을 참조하도록 해주세요.
        return Profile.from_json(in_jar(self.universal, VERSION_JSON))

    def download_forge(self):
        res = requests.get(self.url, stream=True)
        res.raise_for_status()

        with self.jar.open('wb') as fp:
            for chunk in res:
                fp.write(chunk)

    def install(self, *, auto_download=True):
        if auto_download and not self.jar.exists():
            self.download_forge()

        subprocess.check_call(["java", "-jar", str(self.jar.absolute()), "--installServer"], cwd=str(self.directory))
