import os
import obswebsocket as obs
import obswebsocket.requests as obs_requests
from obswebsocket import events
from threading import Lock

ORIGINAL_STREAM_SOURCE_NAME = 'original_stream'
MAIN_SCENE_NAME = 'main'

def create_event_handler(obs_instance):
    def foo(message):
        obs_instance.on_event(message)
    return foo

class OBS:
    def __init__(self, lang, client):
        self.lang = lang
        self.client = client
        self.original_media_source = None
        self.media_queue = []
        self.callback_queue = []

        self.client.register(create_event_handler(self))

    def update(self):
        for callback in self.callback_queue:
            callback()
        self.callback_queue.clear()

    def set_original_media_source(self, scene_name, original_media_source):
        """
        Adds an original media source
        :param scene_name: scene to add an input
        :param original_media_source: url like 'protocol://address[:port][/path][...]', may be rtmp, srt
        """
        self.original_media_source = original_media_source

        source_settings = {
            'input': original_media_source,
            'is_local_file': False,
        }
        request = obs.requests.CreateSource(
            sourceName=ORIGINAL_STREAM_SOURCE_NAME,
            sourceKind='ffmpeg_source',
            sceneName=scene_name,
            sourceSettings=source_settings
        )
        response = self.client.call(request)

        if not response.status:
            raise Exception(f"E PYSERVER::OBS::add_original_media_source(): "
                            f"coudn't create a source, datain: {response.datain}, dataout: {response.dataout}")

        request = obs.requests.SetAudioMonitorType(
            sourceName=ORIGINAL_STREAM_SOURCE_NAME, monitorType='none'
        )
        response = self.client.call(request)

        if not response.status:
            raise Exception(f"E PYSERVER::OBS::add_original_media_source(): "
                            f"coudn't set audio monitor type, datain: {response.datain}, dataout: {response.dataout}")

    def setup_scene(self, scene_name='main'):
        """
        Creates (if not been created) a scene called `scene_name` and sets it as a current scene.
        If it has been created, removes all the sources inside the scene and sets it as a current one.
        """
        scenes = self.client.call(
            obs.requests.GetSceneList()).getScenes()  # [... {'name': '...', 'sources': [...]}, ...]

        # if such scene has already been created
        if any([x['name'] == scene_name for x in scenes]):
            self.clear_scene(scene_name)
        else:
            self.create_scene(scene_name)

        self.set_current_scene(scene_name)

    def clear_all_scenes(self):
        """
        Lists all the scenes and removes all the scene items.
        """
        scenes = self.obsws_get_scene_list()
        for scene_info in scenes:
            scene_name = scene_info['name']
            self.clear_scene(scene_name)

    def clear_scene(self, scene_name):
        """
        Removes all the items from a specified scene
        """
        items = self.obsws_get_scene_item_list(scene_name=scene_name)
        items = [{'id': item['itemId'], 'name': item['sourceName']} for item in items]
        for item in items:
            response = self.client.call(obs.requests.DeleteSceneItem(scene=scene_name, item=item))
            if not response.status:  # if not deleted
                raise Exception(
                    f"E PYSERVER::OBS::clear_scene(): coudn't delete scene item, "
                    f"datain: {response.datain}, dataout: {response.dataout}")

    def set_current_scene(self, scene_name):
        """
        Switches current scene to `scene_name`
        """
        self.client.call(obs.requests.SetCurrentScene(scene_name=scene_name))

    def create_scene(self, scene_name):
        """
        Creates a scene with name `scene_name`
        """
        self.client.call(obs.requests.CreateScene(sceneName=scene_name))

    def run_media(self, path):
        """
        Mutes original media, adds and runs the media located at `path`, and appends a listener which removes
        the media when it has finished. Fires Exception when couldn't add or mute a source.
        """
        filename = os.path.basename(path)
        scene_name = self.obsws_get_current_scene_name()

        response = self.client.call(obs.requests.CreateSource(
            sourceName=filename,
            sourceKind='ffmpeg_source',
            sceneName=scene_name,
            sourceSettings={'local_file': path}
        ))

        if not response.status:
            raise Exception(f"E PYSERVER::OBS::run_media(): "
                            f"coudn't add a media source, datain: {response.datain}, dataout: {response.dataout}")

        self.media_queue.append(filename)

        response = self.client.call(obs.requests.SetMute(source=ORIGINAL_STREAM_SOURCE_NAME, mute=True))
        if not response.status:
            raise Exception(f"E PYSERVER::OBS::run_media(): "
                            f"coudn't mute a source, datain: {response.datain}, dataout: {response.dataout}")

    def on_event(self, message):
        if message.name == 'MediaEnded':
            self.on_media_ended(message)

    def on_media_ended(self, message):
        """
        Fired on event MediaEnded. Fires Exception if could't delete a scene item or unmute a source
        """
        source_name = message.getSourceName()

        def callback():
            if source_name in self.media_queue:
                scene_name = self.obsws_get_current_scene_name()

                response = self.client.call(obs.requests.DeleteSceneItem(scene=scene_name, item=source_name))
                if not response.status:
                    raise Exception(
                        f"E PYSERVER::OBS::on_media_ended(): coudn't delete scene item, "
                        f"datain: {response.datain}, dataout: {response.dataout}")
                self.media_queue.remove(source_name)

                response = self.client.call(obs.requests.SetMute(source=ORIGINAL_STREAM_SOURCE_NAME, mute=False))
                if not response.status:
                    raise Exception(f"E PYSERVER::OBS::on_media_ended(): "
                                    f"coudn't unmute a source, datain: {response.datain}, dataout: {response.dataout}")

        self.callback_queue.append(callback)

    def obsws_get_current_scene_name(self):
        return self.client.call(obs.requests.GetCurrentScene()).getName()

    def obsws_get_sources_list(self):
        """
        :return: list of [... {'name': '...', 'type': '...', 'typeId': '...'}, ...]
        """
        return self.client.call(obs.requests.GetSourcesList()).getSources()

    def obsws_get_scene_list(self):
        """
        :return: list of [... {'name': '...', 'sources': [{..., 'id': n, ..., 'name': '...', ...}, ...]}, ...]
        """
        return self.client.call(obs.requests.GetSceneList()).getScenes()

    def obsws_get_scene_item_list(self, scene_name):
        """
        :param scene_name: name of the scene
        :return: list of [... {'itemId': n, 'sourceKind': '...', 'sourceName': '...', 'sourceType': '...'}, ...]
        """
        return self.client.call(obs.requests.GetSceneItemList(sceneName=scene_name)).getSceneItems()
