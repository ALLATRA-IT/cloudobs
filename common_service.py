import json
import os
from urllib.parse import urlencode

import grequests
from dotenv import load_dotenv
from flask import Flask
from flask import request

import server
import util
from config import API_CLEANUP_ROUTE
from config import API_INIT_ROUTE
from config import API_MEDIA_PLAY_ROUTE
from config import API_SET_STREAM_SETTINGS_ROUTE
from config import API_SIDECHAIN_ROUTE
from config import API_SOURCE_VOLUME_ROUTE
from config import API_STREAM_START_ROUTE
from config import API_STREAM_STOP_ROUTE
from config import API_TRANSITION_ROUTE
from config import API_TS_OFFSET_ROUTE
from config import API_TS_VOLUME_ROUTE
from util import ExecutionStatus, MultilangParams

load_dotenv()
MEDIA_DIR = os.getenv("MEDIA_DIR")

app = Flask(__name__)
obs_server: server.Server = None
instance_service_addrs = util.ServiceAddrStorage()  # dict of `"lang": {"addr": "address"}
langs = []


def broadcast(
    api_route,
    http_method,
    params: util.MultilangParams = None,
    param_name="params",
    return_status=False,
    method_name="broadcast",
):
    requests_ = {}  # lang: request
    responses_ = {}  # lang: response

    langs_ = params.list_langs() if params is not None else langs
    # create requests for all langs
    for lang in langs_:
        addr = instance_service_addrs.addr(lang)  # get server address
        request_ = f"{addr}{api_route}"  # create requests
        if params is not None:  # add query params if needed
            params_json = json.dumps({lang: params[lang]})
            query_params = urlencode({param_name: params_json})
            request_ = request_ + "?" + query_params
        requests_[lang] = request_  # dump request

    # initialize grequests
    for lang, request_ in requests_.items():
        if http_method == "GET":
            requests_[lang] = grequests.get(request_)
        elif http_method == "POST":
            requests_[lang] = grequests.post(request_)
        else:
            raise
    # send requests
    for lang, response_ in zip(requests_.keys(), grequests.map(requests_.values())):
        responses_[lang] = response_

    # decide wether to return status of response
    if return_status:
        status: ExecutionStatus = ExecutionStatus(status=True)
        for lang, response_ in responses_.items():
            if response_.status_code != 200:
                msg_ = f"E PYSERVER::{method_name}(): {lang}, details: {response_.text}"
                print(msg_)
                status.append_error(msg_)
        return status
    else:
        return responses_


@app.route(API_INIT_ROUTE, methods=["POST"])
def init():
    """
    Query parameters:
    server_langs: json,
        dict of "lang": {
            "host_url": "base_url",
            "websocket_port": 1234,
            "password": "qwerty123",
            "original_media_url": "srt://localhost"
        }
    e.g.: {
        "rus": {
            "host_url": "http://255.255.255.255:5000",
            "websocket_port": 1234,
            "password": "qwerty123",
            "original_media_url": "srt://localhost"
        },
        "eng": ...
    }
    :return:
    """
    server_langs = request.args.get("server_langs", "")
    server_langs = json.loads(server_langs)

    # validate input parameters before broadcasting them to servers
    status: ExecutionStatus = util.validate_init_params(server_langs)
    if not status:
        return status.to_http_status()

    status = ExecutionStatus(status=True)

    # in the following loop we build `server_lang` parameters for each lang and
    # broadcast request for all servers
    global instance_service_addrs  # dict of `"lang": {"addr": "address", "init": True/False}
    global langs
    langs = list(set(server_langs.keys()))
    requests_ = []

    for lang in langs:
        lang_info = server_langs[lang]
        # fill `instance_service_addrs`
        instance_service_addrs[lang] = {
            "addr": lang_info["host_url"].strip("/"),
        }
        lang_info.pop("host_url")
        # initialization for every instance service
        # for now every obs instance should be started locally with the instance service
        lang_info["obs_host"] = "localhost"
        lang_info = {lang: lang_info}

        query_params = urlencode({"server_langs": json.dumps(lang_info)})

        addr = instance_service_addrs.addr(lang)
        request_ = f"{addr}{API_INIT_ROUTE}?{query_params}"
        requests_.append(grequests.post(request_))

    for lang, response in zip(langs, grequests.map(requests_, gtimeout=5)):
        if response.status_code != 200:
            msg_ = f"E PYSERVER::init(): couldn't initialize server for {lang}, details: {response.text}"
            print(msg_)
            status.append_error(msg_)

    return status.to_http_status()


@app.route(API_CLEANUP_ROUTE, methods=["POST"])
def cleanup():
    """
    :return:
    """
    status = ExecutionStatus(status=True)

    responses = broadcast(API_CLEANUP_ROUTE, "POST")
    for lang, response in responses.items():
        if response.status_code != 200:
            msg_ = f"E PYSERVER::cleanup(): couldn't cleanup server for {lang}, details: {response.text}"
            print(msg_)
            status.append_error(msg_)

    return status.to_http_status()


@app.route(API_MEDIA_PLAY_ROUTE, methods=["POST"])
def media_play():
    """
    Query parameters:
    params: json dictionary,
    e.g. {"lang": {"name": "...", "search_by_num": "0/1"}, ...}
    :return:
    """
    params = request.args.get("params", None)
    params = json.loads(params)

    params = MultilangParams(params, langs=langs)
    status = broadcast(
        API_MEDIA_PLAY_ROUTE, "POST", params=params, param_name="params", return_status=True, method_name="media_play"
    )

    return status.to_http_status()


@app.route(API_SET_STREAM_SETTINGS_ROUTE, methods=["POST"])
def set_stream_settings():
    """
    Query parameters:
    stream_settings: json dictionary,
    e.g. {"lang": {"server": "rtmp://...", "key": "..."}, ...}
    :return:
    """
    stream_settings = request.args.get("stream_settings", None)
    stream_settings = json.loads(stream_settings)

    params = MultilangParams(stream_settings, langs=langs)
    status = broadcast(
        API_SET_STREAM_SETTINGS_ROUTE,
        "POST",
        params=params,
        param_name="stream_settings",
        return_status=True,
        method_name="set_stream_settings",
    )

    return status.to_http_status()


@app.route(API_STREAM_START_ROUTE, methods=["POST"])
def stream_start():
    """
    Starts streaming on all machines
    :return:
    """
    status = broadcast(API_STREAM_START_ROUTE, "POST", params=None, return_status=True, method_name="stream_start")

    return status.to_http_status()


@app.route(API_STREAM_STOP_ROUTE, methods=["POST"])
def stream_stop():
    """
    Stops streaming on all machines
    :return:
    """
    status = broadcast(API_STREAM_STOP_ROUTE, "POST", params=None, return_status=True, method_name="stream_stop")

    return status.to_http_status()


@app.route(API_TS_OFFSET_ROUTE, methods=["POST"])
def set_ts_offset():
    """
    Query parameters:
    offset_settings: json dictionary,
    e.g. {"lang": 4000, ...} (note, offset in milliseconds)
    :return:
    """
    offset_settings = request.args.get("offset_settings", None)
    offset_settings = json.loads(offset_settings)

    params = MultilangParams(offset_settings, langs=langs)
    status = broadcast(
        API_TS_OFFSET_ROUTE,
        "POST",
        params=params,
        param_name="offset_settings",
        return_status=True,
        method_name="set_ts_offset",
    )

    return status.to_http_status()


@app.route(API_TS_OFFSET_ROUTE, methods=["GET"])
def get_ts_offset():
    """
    Retrieves information about teamspeak sound offset
    :return: {"lang": offset, ...} (note, offset in milliseconds)
    """
    responses = broadcast(API_TS_OFFSET_ROUTE, "GET", params=None, return_status=False)
    data = {}
    for lang, response in responses.items():
        try:
            data_ = json.loads(response.text)
        except json.JSONDecodeError:
            data_ = {lang: "#"}
        for lang_, value in data_.items():
            data[lang_] = value

    return json.dumps(data), 200


@app.route(API_TS_VOLUME_ROUTE, methods=["POST"])
def set_ts_volume():
    """
    Query parameters:
    volume_settings: json dictionary,
    e.g. {"lang": 0.0, ...}
    :return:
    """
    volume_settings = request.args.get("volume_settings", None)
    volume_settings = json.loads(volume_settings)

    params = MultilangParams(volume_settings, langs=langs)
    status = broadcast(
        API_TS_VOLUME_ROUTE,
        "POST",
        params=params,
        param_name="volume_settings",
        return_status=True,
        method_name="set_ts_volume",
    )

    return status.to_http_status()


@app.route(API_TS_VOLUME_ROUTE, methods=["GET"])
def get_ts_volume():
    """
    Retrieves information about teamspeak sound volume
    :return: {"lang": offset, ...} (note, volume in decibels)
    """
    responses = broadcast(API_TS_VOLUME_ROUTE, "GET", params=None, return_status=False)
    data = {}
    for lang, response in responses.items():
        try:
            data_ = json.loads(response.text)
        except json.JSONDecodeError:
            data_ = {lang: "#"}
        for lang_, value in data_.items():
            data[lang_] = value

    return json.dumps(data), 200


@app.route(API_SOURCE_VOLUME_ROUTE, methods=["POST"])
def set_source_volume():
    """
    Query parameters:
    volume_settings: json dictionary,
    e.g. {"lang": 0.0, ...}
    :return:
    """
    volume_settings = request.args.get("volume_settings", None)
    volume_settings = json.loads(volume_settings)

    params = MultilangParams(volume_settings, langs=langs)
    status = broadcast(
        API_TS_VOLUME_ROUTE,
        "POST",
        params=params,
        param_name="volume_settings",
        return_status=True,
        method_name="set_source_volume",
    )

    return status.to_http_status()


@app.route(API_SOURCE_VOLUME_ROUTE, methods=["GET"])
def get_source_volume():
    """
    Retrieves information about original source volume
    :return: {"lang": volume, ...} (note, volume in decibels)
    """
    responses = broadcast(API_SOURCE_VOLUME_ROUTE, "GET", params=None, return_status=False)
    data = {}
    for lang, response in responses.items():
        try:
            data_ = json.loads(response.text)
        except json.JSONDecodeError:
            data_ = {lang: "#"}
        for lang_, value in data_.items():
            data[lang_] = value

    return json.dumps(data), 200


@app.route(API_SIDECHAIN_ROUTE, methods=["POST"])
def setup_sidechain():
    """
    Query parameters:
    sidechain_settings: json dictionary,
    e.g. {"lang": {'ratio': ..., 'release_time': ..., 'threshold': ...}, ...}
    :return:
    """
    sidechain_settings = request.args.get("sidechain_settings", None)
    sidechain_settings = json.loads(sidechain_settings)

    params = MultilangParams(sidechain_settings, langs=langs)
    status = broadcast(
        API_SIDECHAIN_ROUTE,
        "POST",
        params=params,
        param_name="sidechain_settings",
        return_status=True,
        method_name="setup_sidechain",
    )

    return status.to_http_status()


@app.route(API_TRANSITION_ROUTE, methods=["POST"])
def setup_transition():
    """
    Query parameters:
    transition_settings: json dictionary,
    e.g. {"lang": {'transition_name': ..., 'audio_fade_style': ..., 'path': ..., ...}, ...}
    :return:
    """
    transition_settings = request.args.get("transition_settings", None)
    transition_settings = json.loads(transition_settings)

    params = MultilangParams(transition_settings, langs=langs)
    status = broadcast(
        API_TRANSITION_ROUTE,
        "POST",
        params=params,
        param_name="transition_settings",
        return_status=True,
        method_name="setup_transition",
    )

    return status.to_http_status()


if __name__ == "__main__":
    app.run("0.0.0.0", 5000)
