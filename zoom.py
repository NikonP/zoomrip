import re
from typing import Optional, Tuple

import httpx
import websockets

from constants import auth_re, ts_re
from exceptions import WrongPasswordError

from loguru import logger


class Zoom:
    @logger.catch
    def __init__(self, url, username: str):
        self.username = username
        self.host = "/".join(url.split("/")[:3])

        self.client = httpx.AsyncClient(verify=False)

    @logger.catch
    async def join_meeting(
        self, meeting_id: int, password: Optional[str] = ""
    ) -> Optional[websockets.client.Connect]:
        logger.debug("Joining a meeting")
        self.client.cookies.set("wc_join", f"{meeting_id}*{self.username}")
        self.client.cookies.set("wc_dn", self.username)

        configuration = await self._get_configuration(meeting_id, password)

        if configuration is None:
            raise WrongPasswordError("Wrong password")

        best_server = await self._find_best_server(meeting_id)
        connection = await self._connect(
            meeting_id, best_server, configuration, password
        )
        return await self._websocket_connect(connection)

    @logger.catch
    async def _get_configuration(self, meeting_id: int, password: str) -> Optional[str]:
        join_request = await self.client.get(
            f"{self.host}/wc/{meeting_id}/join",
            params={
                "pwd": password,
                "track_id": "",
                "jmf_code": "",
                "meeting_result": "",
            },
        )
        if ">Meeting password is wrong. Please re-enter." not in join_request.text:
            return join_request.text
        else:
            raise WrongPasswordError("Wrong meeting password")

    @logger.catch
    async def _find_best_server(self, meeting_id: int) -> dict:
        best_server = (await self.client.get(
            f"https://rwcff.zoom.us/wc/ping/{meeting_id}"
        )).json()
        logger.debug(f"Best server: {best_server['rwg']}")
        return best_server

    @logger.catch
    async def _connect(
        self,
        meeting_id: int,
        best_server: dict,
        configuration: str,
        password: Optional[str] = "",
    ):
        auth, ts = self._extract_config_variables(configuration)

        logger.debug(f"Auth: {auth}, TS: {ts}")

        return await self.client.get(
            f"https://{best_server['rwg']}/webclient/{meeting_id}",
            params={
                "dn": self.username,
                "ts": ts,
                "auth": auth,
                "mpwd": password or "",
                "rwcAuth": best_server["rwcAuth"],
            },
        )

    @staticmethod
    @logger.catch
    async def _websocket_connect(connection) -> websockets.client.Connect:
        logger.debug(f"WebSocket connection url: {str(connection.url)}")
        return websockets.connect(str(connection.url).replace("https", "wss"))

    @staticmethod
    @logger.catch
    def _extract_config_variables(configuration: str) -> Tuple[str, str]:
        auth = re.search(auth_re, configuration).group(1)
        ts = re.search(ts_re, configuration).group(1)
        return auth, ts
