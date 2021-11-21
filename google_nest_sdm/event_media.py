"""Libraries related to providing a device level interface for event related media."""

from __future__ import annotations

import datetime
import logging
from collections import OrderedDict
from collections.abc import Iterable
from typing import Dict, Optional

from .camera_traits import EventImageGenerator, EventImageType
from .event import EventMessage, ImageEventBase

_LOGGER = logging.getLogger(__name__)

DEFAULT_CACHE_SIZE = 2


class CachePolicy:
    """Policy for how many local objects to cache in memory."""

    def __init__(
        self, event_cache_size: int = DEFAULT_CACHE_SIZE, prefetch: bool = False
    ):
        self._event_cache_size = event_cache_size
        self._prefetch = prefetch

    @property
    def event_cache_size(self) -> int:
        """Number of events to keep in memory per device."""
        return self._event_cache_size

    @event_cache_size.setter
    def event_cache_size(self, value: int) -> None:
        """Set the number of events to keep in memory per device."""
        self._event_cache_size = value

    @property
    def prefetch(self) -> bool:
        """Return true if event media should be pre-fetched."""
        return self._prefetch

    @prefetch.setter
    def prefetch(self, value: bool) -> None:
        """Update the value for whether event media should be pre-fetched."""
        self._prefetch = value


class Media:
    """Represents media related to an event."""

    def __init__(self, contents: bytes, event_image_type: EventImageType) -> None:
        """Initialize Media."""
        self._contents = contents
        self._event_image_type = event_image_type

    @property
    def contents(self) -> bytes:
        """Media content."""
        return self._contents

    @property
    def event_image_type(self) -> EventImageType:
        """Content event image type of the media."""
        return self._event_image_type


class EventMedia:
    """Represents an event and its associated media."""

    def __init__(
        self,
        event_id: str,
        event_type: str,
        event_timestamp: datetime.datetime,
        media: Media,
    ) -> None:
        self._event_id = event_id
        self._event_type = event_type
        self._event_timestamp = event_timestamp
        self._media = media

    @property
    def event_id(self) -> str:
        """Return the event id."""
        return self._event_id

    @property
    def event_type(self) -> str:
        """Return the event type."""
        return self._event_type

    @property
    def event_timestamp(self) -> datetime.datetime:
        """Return timestamp that the event ocurred."""
        return self._event_timestamp

    @property
    def media(self) -> Media:
        return self._media


class EventMediaManager:
    """Responsible for handling recent events and fetching associated media."""

    def __init__(self, event_trait_map: Dict[str, EventImageGenerator]) -> None:
        """Initialize DeviceEventMediaManager."""
        self._event_trait_map = event_trait_map
        self._cache_policy = CachePolicy()
        self._data: OrderedDict[str, ImageEventBase] = OrderedDict()

    @property
    def cache_policy(self) -> CachePolicy:
        """Return the current CachePolicy."""
        return self._cache_policy

    @cache_policy.setter
    def cache_policy(self, value: CachePolicy) -> None:
        """Update the CachePolicy."""
        self._cache_policy = value

    async def get_media(self, event_id: str) -> Optional[EventMedia]:
        """Get media for the specified event."""
        if not (event := self._data.get(event_id)):
            return None
        self._data.move_to_end(event_id)
        if not (generator := self._event_trait_map.get(event.event_type)):
            return None
        event_image = await generator.generate_event_image(event)
        if not event_image:
            return None
        contents = await event_image.contents()
        media = Media(contents, event_image.event_image_type)
        return EventMedia(event_id, event.event_type, event.timestamp, media)

    async def events(self) -> Iterable[ImageEventBase]:
        """Return revent events."""
        result = list(self._data.values())
        result.sort(key=lambda x: x.timestamp, reverse=True)
        return result

    async def async_handle_events(self, event_message: EventMessage) -> None:
        """Handle the EventMessage."""
        events = event_message.resource_update_events
        if not events:
            return
        _LOGGER.debug("Event Update %s", events.keys())
        for (event_name, event) in events.items():
            if event_name not in self._event_trait_map:
                continue
            self._event_trait_map[event_name].handle_event(event)
            self._data[event.event_id] = event
            if len(self._data) > self._cache_policy.event_cache_size:
                self._data.popitem(last=False)

    def active_events(self, event_types: list) -> Dict[str, ImageEventBase]:
        """Return any active events for the specified trait names."""
        active_events = {}
        for event_type in event_types:
            trait = self._event_trait_map.get(event_type)
            if not trait or not trait.active_event:
                continue
            active_events[event_type] = trait.active_event
        return active_events

    @property
    def active_event_trait(self) -> Optional[EventImageGenerator]:
        """Return trait with the most recently received active event."""
        trait_to_return: EventImageGenerator | None = None
        for trait in self._event_trait_map.values():
            if not trait.active_event:
                continue
            if trait_to_return is None:
                trait_to_return = trait
            else:
                event = trait.last_event
                if not event or not trait_to_return.last_event:
                    continue
                if event.expires_at > trait_to_return.last_event.expires_at:
                    trait_to_return = trait
        return trait_to_return
