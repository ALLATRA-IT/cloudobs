import re

# import aiohttp
# import asyncio
# from grequests import async
#
# async def request(requests_, method):
#     responses_ = {}
#     async with aiohttp.ClientSession() as session:
#         for lang, request_ in requests_.items():
#             if method == 'GET':
#                 async with session.get(request_) as resp:
#                     response_ = await resp.read()
#                     responses_[lang] = response_
#             elif method == 'POST':
#                 async with session.post(request_) as resp:
#                     response_ = await resp.read()
#                     responses_[lang] = response_


def validate_init_params(server_langs):
    for lang, lang_info in server_langs.items():
        for attr in ["host_url", "websocket_port", "password", "original_media_url"]:
            if attr not in lang_info:
                return ExecutionStatus(status=False, message=f"Please specify `{attr}` attribute for lang '{lang}'")
        websockets_port = lang_info["websocket_port"]
        # TODO: validate `obs_host`
        if not str(websockets_port).isdigit():
            return ExecutionStatus(status=False, message="`websocket_port` must be a number")
        # TODO: validate original_media_url
    return ExecutionStatus(status=True)


def validate_media_play_params(name, use_file_num):
    if use_file_num not in ("0", "1"):
        return ExecutionStatus(status=False, message="`search_by_num` should be in range of '0' or '1'")

    if not name:
        return ExecutionStatus(status=False, message="`name` must not be empty")

    return ExecutionStatus(status=True)


class ServiceAddrStorage:
    """
    TODO: save/load config to/from disk
    """

    def __init__(self):
        self.dct = {}

    def __getitem__(self, item):
        return self.dct[item]

    def __setitem__(self, key, value):
        self.dct[key] = value

    def __iter__(self):
        return self.dct.__iter__()

    def items(self):
        return self.dct.items()

    def addr(self, lang):
        return self.dct[lang]["addr"]


class MultilangParams:
    def __init__(self, params_dict, langs=None):
        self.params_dict = params_dict
        self.langs = langs
        self.all_langs = (len(params_dict) == 1) and ("__all__" in params_dict)

    def __getitem__(self, item):
        if self.all_langs:
            return self.params_dict["__all__"]
        return self.params_dict[item]

    def __setitem__(self, key, value):
        if self.all_langs:
            raise NotImplementedError()
        self.params_dict[key] = value

    def __iter__(self):
        return self.params_dict.__iter__()

    def items(self):
        return self.params_dict.items()

    def list_langs(self):
        if self.all_langs:
            return self.langs
        return list(self.params_dict.keys())


class ExecutionStatus:
    def __init__(self, status, message=""):
        self.status = status
        self.message = message

        if re.match(r"\d{3}$", str(status)):
            self._type = "http"
        else:
            self._type = ""

    def __bool__(self):
        if self._type == "http":
            return bool(self.status) and str(self.status)[:1] == "2"
        else:
            return bool(self.status)

    def append_warning(self, message):
        if self.message:
            self.message += "\n-----\n"
        self.message += message
        self.status = False

    def append_error(self, message):
        if self.message:
            self.message += "\n-----\n"
        self.message += message
        self.status = False

    def to_http_status(self):
        """
        Returns http perspective of the status:
        `(message, code)`
        """
        code = 200 if self.__bool__() else 500
        msg = "Ok" if code == 200 and not self.message else self.message
        return msg, code
