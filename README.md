# YAYCL: YAML Configuration loader and cache

All YAML files stored in the given directory are automatically parsed and loaded on request.
The parsed files are exposed as object attributes based on the yaml file name. 

For example, consider a ``conf/config.yaml`` file:

```yaml
dict_key:
    key1: value1
    key2: value2
    key3: value3
list_key:
    - 1
    - 2
    - 3
string_key: 'string value'
```

Now, you can interact with that yaml in python with minimal fuss:
```python
import yaycl
conf = yaycl.Config('conf')
# assuming config.yaml is valid yaml, this should work:
assert 'key2' in conf.config.dict_key
```

Once loaded, the yaml contents are cached. The entire cache of a config object can be cleared,
or a single config file's cache can be cleared:
```python
conf.clear()  # clears the entire cache
conf.config.clear() or conf['config'].clear()  # clears the cache only for config.yaml
```

Note that, as in the example above, yaml files loaded by yaycl (currently) must be a mapping type at the top level. Files containing more than one yaml document are (currently) unsupported.

## Module Impersonation

`yaycl.Config` is indended to manage config files for an entire project. To facilitate
that goal, it supports acting as a module, making configurations importable.

The module's name doesn't matter, as long as it can be imported by that name.

In this example, we'll make a module called `conf.py`, with contents:

```python
import sys

from yaycl import Config

sys.modules[__name__] = Config('/path/to/yaml/config/dir')
```

Now, the first time `conf` is imported, it will replace itself in conf with an instance of
`yaycl.Config`, which will be what python imports thereafter. Once done, you can import config
files directly. Here's the same example from before, but using the direct import method:

```python
from conf import config
assert 'key2' in conf.config.dict_key
```

For brevity, following examples will use the module impersonation mechanism.

## Shenanigans

Special care has been taken to ensure that all objects are mutated, rather than replaced,
so all names will reference the same config object.

All objects representing config files (attributes or items accessed directly from the conf
module) will be some type of `AttrDict`. Attempting to make such a config object be anything
other than an `AttrDict` (see "Inherited methods section below)  will probably break everything
and should not be attempted, lest shenanigans be called.

```python
# Don't do this...
conf.key = 'not a dict'
# ...or this.
conf['key'] = ['also', 'not', 'a', 'dict']
```

Generally speaking, with the exception of runtime overrides (see below), a `yaycl.Config` instance
should be considered read-only.

# Local Configuration Overrides

In addition to loading YAML files, the `yacl.Config` loader supports local override
files. This feature is useful for maintaining a shared set of config files for a team, while
still allowing for local configuration.

Take the following example YAML file, `config.local.yaml`:

```yaml
string_key: 'new string value'
```

When loaded by the conf loader, the `string_key` will be automatically overridden by the value
in the local YAML file::

```python
from conf import config
print config.string_key
```

This will print: `new string value`, instead of the value in the base config, `string value`

The existing keys (`dict_key` and `list_key` in this case) will not altered by the local
config override.

This allows for configurations to be stored in revision control, while still making it trivial
to test new configs, override an existing config, or even create configs that only exist
locally.

```
# .gitignore suggestion; adapt to your SCM of choice
*.local.yaml
```

# Runtime Overrides

Sometimes writing to the config files is an inconvenient way to ensure that runtime changes
persist through configuration cache clearing. These "runtime" changes can be stashed in the
runtime overrides dict, allowing them to persist through a cache clear.

The runtime overrides dictionary mimics the layout of the conf module itself, where
configuration file names are keys in the runtime overrides dictionary. So, for example, to
update the base_url in a way that will persist clearing of the cache, the following will work:

```python
import conf
conf.runtime['config']['string_key'] = 'overridden string key'
print conf.config.string_key
```

That should print `overridden string key`

## runtime.yaml

If you have a config file named 'runtime.yaml' that you'd like to load, or really any config
name that interferes with python names ('get.yaml', for example), note that the configs are
always available via dictionary lookup; attribute lookup is supported for brevity, but dict
item lookup should always work.

```python
conf.runtime['runtime'] = {'shenanigans': True}
assert conf['runtime']['shenanigans']
```

# Inherited methods

Once loaded, all configs are instances of `AttrDict`, a very helpful class from the
[layered-yaml-attrdict-config](https://pypi.python.org/pypi/layered-yaml-attrdict-config/)
package. As such, all methods normally available to AttrDicts are available here.

For example, `Config.save` and `Config`'s inheritance abilities rely on `AttrDict`'s
`dump` and `rebase` methods, respectively.

Of course, since `AttrDict` is a `dict` subclass, dictionary methods can also be used to
manipulate a `yaycl.Config` at runtime. The `clear` method is particularly
useful as a means to trigger a reload of all config files by clearing yaycl's cache.

# Thread safety

No care whatsoever has been taken to ensure thread-safety, so if you're doing threaded
things with the conf module you should manage your own locking when making any conf
changes. Since most config are loaded from the filesystem, generally this means that
any changes to the runtime overrides should be done under a lock.

[![Coverage Status](https://coveralls.io/repos/seandst/yaycl/badge.svg?branch=master)](https://coveralls.io/r/seandst/yaycl?branch=master)
[![Build Status](https://travis-ci.org/seandst/yaycl.svg?branch=master)](https://travis-ci.org/seandst/yaycl)
