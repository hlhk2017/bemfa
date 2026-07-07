"""Support for bemfa service."""

import logging
from typing import Any
import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import ATTR_DEVICE_CLASS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry
from homeassistant.helpers import entity_registry
from homeassistant.helpers import device_registry
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from .utils import has_key
from .const import (
    OPTIONS_CO2,
    OPTIONS_HUMIDITY,
    OPTIONS_ILLUMINANCE,
    OPTIONS_PM25,
    OPTIONS_TEMPERATURE,
    TopicSuffix,
)
from .sync import SYNC_TYPES, Sync

_LOGGING = logging.getLogger(__name__)

def area_entities(hass: HomeAssistant, area_name_or_id: str) -> set[str]:
    ar_reg = area_registry.async_get(hass)
    area = ar_reg.async_get_area(area_name_or_id)
    if area is None:
        for a in ar_reg.async_list_areas():
            if a.name == area_name_or_id:
                area = a
                break
    if area is None:
        return set()
    area_id = area.id
    ent_reg = entity_registry.async_get(hass)
    dev_reg = device_registry.async_get(hass)
    result: set[str] = set()
    for entry in list(ent_reg.entities.values()):
        if entry.area_id == area_id:
            result.add(entry.entity_id)
            continue
        if entry.device_id is not None:
            device = dev_reg.async_get(entry.device_id)
            if device is not None and device.area_id == area_id:
                result.add(entry.entity_id)
    return result


@SYNC_TYPES.register("sensor")
class Sensor(Sync):
    """Sync a hass area to bemfa sensor device."""

    @staticmethod
    def get_config_step_id() -> str:
        return "sync_config_sensor"

    @staticmethod
    def _get_topic_suffix() -> TopicSuffix:
        return TopicSuffix.SENSOR

    @classmethod
    def collect_supported_syncs(cls, hass: HomeAssistant):
        """Collect area packaged sensors and environmental sensor entities."""
        syncs = [
            cls(hass, "area.{id}".format(id=area.id), area.name)
            for area in area_registry.async_get(hass).async_list_areas()
        ]

        syncs.extend(
            cls(hass, state.entity_id, state.name)
            for state in hass.states.async_all(SENSOR_DOMAIN)
        )
        return syncs

    def generate_details_schema(self) -> dict[str, Any]:
        temperature_sensors: dict[str, str] = {}
        humidity_sensors: dict[str, str] = {}
        illuminance_sensors: dict[str, str] = {}
        pm25_sensors: dict[str, str] = {}
        co2_sensors: dict[str, str] = {}

        if self._entity_id.startswith(f"{SENSOR_DOMAIN}."):
            state = self._hass.states.get(self._entity_id)
            if state is not None:
                self._add_sensor_option(
                    state,
                    self._get_sensor_option_key(state.attributes),
                    {
                        OPTIONS_TEMPERATURE: temperature_sensors,
                        OPTIONS_HUMIDITY: humidity_sensors,
                        OPTIONS_ILLUMINANCE: illuminance_sensors,
                        OPTIONS_PM25: pm25_sensors,
                        OPTIONS_CO2: co2_sensors,
                    },
                )
        else:
            # filter entities in our area
            a_entities = area_entities(self._hass, self._entity_id.split(".")[1])

            for state in self._hass.states.async_all(SENSOR_DOMAIN):
                if state.entity_id not in a_entities:
                    continue
                if not has_key(state.attributes, ATTR_DEVICE_CLASS):
                    continue
                self._add_sensor_option(
                    state,
                    self._get_sensor_option_key(state.attributes),
                    {
                        OPTIONS_TEMPERATURE: temperature_sensors,
                        OPTIONS_HUMIDITY: humidity_sensors,
                        OPTIONS_ILLUMINANCE: illuminance_sensors,
                        OPTIONS_PM25: pm25_sensors,
                        OPTIONS_CO2: co2_sensors,
                    },
                )
        schema = super().generate_details_schema()
        for (_t, _d) in (
            (OPTIONS_TEMPERATURE, temperature_sensors),
            (OPTIONS_HUMIDITY, humidity_sensors),
            (OPTIONS_ILLUMINANCE, illuminance_sensors),
            (OPTIONS_PM25, pm25_sensors),
            (OPTIONS_CO2, co2_sensors),
        ):
            if _d:
                schema[
                    vol.Optional(
                        _t,
                        description={
                            "suggested_value": self._config[_t]
                            if _t in self._config and self._config[_t] in _d
                            else list(_d.keys())[0]
                        },
                    )
                ] = SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=value,
                                label=label,
                            )
                            for (value, label) in _d.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
        return schema

    def _add_sensor_option(
        self,
        state,
        option_key: str,
        sensor_options: dict[str, dict[str, str]],
    ) -> None:
        """Add an environmental sensor to the matching option map."""
        sensor_options[option_key][state.entity_id] = "{name} ({id})".format(
            name=state.name, id=state.entity_id
        )

    def _get_sensor_option_key(self, attributes) -> str:
        """Map a sensor entity to a Bemfa environmental sensor field."""
        if not has_key(attributes, ATTR_DEVICE_CLASS):
            return OPTIONS_TEMPERATURE

        device_class = attributes[ATTR_DEVICE_CLASS]
        if device_class == "humidity":
            return OPTIONS_HUMIDITY
        if device_class == "illuminance":
            return OPTIONS_ILLUMINANCE
        if device_class == "pm25":
            return OPTIONS_PM25
        if device_class == "carbon_dioxide":
            return OPTIONS_CO2

        return OPTIONS_TEMPERATURE

    def get_watched_entity_ids(self) -> list[str]:
        ids: list[str] = []
        for name in (
            OPTIONS_TEMPERATURE,
            OPTIONS_HUMIDITY,
            OPTIONS_ILLUMINANCE,
            OPTIONS_PM25,
            OPTIONS_CO2,
        ):
            if name in self._config:
                ids.append(self._config[name])
        return ids

    def _generate_msg_parts(self) -> list[str]:
        msg: list[str] = [""]
        for name in (
            OPTIONS_TEMPERATURE,
            OPTIONS_HUMIDITY,
            "",
            OPTIONS_ILLUMINANCE,
            OPTIONS_PM25,
            OPTIONS_CO2,
        ):
            if not name:
                msg.append("")
                continue
            if name not in self._config:
                msg.append("")
                continue
            state = self._hass.states.get(self._config[name])
            msg.append(state.state if state is not None else "")
        return msg
