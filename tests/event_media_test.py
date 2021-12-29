import datetime
import itertools
from typing import Any, Awaitable, Callable, Dict

import aiohttp
import pytest

from google_nest_sdm import google_nest_api
from google_nest_sdm.camera_traits import EventImageType
from google_nest_sdm.event import EventMessage, ImageEventBase
from google_nest_sdm.event_media import InMemoryEventMediaStore

from .conftest import FAKE_TOKEN, DeviceHandler, NewHandler, NewImageHandler, Recorder


@pytest.mark.parametrize(
    "test_trait,test_event_trait",
    [
        ("sdm.devices.traits.CameraMotion", "sdm.devices.events.CameraMotion.Motion"),
        ("sdm.devices.traits.CameraPerson", "sdm.devices.events.CameraPerson.Person"),
        ("sdm.devices.traits.CameraSound", "sdm.devices.events.CameraSound.Sound"),
        ("sdm.devices.traits.DoorbellChime", "sdm.devices.events.DoorbellChime.Chime"),
    ],
)
async def test_event_manager_image(
    app: aiohttp.web.Application,
    recorder: Recorder,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
    test_trait: str,
    test_event_trait: str,
) -> None:
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            test_trait: {},
        }
    )

    post_handler = NewHandler(
        recorder,
        [
            {
                "results": {
                    "url": "image-url-1",
                    "token": "g.1.eventToken",
                },
            },
            {
                "results": {
                    "url": "image-url-2",
                    "token": "g.2.eventToken",
                },
            },
        ],
    )
    app.router.add_post(f"/{device_id}:executeCommand", post_handler)
    app.router.add_get(
        "/image-url-1", NewImageHandler([b"image-bytes-1"], token="g.1.eventToken")
    )
    app.router.add_get(
        "/image-url-2", NewImageHandler([b"image-bytes-2"], token="g.2.eventToken")
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    ts1 = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": ts1.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        test_event_trait: {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "FWWVQVUdGNUlTU2V4MGV2aTNXV...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )
    ts2 = ts1 + datetime.timedelta(seconds=5)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "a94b2115-3b57-4eb4-8830-80519f188ec9",
                "timestamp": ts2.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        test_event_trait: {
                            "eventSessionId": "QjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "ABCZQRUdGNUlTU2V4MGV3bRZ23...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )

    event_media_manager = device.event_media_manager

    event_media = await event_media_manager.get_media("CjY5Y3VKaTZwR3o4Y19YbTVfMF...")
    assert event_media
    assert event_media.event_session_id == "CjY5Y3VKaTZwR3o4Y19YbTVfMF..."
    assert event_media.event_type == test_event_trait
    assert event_media.event_timestamp.isoformat(timespec="seconds") == ts1.isoformat(
        timespec="seconds"
    )
    assert event_media.media.contents == b"image-bytes-1"
    assert event_media.media.event_image_type.content_type == "image/jpeg"

    event_media = await event_media_manager.get_media("QjY5Y3VKaTZwR3o4Y19YbTVfMF...")
    assert event_media
    assert event_media.event_session_id == "QjY5Y3VKaTZwR3o4Y19YbTVfMF..."
    assert event_media.event_type == test_event_trait
    assert event_media.event_timestamp.isoformat(timespec="seconds") == ts2.isoformat(
        timespec="seconds"
    )
    assert event_media.media.contents == b"image-bytes-2"
    assert event_media.media.event_image_type.content_type == "image/jpeg"

    assert len(list(await event_media_manager.async_events())) == 2


async def test_event_manager_prefetch_image(
    app: aiohttp.web.Application,
    recorder: Recorder,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            "sdm.devices.traits.CameraMotion": {},
        }
    )

    post_handler = NewHandler(
        recorder,
        [
            {
                "results": {
                    "url": "image-url-1",
                    "token": "g.1.eventToken",
                },
            },
        ],
    )
    app.router.add_post(f"/{device_id}:executeCommand", post_handler)
    app.router.add_get(
        "/image-url-1", NewImageHandler([b"image-bytes-1"], token="g.1.eventToken")
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    # Turn on event fetching
    device.event_media_manager.cache_policy.fetch = True

    ts1 = datetime.datetime(2019, 1, 1, 0, 0, 1, tzinfo=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": ts1.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "FWWVQVUdGNUlTU2V4MGV2aTNXV...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )
    # Event is not fetched on event arrival since it was expired
    event_media_manager = device.event_media_manager
    assert len(list(await event_media_manager.async_events())) == 0
    assert not await event_media_manager.get_active_event_media()

    # And we won't fetch it when asked either
    event_media = await event_media_manager.get_media("CjY5Y3VKaTZwR3o4Y19YbTVfMF...")
    assert not event_media
    assert len(list(await event_media_manager.async_events())) == 0

    # Publishing an active event is fetched immediately
    ts2 = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": ts2.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "DkY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "GXQADVUdGNUlTU2V4MGV2aTNXV...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )
    assert len(list(await event_media_manager.async_events())) == 1

    # However, manually fetching it could still work
    event_media_manager = device.event_media_manager
    event_media = await event_media_manager.get_media("DkY5Y3VKaTZwR3o4Y19YbTVfMF...")
    assert event_media
    assert event_media.event_session_id == "DkY5Y3VKaTZwR3o4Y19YbTVfMF..."
    assert event_media.event_type == "sdm.devices.events.CameraMotion.Motion"
    assert event_media.event_timestamp.isoformat(timespec="seconds") == ts2.isoformat(
        timespec="seconds"
    )
    assert event_media.media.contents == b"image-bytes-1"
    assert event_media.media.event_image_type.content_type == "image/jpeg"


async def test_event_manager_event_expiration(
    app: aiohttp.web.Application,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            "sdm.devices.traits.CameraMotion": {},
        }
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    device.event_media_manager.cache_policy.event_cache_size = 10

    ts1 = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": ts1.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "FWWVQVUdGNUlTU2V4MGV2aTNXV...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )
    ts2 = ts1 + datetime.timedelta(seconds=5)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "a94b2115-3b57-4eb4-8830-80519f188ec9",
                "timestamp": ts2.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "DgY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "ABCZQRUdGNUlTU2V4MGV3bRZ23...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )

    # Event is in the past and is expired
    ts3 = ts1 - datetime.timedelta(seconds=90)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "b83c2115-3b57-4eb4-8830-80519f167fa8",
                "timestamp": ts3.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "EkY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "1234QRUdGNUlTU2V4MGV3bRZ23...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )

    event_media_manager = device.event_media_manager
    assert len(list(await event_media_manager.async_events())) == 2


async def test_event_manager_cache_expiration(
    app: aiohttp.web.Application,
    recorder: Recorder,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            "sdm.devices.traits.CameraMotion": {},
        }
    )

    response = {
        "results": {
            "url": "image-url-1",
            "token": "g.1.eventToken",
        },
    }
    num_events = 10
    post_handler = NewHandler(recorder, list(itertools.repeat(response, num_events)))
    app.router.add_post(f"/{device_id}:executeCommand", post_handler)
    app.router.add_get(
        "/image-url-1",
        NewImageHandler(
            list(itertools.repeat(b"image-bytes-1", num_events)), token="g.1.eventToken"
        ),
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    # Turn on event fetching
    device.event_media_manager.cache_policy.fetch = True
    device.event_media_manager.cache_policy.event_cache_size = 8

    class TestStore(InMemoryEventMediaStore):
        def get_media_key(self, device_id: str, event: ImageEventBase) -> str:
            """Return a predictable media key."""
            return event.event_session_id

    store = TestStore()
    device.event_media_manager.cache_policy.store = store

    for i in range(0, num_events):
        ts = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
            seconds=i
        )
        await device.async_handle_event(
            await event_message(
                {
                    "eventId": f"0120ecc7-{i}",
                    "timestamp": ts.isoformat(timespec="seconds"),
                    "resourceUpdate": {
                        "name": device_id,
                        "events": {
                            "sdm.devices.events.CameraMotion.Motion": {
                                "eventSessionId": f"CjY5Y3VK..{i}...",
                                "eventId": f"FWWVQVU..{i}...",
                            },
                        },
                    },
                    "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
                }
            )
        )

    event_media_manager = device.event_media_manager
    # All old items are evicted from the cache
    assert len(list(await event_media_manager.async_events())) == 8

    # Old items are evicted from the media store
    assert await store.async_load_media("CjY5Y3VK..0...") is None
    assert await store.async_load_media("CjY5Y3VK..1...") is None
    for i in range(2, num_events):
        assert await store.async_load_media(f"CjY5Y3VK..{i}...") == b"image-bytes-1"


async def test_event_manager_prefetch_image_failure(
    app: aiohttp.web.Application,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            "sdm.devices.traits.CameraMotion": {},
        }
    )

    # Send one failure response, then 3 other valid responses. The cache size
    # is too so we're exercising events dropping out of the cache.
    responses = [
        aiohttp.web.json_response(
            {
                "results": {
                    "url": "image-url-1",
                    "token": "g.1.eventToken",
                },
            }
        ),
        aiohttp.web.Response(status=502),
        aiohttp.web.json_response(
            {
                "results": {
                    "url": "image-url-1",
                    "token": "g.1.eventToken",
                },
            }
        ),
        aiohttp.web.json_response(
            {
                "results": {
                    "url": "image-url-1",
                    "token": "g.1.eventToken",
                },
            }
        ),
        aiohttp.web.json_response(
            {
                "results": {
                    "url": "image-url-1",
                    "token": "g.1.eventToken",
                },
            }
        ),
    ]

    async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        assert request.headers["Authorization"] == "Bearer %s" % FAKE_TOKEN
        return responses.pop(0)

    app.router.add_post(f"/{device_id}:executeCommand", handler)
    app.router.add_get(
        "/image-url-1",
        NewImageHandler(
            list(itertools.repeat(b"image-bytes-1", 4)), token="g.1.eventToken"
        ),
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    # Turn on event fetching
    device.event_media_manager.cache_policy.fetch = True
    device.event_media_manager.cache_policy.event_cache_size = 3

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    for i in range(0, 5):
        ts = now + datetime.timedelta(seconds=i)
        await device.async_handle_event(
            await event_message(
                {
                    "eventId": f"0120ecc7-{i}",
                    "timestamp": ts.isoformat(timespec="seconds"),
                    "resourceUpdate": {
                        "name": device_id,
                        "events": {
                            "sdm.devices.events.CameraMotion.Motion": {
                                "eventSessionId": f"CjY5Y...{i}...",
                                "eventId": f"FWWVQVU..{i}...",
                            },
                        },
                    },
                    "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
                }
            )
        )

    event_media_manager = device.event_media_manager
    events = await event_media_manager.async_events()
    assert len(list(events)) == 3

    for i in range(1, 4):
        event_media = await event_media_manager.get_media(f"CjY5Y...{i}...")
        if i == 1:
            assert not event_media
            continue

        ts = now + datetime.timedelta(seconds=i)
        assert event_media
        assert event_media.event_session_id == f"CjY5Y...{i}..."
        assert event_media.event_type == "sdm.devices.events.CameraMotion.Motion"
        assert event_media.event_timestamp.isoformat(
            timespec="seconds"
        ) == ts.isoformat(timespec="seconds")
        assert event_media.media.contents == b"image-bytes-1"
        assert event_media.media.event_image_type.content_type == "image/jpeg"


async def test_multi_device_events(
    app: aiohttp.web.Application,
    recorder: Recorder,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:

    device_id1 = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            "sdm.devices.traits.CameraMotion": {},
        }
    )
    device_id2 = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            "sdm.devices.traits.CameraMotion": {},
        }
    )

    response = {
        "results": {
            "url": "image-url-1",
            "token": "g.1.eventToken",
        },
    }
    num_events = 4
    post_handler = NewHandler(recorder, list(itertools.repeat(response, num_events)))
    app.router.add_post(f"/{device_id1}:executeCommand", post_handler)
    app.router.add_get(
        "/image-url-1",
        NewImageHandler(
            list(itertools.repeat(b"image-bytes-1", num_events)), token="g.1.eventToken"
        ),
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 2
    device = devices[0]
    assert device.name == device_id1
    device = devices[1]
    assert device.name == device_id2

    # Use shared event store for all devices
    store = InMemoryEventMediaStore()
    devices[0].event_media_manager.cache_policy.store = store
    devices[1].event_media_manager.cache_policy.store = store

    # Each device has
    event_media_manager = devices[0].event_media_manager
    assert len(list(await event_media_manager.async_events())) == 0
    event_media_manager = devices[1].event_media_manager
    assert len(list(await event_media_manager.async_events())) == 0

    ts = datetime.datetime.now(tz=datetime.timezone.utc)
    await devices[0].async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-1",
                "timestamp": ts.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id1,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "FWWVQVU..1...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )

    # Each device has a single event
    event_media_manager = devices[0].event_media_manager
    assert len(list(await event_media_manager.async_events())) == 1
    event_media_manager = devices[1].event_media_manager
    assert len(list(await event_media_manager.async_events())) == 0

    await devices[1].async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-2",
                "timestamp": ts.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id2,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "FWWVQVU..2...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )

    # Each device has a single event
    event_media_manager = devices[0].event_media_manager
    assert len(list(await event_media_manager.async_events())) == 1
    event_media_manager = devices[1].event_media_manager
    assert len(list(await event_media_manager.async_events())) == 1


@pytest.mark.parametrize(
    "test_trait,test_event_trait",
    [
        ("sdm.devices.traits.CameraMotion", "sdm.devices.events.CameraMotion.Motion"),
        ("sdm.devices.traits.CameraPerson", "sdm.devices.events.CameraPerson.Person"),
        ("sdm.devices.traits.CameraSound", "sdm.devices.events.CameraSound.Sound"),
        ("sdm.devices.traits.DoorbellChime", "sdm.devices.events.DoorbellChime.Chime"),
    ],
)
async def test_camera_active_clip_preview_threads(
    test_trait: str,
    test_event_trait: str,
    app: aiohttp.web.Application,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraClipPreview": {},
            test_trait: {},
        }
    )

    async def img_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        assert request.headers["Authorization"] == "Bearer %s" % FAKE_TOKEN
        return aiohttp.web.Response(body=b"image-bytes-1")

    app.router.add_get("/image-url-1", img_handler)

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": now.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        test_event_trait: {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "n:1",
                        },
                        "sdm.devices.events.CameraClipPreview.ClipPreview": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "previewUrl": "image-url-1",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
                "eventThreadId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                "resourcegroup": [
                    "enterprises/project-id1/devices/device-id1",
                ],
                "eventThreadState": "STARTED",
            }
        )
    )
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": now.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        test_event_trait: {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "n:1",
                        },
                        "sdm.devices.events.CameraClipPreview.ClipPreview": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "previewUrl": "image-url-1",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
                "eventThreadId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                "resourcegroup": [
                    "enterprises/project-id1/devices/device-id1",
                ],
                "eventThreadState": "ENDED",
            }
        )
    )

    # Verify active event traits
    trait = device.traits[test_trait]
    assert trait.active_event is not None
    image = await trait.generate_active_event_image()
    assert image
    assert image.event_image_type == EventImageType.CLIP_PREVIEW
    assert image.url == "image-url-1"
    assert image.token is None

    # Verify event manager view
    event_media_manager = devices[0].event_media_manager
    events = list(await event_media_manager.async_events())
    assert len(events) == 1
    event = events[0]
    assert event.event_type == test_event_trait
    assert event.event_session_id == "CjY5Y3VKaTZwR3o4Y19YbTVfMF..."
    assert event.event_id == "n:1"
    assert event.event_image_type.content_type == "video/mp4"

    event_media = await event_media_manager.get_media("CjY5Y3VKaTZwR3o4Y19YbTVfMF...")
    assert event_media
    assert event_media.event_session_id == "CjY5Y3VKaTZwR3o4Y19YbTVfMF..."
    assert event_media.event_type == test_event_trait
    assert event_media.event_timestamp.isoformat(timespec="seconds") == now.isoformat(
        timespec="seconds"
    )
    assert event_media.media.contents == b"image-bytes-1"
    assert event_media.media.event_image_type.content_type == "video/mp4"


async def test_unsupported_event_for_event_manager(
    app: aiohttp.web.Application,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraEventImage": {},
            "sdm.devices.traits.CameraMotion": {},
        }
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    ts1 = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": ts1.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.DoorbellChime.Chime": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "FWWVQVUdGNUlTU2V4MGV2aTNXV...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )
    event_media_manager = device.event_media_manager
    assert len(list(await event_media_manager.async_events())) == 0

    event_media = await event_media_manager.get_media("CjY5Y3VKaTZwR3o4Y19YbTVfMF...")
    assert not event_media


async def test_camera_active_clip_preview_threads_with_new_events(
    app: aiohttp.web.Application,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    """Test an update to an existing session that contains new events."""
    device_id = device_handler.add_device(
        traits={
            "sdm.devices.traits.CameraClipPreview": {},
            "sdm.devices.traits.CameraMotion": {},
            "sdm.devices.traits.CameraPerson": {},
        }
    )

    async def img_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
        assert request.headers["Authorization"] == "Bearer %s" % FAKE_TOKEN
        return aiohttp.web.Response(body=b"image-bytes-1")

    app.router.add_get("/image-url-1", img_handler)

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": now.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "n:1",
                        },
                        "sdm.devices.events.CameraClipPreview.ClipPreview": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "previewUrl": "image-url-1",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
                "eventThreadId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                "resourcegroup": [
                    "enterprises/project-id1/devices/device-id1",
                ],
                "eventThreadState": "STARTED",
            }
        )
    )
    # Updates the session with an additional event
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": now.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        "sdm.devices.events.CameraMotion.Motion": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "n:1",
                        },
                        "sdm.devices.events.CameraPerson.Person": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "n:2",
                        },
                        "sdm.devices.events.CameraClipPreview.ClipPreview": {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "previewUrl": "image-url-1",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
                "eventThreadId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                "resourcegroup": [
                    "enterprises/project-id1/devices/device-id1",
                ],
                "eventThreadState": "ENDED",
            }
        )
    )

    # Verify active event traits
    trait = device.traits.get("sdm.devices.traits.CameraMotion")
    assert trait
    assert trait.active_event is not None
    image = await trait.generate_active_event_image()
    assert image
    assert image.event_image_type == EventImageType.CLIP_PREVIEW
    assert "image-url-1" == image.url
    assert image.token is None
    trait = device.traits.get("sdm.devices.traits.CameraPerson")
    assert trait
    assert trait.active_event is not None
    image = await trait.generate_active_event_image()
    assert image
    assert image.event_image_type == EventImageType.CLIP_PREVIEW
    assert "image-url-1" == image.url
    assert image.token is None

    # Verify event manager view. Currently events are still collapsed into 1 event, but
    # this may change in the future to represent it differently.
    event_media_manager = devices[0].event_media_manager
    events = list(await event_media_manager.async_events())
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "sdm.devices.events.CameraPerson.Person"
    assert event.event_session_id == "CjY5Y3VKaTZwR3o4Y19YbTVfMF..."
    assert event.event_id == "n:2"
    assert event.event_image_type.content_type == "video/mp4"

    event_media = await event_media_manager.get_media("CjY5Y3VKaTZwR3o4Y19YbTVfMF...")
    assert event_media
    assert event_media.event_session_id == "CjY5Y3VKaTZwR3o4Y19YbTVfMF..."
    assert event_media.event_type == "sdm.devices.events.CameraPerson.Person"
    assert event_media.event_timestamp.isoformat(timespec="seconds") == now.isoformat(
        timespec="seconds"
    )
    assert event_media.media.contents == b"image-bytes-1"
    assert event_media.media.event_image_type.content_type == "video/mp4"


@pytest.mark.parametrize(
    "test_trait,test_event_trait",
    [
        ("sdm.devices.traits.CameraMotion", "sdm.devices.events.CameraMotion.Motion"),
        ("sdm.devices.traits.CameraPerson", "sdm.devices.events.CameraPerson.Person"),
        ("sdm.devices.traits.CameraSound", "sdm.devices.events.CameraSound.Sound"),
        ("sdm.devices.traits.DoorbellChime", "sdm.devices.events.DoorbellChime.Chime"),
    ],
)
async def test_events_without_media_support(
    test_trait: str,
    test_event_trait: str,
    app: aiohttp.web.Application,
    recorder: Recorder,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
) -> None:
    device_id = device_handler.add_device(traits={test_trait: {}})

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": now.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        test_event_trait: {
                            "eventSessionId": "CjY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "FWWVQVUdGNUlTU2V4MGV2aTNXV...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )
    event_media_manager = device.event_media_manager

    # No trait to fetch media
    with pytest.raises(ValueError, match=r"Camera does not have trait"):
        await event_media_manager.get_media("CjY5Y3VKaTZwR3o4Y19YbTVfMF...")


@pytest.mark.parametrize(
    "test_trait,test_event_trait,other_trait",
    [
        (
            "sdm.devices.traits.CameraMotion",
            "sdm.devices.events.CameraMotion.Motion",
            "sdm.devices.traits.CameraPerson",
        ),
        (
            "sdm.devices.traits.CameraPerson",
            "sdm.devices.events.CameraPerson.Person",
            "sdm.devices.traits.CameraSound",
        ),
        (
            "sdm.devices.traits.CameraSound",
            "sdm.devices.events.CameraSound.Sound",
            "sdm.devices.traits.DoorbellChime",
        ),
        (
            "sdm.devices.traits.DoorbellChime",
            "sdm.devices.events.DoorbellChime.Chime",
            "sdm.devices.traits.CameraMotion",
        ),
    ],
)
async def test_event_manager_no_media_support(
    app: aiohttp.web.Application,
    device_handler: DeviceHandler,
    api_client: Callable[[], Awaitable[google_nest_api.GoogleNestAPI]],
    event_message: Callable[[Dict[str, Any]], Awaitable[EventMessage]],
    test_trait: str,
    test_event_trait: str,
    other_trait: str,
) -> None:
    device_id = device_handler.add_device(
        traits={
            test_trait: {},
            other_trait: {},
        }
    )

    api = await api_client()
    devices = await api.async_get_devices()
    assert len(devices) == 1
    device = devices[0]
    assert device.name == device_id

    # Turn on event fetching
    device.event_media_manager.cache_policy.fetch = True

    ts1 = datetime.datetime.now(tz=datetime.timezone.utc)
    await device.async_handle_event(
        await event_message(
            {
                "eventId": "0120ecc7-3b57-4eb4-9941-91609f189fb4",
                "timestamp": ts1.isoformat(timespec="seconds"),
                "resourceUpdate": {
                    "name": device_id,
                    "events": {
                        test_event_trait: {
                            "eventSessionId": "DkY5Y3VKaTZwR3o4Y19YbTVfMF...",
                            "eventId": "GXQADVUdGNUlTU2V4MGV2aTNXV...",
                        },
                    },
                },
                "userId": "AVPHwEuBfnPOnTqzVFT4IONX2Qqhu9EJ4ubO-bNnQ-yi",
            }
        )
    )

    # The device does not support media, so it does not show up in the media manager
    event_media_manager = device.event_media_manager
    assert len(list(await event_media_manager.async_events())) == 1

    # Fetching media by event fails
    with pytest.raises(ValueError):
        await event_media_manager.get_media("DkY5Y3VKaTZwR3o4Y19YbTVfMF...")

    # however, we should see an active event
    trait = device.traits[test_trait]
    assert trait.active_event is not None

    # Fetching the media fails since its not supported
    with pytest.raises(ValueError):
        await trait.generate_active_event_image()

    trait = device.traits[other_trait]
    assert trait.active_event is None