import logging
import os
import ssl
import sys

import certifi
import yaml
from imap_tools import BaseMailBox, MailBox

from mail_juicer.models.action import Action, ActionLoader, DeleteAction, FlagAction, MoveAction
from mail_juicer.models.enums import Flag
from mail_juicer.models.rule import Rule
from mail_juicer.models.settings import Settings

logger = logging.getLogger(__name__)


def make_ssl_context():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.set_ciphers("DEFAULT@SECLEVEL=1")
    context.load_verify_locations(
        cafile=os.path.relpath(certifi.where()), capath=None, cadata=None
    )
    return context


default_actions = {
    "delete": DeleteAction(),
    "trash": MoveAction(dest="Trash"),
    "mark_read": FlagAction(flag=Flag.SEEN),
}


class State:
    def __init__(self):
        self._settings = None
        self._rules = None
        self._mailbox = None
        self.actions: dict[str, Action] = default_actions

    def create_mailbox(self):
        ssl_context = make_ssl_context()
        self._mailbox = MailBox(self.settings.server, ssl_context=ssl_context).login(
            self.settings.username, self.settings.password
        )

    def parse_config(self, config_raw):
        try:
            config_dict = yaml.safe_load(config_raw)
        except Exception:
            logger.exception("Failed loading config file, check that the yaml syntax is valid.")
            raise

        if (
            not isinstance(config_dict, dict)
            or (config_dict.keys() - {"rules", "settings", "actions"}) != set()
            or "rules" not in config_dict
            or "settings" not in config_dict
        ):
            logger.error(
                "The config file should contain a mapping with the keys 'rules', 'settings' and 'actions' (optional)."
            )
            sys.exit(1)

        try:
            self._settings = Settings(**config_dict["settings"])
        except Exception as exc:
            logger.error("Failed parsing the 'settings' section of the configuration:")
            logger.error(exc)
            sys.exit(1)

        parsed_rules = []
        for rule_dict in config_dict["rules"]:
            try:
                parsed_rules.append(Rule.parse_obj(rule_dict))
            except Exception as exc:
                logger.error("Failed parsing the 'rules' section of the configuration:")
                logger.error(rule_dict)
                logger.error(exc)
                sys.exit(1)
        self._rules = parsed_rules

        if "actions" in config_dict:
            if not isinstance(config_dict["actions"], dict):
                logger.error(f"'actions' value is not a mapping: {config_dict['actions']}")
                sys.exit(1)
            for action_name, action_dict in config_dict["actions"].items():
                if action_name in self.actions:
                    logger.warning(f"Overriding default action f{action_name}")
                try:
                    self.actions[action_name] = ActionLoader.parse_obj(action_dict).__root__
                except Exception as exc:
                    logger.error("Failed parsing the 'actions' section of the configuration:")
                    logger.error(action_dict)
                    logger.error(exc)
                    sys.exit(1)
            self._rules = parsed_rules

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            raise Exception("Uninitialized settings")
        return self._settings

    @property
    def rules(self) -> list[Rule]:
        if self._rules is None:
            raise Exception("Uninitialized rules")
        return self._rules

    @property
    def mailbox(self) -> BaseMailBox:
        if self._mailbox is None:
            raise Exception("Uninitialized mailbox")
        return self._mailbox


state = State()