# -*- coding: utf-8 -*-
from collections import defaultdict
from functools import partial
from warnings import catch_warnings, warn

import os
import yaml
from pkg_resources import iter_entry_points

from lya import AttrDict, OrderedDictYAMLLoader


class ConfigNotFound(UserWarning):
    pass


class ConfigInvalid(UserWarning):
    pass


class InvalidInheritPath(UserWarning):
    pass


class Config(dict):
    """Configuration YAML loader and cache"""
    def __init__(self, config_dir, **kwargs):
        # private yaycl conf, plugins can stash info here for configuration
        self._yaycl = AttrDict({'config_dir': config_dir})
        self._yaycl.update(kwargs)
        self._runtime = ConfigTree(self)

    def _runtime_overrides(self):
        return self._runtime

    def _set_runtime_overrides(self, overrides_dict):
        self._runtime.update(overrides_dict)

    def _del_runtime_overrides(self):
        self._runtime.clear()

    runtime = property(_runtime_overrides, _set_runtime_overrides, _del_runtime_overrides)

    def save(self, key):
        """Write out an in-memory config to the conf dir

        Warning: This will destroy any formatting or ordering that existed in the original yaml

        """
        with open(os.path.join(self._yaycl.config_dir, '%s.yaml' % key), 'w') as conf_file:
            self[key].dump(conf_file)

    # Support for descriptor access, e.g. instance.attrname
    # Note that this is only on the get side, for support of nefarious things
    # like setting and deleting, use the normal dict interface.
    def __getattribute__(self, attr):
        # Attempt normal object attr lookup; delegate to the dict interface if that fails
        try:
            return super(Config, self).__getattribute__(attr)
        except AttributeError:
            # try to load from cache first if this conf is already known
            if attr in self:
                return self[attr]

            if attr.startswith('_'):
                # don't try to load private names
                raise

            # If we're here, trigger the loader via getitem
            return self[attr]

    def __getitem__(self, key):
        # Attempt a normal dict lookup to pull a cached conf
        if key not in self:
            super(Config, self).__setitem__(key, AttrDict())
            # Cache miss, populate this conf key
            # Call out to dict's setitem here since this is the only place where we're allowed to
            # create a new key and we want the default behavior instead of the override below
            self._populate(key)
        return super(Config, self).__getitem__(key)

    def __setitem__(self, key, value):
        self[key].clear()
        self[key].update(value)

    def __delitem__(self, key):
        self[key].clear()
        self._populate(key)

    def _inherit(self, conf_key):
        """Recurses through an object looking for 'inherit' clauses and replaces them with their
        real counterparts. In the case of a dict, the inherit clause remains, in the case of
        anything else, a replacement occurs such that:

        sim5:
          key: value
          newkey: newvalue

        sim6:
          tags:
            - tag1
            - tag2
        sim7:
          inherit: management_systems/sim5
          test:
              tags:
                  inherit: management_systems/sim6/tags

        Will produce the following output if requesting management_systems/sim7

          inherit: management_systems/sim5
          key: value
          newkey: newvalue
          test:
              tags:
                  - tag1
                  - tag2
        """
        for keys in self._needs_inherit(conf_key):
            # get the dict containing inherit key
            keys, root_key = keys[:-1], keys[-1]
            root = self[conf_key]
            for k in keys:
                root = root[k]

            # find the dict we're inheriting based on value
            base = self[conf_key]
            try:
                for path_element in root[root_key]['inherit'].split('/'):
                    base = base[path_element]
            except KeyError:
                warn('{} path cannot be traversed, {} does not exist'.format(
                    root[root_key]['inherit'], path_element), InvalidInheritPath)

            # rebase if the base was an attrdict,
            # otherwise overwrite the key in-place
            if isinstance(base, AttrDict):
                del(root[root_key]['inherit'])
                root[root_key].rebase(base)
            else:
                root[root_key] = base

    def _needs_inherit(self, conf_key):
        conf = self[conf_key]
        # loop over keys until all the inherits are gone
        while True:
            seen_inherit = False
            for k, v in conf.flatten_dict(conf):
                if k[-1] == 'inherit':
                    # give back the keys needed to get to a dict containing an inherit key
                    seen_inherit = True
                    yield k[:-1]
            if not seen_inherit:
                break

    def _populate(self, key):
        yaml_dict = self._load_yaml(key)

        # Graft in local yaml updates if they're available
        with catch_warnings():
            local_yaml = '%s.local' % key
            local_yaml_dict = load_yaml(self, local_yaml, warn_on_fail=False)
            if local_yaml_dict:
                yaml_dict.update_dict(local_yaml_dict)

        # Graft on the runtime overrides
        yaml_dict.update(self.runtime.get(key, {}))
        self[key].update(yaml_dict)
        self._inherit(key)

    def clear(self):
        # because of the 'from conf import foo' mechanism, we need to clear each key in-place,
        # and reload the runtime overrides. Once a key is created in this dict, its value MUST NOT
        # change to a different dict object.
        for key in self:
            # clear the conf dict in-place
            self[key].clear()
            self._populate(key)

    def _load_yaml(self, conf_key, warn_on_fail=True):
        # sort the default loader last
        # return the first conf loader that succeeds,
        # otherwise return the last conf that was loaded
        for ep in sorted(iter_entry_points('yaycl.load_yaml'),
                key=lambda ep: ep.name == 'default'):
            loader = ep.load()
            conf = loader(self, conf_key, warn)
            if conf:
                return conf
        else:
            # Since we put default last, the last conf loaded will
            # an empty AttrDict; warn and return
            if warn_on_fail:
                msg = 'Unable to load configuration "{}"'.format(conf_key)
                warn(msg, ConfigNotFound)
            return conf


class ConfigTree(defaultdict):
    """A tree class that knows to clear the config when mutated

    This ensures runtime overrides persist though conf changes while
    still making it easy to nest items/attrs as much as needed to
    override a specific conf branch easily.

    This supports item getters and setters similar to ``AttrDict``,
    but attr getters and setters are currently unsupported.

    """
    def __init__(self, conf, *args, **kwargs):
        self._conf = conf
        tree_constructor = partial(type(self), conf)
        super(ConfigTree, self).__init__(tree_constructor, *args, **kwargs)

    @property
    def _sup(self):
        return super(ConfigTree, self)

    def __setitem__(self, key, value):
        self._sup.__setitem__(key, value)
        self._clear_conf()

    def __delitem__(self, key):
        self._sup.__delitem__(key)
        self._clear_conf()

    def update(self, other):
        self._sup.update(other)
        self._clear_conf()

    def clear(self):
        self._sup.clear()
        self._clear_conf()

    def _clear_conf(self):
        if self._conf:
            self._conf.clear()


def load_yaml(conf, conf_key, warn_on_fail=True):
    loaded_yaml = AttrDict()

    filename = os.path.join(conf._yaycl.config_dir, '{}.yaml'.format(conf_key))

    # Find the requested yaml in the yaml dir
    if os.path.exists(filename):
        with open(filename) as config_fh:
            try:
                loaded_yaml.update(yaml.load(config_fh, Loader=OrderedDictYAMLLoader))
            except:
                warn('Unable to parse configuration file at {}'.format(filename), ConfigInvalid)

    return loaded_yaml

