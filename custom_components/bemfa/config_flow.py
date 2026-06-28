"""Config flow for bemfa integration."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .sync import SYNC_TYPES, Sync
from .const import (
    CONF_UID,
    DOMAIN,
    OPTIONS_CONFIG,
    OPTIONS_SELECT,
    OPTIONS_SYNC_TYPE,
    OPTIONS_NAME,
)
from .service import BemfaService

_LOGGER = logging.getLogger(__name__)

SYNC_TYPE_LABELS = {
    "automation": ("自动化", "Automation"),
    "binary_sensor": ("二元传感器", "Binary sensor"),
    "camera": ("摄像头", "Camera"),
    "climate": ("空调", "Climate"),
    "cover": ("窗帘", "Cover"),
    "fan": ("风扇", "Fan"),
    "group": ("组", "Group"),
    "input_boolean": ("输入布尔", "Input boolean"),
    "light": ("灯", "Light"),
    "lock": ("锁", "Lock"),
    "media_player": ("媒体播放器", "Media player"),
    "remote": ("遥控器", "Remote"),
    "scene": ("场景", "Scene"),
    "script": ("脚本", "Script"),
    "sensor": ("环境传感器", "Sensor"),
    "siren": ("警报器", "Siren"),
    "switch": ("开关", "Switch"),
    "vacuum": ("扫地机", "Vacuum"),
}

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_UID): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for bemfa."""

    VERSION = 1

    # Bemfa service uses uid to auth api calls. One shall provide his uid to config this integration.
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_USER_DATA_SCHEMA, last_step=True
            )

        # uid should match this regExp
        if not re.match("^[0-9a-f]{32}$", user_input[CONF_UID]):
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "invalid_uid"},
                last_step=True,
            )

        # Multiply integration instances with same uid may case unexpected results.
        # We treat the md5sum of each configured uid as unique.
        uid_md5 = hashlib.md5(user_input[CONF_UID].encode("utf-8")).hexdigest()
        await self.async_set_unique_id(uid_md5)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="",
            data=user_input,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle a option flow for bemfa."""

    # creat or modify a sync
    _is_create: bool

    # a dict to hold syncs when create / modify one of them
    # with this map we can get it in the next step
    _sync_dict: dict[str, Sync]

    # sync type selected for creating syncs
    _sync_type: str

    # current sync we are creating or modifu
    _sync: Sync

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry_id = config_entry.entry_id
        self._config = (
            config_entry.options[OPTIONS_CONFIG].copy()
            if OPTIONS_CONFIG in config_entry.options
            else {}
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "create_sync",
                "modify_sync",
                "destroy_sync",
            ],
        )

    async def async_step_create_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create a hass-to-bemfa sync."""
        if user_input is not None:
            self._sync_type = user_input[OPTIONS_SYNC_TYPE]
            return await self.async_step_create_sync_entities()

        service = self._get_service()
        all_topics = await service.async_fetch_all_topics()
        all_syncs = service.collect_supported_syncs()
        self._sync_dict = {}
        for sync in all_syncs:
            if sync.topic not in all_topics:
                self._sync_dict[sync.entity_id] = sync

        if not bool(self._sync_dict):
            return self.async_show_form(step_id="empty", last_step=False)

        self._is_create = True
        type_options = self._generate_sync_type_options(self._sync_dict.values())

        return self.async_show_form(
            step_id="create_sync",
            data_schema=vol.Schema(
                {
                    vol.Required(OPTIONS_SYNC_TYPE): SelectSelector(
                        SelectSelectorConfig(
                            options=type_options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            last_step=False,
        )

    async def async_step_create_sync_entities(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select one or more hass entities to sync."""
        if user_input is not None:
            selected = user_input[OPTIONS_SELECT]
            if isinstance(selected, str):
                selected = [selected]

            syncs = [
                self._sync_dict[entity_id]
                for entity_id in selected
                if entity_id in self._sync_dict
                and self._sync_type == self._get_sync_type(self._sync_dict[entity_id])
            ]

            if not syncs:
                return await self.async_step_create_sync_entities()

            if len(syncs) == 1:
                self._sync = syncs[0]
                return await self._async_step_sync_config()

            service = self._get_service()
            for sync in syncs:
                await service.async_create_sync(sync, {OPTIONS_NAME: sync.name})

            return self.async_create_entry(
                title="", data={OPTIONS_CONFIG: self._config}
            )

        syncs = [
            sync
            for sync in self._sync_dict.values()
            if self._sync_type == self._get_sync_type(sync)
        ]
        if not syncs:
            return self.async_show_form(step_id="empty", last_step=False)

        entity_ids = [sync.entity_id for sync in syncs]
        domain_filter = self._get_sync_type_domain(self._sync_type)
        if domain_filter is not None:
            selector = EntitySelector(
                EntitySelectorConfig(
                    domain=domain_filter,
                    include_entities=entity_ids,
                    multiple=True,
                )
            )
        else:
            selector = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(
                            value=sync.entity_id,
                            label=sync.generate_option_label(),
                        )
                        for sync in syncs
                    ],
                    mode=SelectSelectorMode.LIST,
                    multiple=True,
                )
            )

        return self.async_show_form(
            step_id="create_sync_entities",
            data_schema=vol.Schema({vol.Required(OPTIONS_SELECT): selector}),
            last_step=False,
        )

    async def async_step_modify_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Modify a hass-to-bemfa sync."""
        if user_input is not None:
            self._sync = self._sync_dict[user_input[OPTIONS_SELECT]]
            return await self._async_step_sync_config()

        service = self._get_service()
        all_topics = await service.async_fetch_all_topics()
        all_syncs = service.collect_supported_syncs()
        self._sync_dict = {}
        for sync in all_syncs:
            if sync.topic in all_topics:
                sync.name = all_topics[sync.topic]
                self._sync_dict[sync.entity_id] = sync

        if not bool(self._sync_dict):
            return self.async_show_form(step_id="empty", last_step=False)

        self._is_create = False

        return self.async_show_form(
            step_id="modify_sync",
            data_schema=vol.Schema(
                {
                    vol.Required(OPTIONS_SELECT): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=sync.entity_id,
                                    label=sync.generate_option_label(),
                                )
                                for sync in self._sync_dict.values()
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            last_step=False,
        )

    async def _async_step_sync_config(self) -> FlowResult:
        """Set details of a hass-to-bemfa sync."""
        if self._sync.topic in self._config:
            self._sync.config = self._config[self._sync.topic]

        return self.async_show_form(
            step_id=self._sync.get_config_step_id(),
            data_schema=vol.Schema(self._sync.generate_details_schema()),
        )

    async def async_step_sync_config_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set details of a hass-to-bemfa sensor sync."""
        return await self._async_step_sync_config_done(user_input)

    async def async_step_sync_config_binary_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set details of a hass-to-bemfa binary sensor sync."""
        return await self._async_step_sync_config_done(user_input)

    async def async_step_sync_config_climate(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set details of a hass-to-bemfa climate sync."""
        return await self._async_step_sync_config_done(user_input)

    async def async_step_sync_config_cover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set details of a hass-to-bemfa cover sync."""
        return await self._async_step_sync_config_done(user_input)

    async def async_step_sync_config_fan(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set details of a hass-to-bemfa fan sync."""
        return await self._async_step_sync_config_done(user_input)

    async def async_step_sync_config_light(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set details of a hass-to-bemfa light sync."""
        return await self._async_step_sync_config_done(user_input)

    async def async_step_sync_config_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Set details of a hass-to-bemfa switch sync."""
        return await self._async_step_sync_config_done(user_input)

    async def _async_step_sync_config_done(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        service = self._get_service()
        if self._is_create:
            await service.async_create_sync(self._sync, user_input)
        else:
            await service.async_modify_sync(self._sync, user_input)

        # store config to integration options
        if self._sync.config:
            self._config[self._sync.topic] = self._sync.config
        elif self._sync.topic in self._config:
            self._config.pop(self._sync.topic)
        return self.async_create_entry(title="", data={OPTIONS_CONFIG: self._config})

    async def async_step_destroy_sync(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Destroy hass-to-bemfa sync(s)"""
        service = self._get_service()
        if user_input is not None:
            for topic in user_input[OPTIONS_SELECT]:
                await service.async_destroy_sync(topic)
                if topic in self._config:
                    self._config.pop(topic)
            return self.async_create_entry(
                title="", data={OPTIONS_CONFIG: self._config}
            )

        all_topics = await service.async_fetch_all_topics()
        all_syncs = service.collect_supported_syncs()
        topic_map: dict[str, str] = {}
        for sync in all_syncs:
            if sync.topic in all_topics:
                sync.name = all_topics[sync.topic]
                all_topics.pop(sync.topic)
                topic_map[sync.topic] = sync.generate_option_label()

        for (topic, name) in all_topics.items():
            topic_map[topic] = "[?] {name}".format(name=name)

        if not bool(topic_map):
            return self.async_show_form(step_id="empty", last_step=False)
        return self.async_show_form(
            step_id="destroy_sync",
            data_schema=vol.Schema(
                {
                    vol.Required(OPTIONS_SELECT): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=value,
                                    label=label,
                                )
                                for (value, label) in topic_map.items()
                            ],
                            mode=SelectSelectorMode.LIST,
                            multiple=True,
                        )
                    )
                }
            ),
        )

    async def async_step_empty(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """No syncs found."""
        return await self.async_step_init(user_input)

    def _get_service(self) -> BemfaService:
        return self.hass.data[DOMAIN].get(self._entry_id)["service"]

    def _generate_sync_type_options(self, syncs) -> list[SelectOptionDict]:
        """Generate options for sync type selector."""
        counts: dict[str, int] = {}
        for sync in syncs:
            sync_type = self._get_sync_type(sync)
            counts[sync_type] = counts.get(sync_type, 0) + 1

        return [
            SelectOptionDict(
                value=sync_type,
                label=f"{self._get_sync_type_label(sync_type)} ({counts[sync_type]})",
            )
            for sync_type in sorted(counts)
        ]

    def _get_sync_type_label(self, sync_type: str) -> str:
        """Return localized label for a sync type."""
        labels = SYNC_TYPE_LABELS.get(sync_type)
        if labels is None:
            return sync_type

        language = getattr(self.hass.config, "language", None)
        return labels[0] if language is not None and language.startswith("zh") else labels[1]

    def _get_sync_type(self, sync: Sync) -> str:
        """Find registered sync type name for a sync instance."""
        for sync_type, sync_cls in SYNC_TYPES.items():
            if type(sync) is sync_cls:
                return sync_type
        for sync_type, sync_cls in SYNC_TYPES.items():
            if isinstance(sync, sync_cls):
                return sync_type
        return sync.entity_id.split(".")[0]

    def _get_sync_type_domain(self, sync_type: str) -> str | list[str] | None:
        """Return HA entity domain filter for an entity-backed sync type."""
        sync_cls = SYNC_TYPES.get(sync_type)
        if sync_cls is None or not hasattr(sync_cls, "_supported_domain"):
            return None
        return sync_cls._supported_domain()
