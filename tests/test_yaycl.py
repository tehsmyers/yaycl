import os
import random
import string
from warnings import catch_warnings, resetwarnings

import pytest
from lya import AttrDict

from yaycl import Config, ConfigTree, ConfigNotFound, ConfigInvalid

test_yaml_contents = '''
test_key: test_value
nested_test_root:
    nested_test_key_1: nested_test_value_1
    nested_test_key_2: nested_test_value_2
inherit_value:
    inherit: nested_test_root
    inherit_nested_value:
        inherit: inherit_value
'''

local_test_yaml_contents = '''
test_key: test_overridden_value
nested_test_root:
    nested_test_key_1: overridden_nested_test_value
'''

invalid_test_yaml_contents = '''
% this isn't valid yaml
'''


@pytest.fixture
def clear_conf(conf):
    # Ensure the conf is cleared before every test
    conf.clear()
    conf.runtime.clear()
pytestmark = pytest.mark.usefixtures('clear_conf')


@pytest.fixture
def random_string():
    return ''.join((random.choice(string.letters) for _ in xrange(8)))


@pytest.fixture
def test_yaml(request, random_string):
    test_yaml = create_test_yaml(request, conf, test_yaml_contents, random_string)
    filename, ext = os.path.splitext(os.path.basename(test_yaml.name))
    return filename


@pytest.fixture(scope='session')
def conf_dir(request):
    dir = request.session.fspath.join('tests', 'conf')
    dir.ensure(dir=True)
    request.addfinalizer(lambda: delete_path(dir))
    return dir


@pytest.fixture
def conf(conf_dir):
    return Config(conf_dir.strpath)

def create_test_yaml(request, conf, contents, filename, local=False):
    if local:
        suffix = '.local.yaml'
    else:
        suffix = '.yaml'
    filename += suffix

    full_path = conf_dir(request).join(filename)

    test_yaml = full_path.open('w')
    test_yaml.write(contents)
    test_yaml.flush()
    test_yaml.seek(0)

    request.addfinalizer(lambda: delete_path(full_path))

    return test_yaml


def delete_path(path):
    if path.check():
        path.remove()

def test_conf_basics(test_yaml, conf):
    # Dict lookup method works
    assert conf[test_yaml]['test_key'] == 'test_value'
    assert isinstance(conf, Config)
    assert isinstance(conf.runtime, ConfigTree)
    assert isinstance(conf[test_yaml], AttrDict)
    assert isinstance(conf[test_yaml]['nested_test_root'], AttrDict)
    assert isinstance(conf[test_yaml].nested_test_root, AttrDict)
    assert conf[test_yaml]['nested_test_root'] is conf[test_yaml].nested_test_root


def test_conf_yamls_item(test_yaml, conf):
    # delitem doesn't really delete, it only clears in-place
    old_test_yaml = conf[test_yaml]
    del(conf[test_yaml])
    assert conf[test_yaml] is old_test_yaml

    # setitem doesn't really set, it only updates in-place
    conf[test_yaml] = {'foo': 'bar'}
    assert conf[test_yaml] is old_test_yaml


def test_conf_yamls_attr(test_yaml, conf):
    # Attribute lookup method works
    assert getattr(conf, test_yaml)['test_key'] == 'test_value'


def test_conf_yamls_save(request, test_yaml, conf):
    save_test = conf_dir(request).join('{}.yaml'.format('save_test'))
    request.addfinalizer(lambda: delete_path(save_test))
    with create_test_yaml(request, conf, local_test_yaml_contents, test_yaml):
        assert not save_test.check()
        conf['save_test'].update(conf[test_yaml])
        conf.save('save_test')
        del(conf['save_test'])
        assert save_test.check
        assert sorted(conf['save_test']) == sorted(conf[test_yaml])


def test_conf_yamls_override(request, test_yaml, conf):
    # Make a .local.yaml file with the same root name as test_yaml,
    with create_test_yaml(request, conf, local_test_yaml_contents, test_yaml, local=True):
        # Check that the simple local override works.
        assert conf[test_yaml]['test_key'] == 'test_overridden_value'

        # Check that the local override of specific nested keys works.
        nested_root = conf[test_yaml]['nested_test_root']
        assert nested_root['nested_test_key_1'] == 'overridden_nested_test_value'
        assert nested_root['nested_test_key_2'] == 'nested_test_value_2'


def test_conf_yamls_import(test_yaml, conf):
    # Emulate from conf import $test_yaml
    assert getattr(conf, test_yaml) == conf[test_yaml]


def test_conf_yamls_not_found(random_string, conf, recwarn):
    # Make sure the the ConfigNotFound warning is issued correctly
    resetwarnings()
    conf[random_string]
    assert recwarn.pop(ConfigNotFound)


def test_conf_doesnt_load_privates(conf):
    with pytest.raises(AttributeError):
        assert conf._private


def test_conf_runtime_override(random_string, conf):
    # Add the random string to the runtime dict, as well as a junk value to
    # prove we can add more than one thing via the ConfTree
    conf.runtime['test_config'][random_string] = True
    conf.runtime['foo'] = 'bar'
    # the override is in place
    assert random_string in conf.test_config
    conf.clear()
    # the override is still in place
    assert random_string in conf.test_config
    # both item and attr access works
    assert conf.test_config[random_string] is True
    assert getattr(conf.test_config, random_string) is True
    # deleting works
    del(conf.runtime['test_config'][random_string])
    assert random_string not in conf.test_config


def test_conf_runtime_set(random_string, conf):
    # setting runtime directly works, and doesn't change the object that runtime points to
    old_runtime = conf.runtime
    conf.runtime = {'test_config': {random_string: True}}
    conf.runtime is old_runtime
    assert random_string in conf.test_config


def test_conf_runtime_update(random_string, conf):
    # In addition to direct nested assignment, dict update should also work
    conf.runtime.update({'test_config': {random_string: True}})
    assert random_string in conf.test_config


def test_conf_runtime_clear(test_yaml, random_string, conf):
    conf.runtime[test_yaml]['test_key'] = random_string
    assert conf[test_yaml]['test_key'] == random_string
    conf.runtime.clear()
    assert conf[test_yaml]['test_key'] == 'test_value'


def test_conf_runtime_del(test_yaml, random_string, conf):
    conf.runtime[test_yaml]['test_key'] = random_string
    assert conf[test_yaml]['test_key'] == random_string
    del(conf.runtime)
    assert conf[test_yaml]['test_key'] == 'test_value'


def test_conf_imported_attr(test_yaml, random_string, conf):
    # "from conf import attr" should be the same object as "conf.attr"
    # mutating the runtime dict shouldn't change that
    imported_test_yaml = getattr(conf, test_yaml)
    conf.runtime[test_yaml]['test_key'] = random_string
    assert imported_test_yaml['test_key'] == random_string
    assert imported_test_yaml is getattr(conf, test_yaml)


def test_conf_override_before_import(test_yaml, random_string, conf):
    # You should be able to create a "fake" config file by preseeding the runtime overrides
    conf.runtime['foo']['test_key'] = random_string
    foo = getattr(conf, 'foo')
    assert foo['test_key'] == random_string


def test_conf_load_invalid_yaml(request, test_yaml, random_string, conf, recwarn):
    resetwarnings()
    with create_test_yaml(request, conf, invalid_test_yaml_contents, test_yaml, local=True):
        conf[test_yaml]
        assert recwarn.pop(ConfigInvalid)


def test_inheritance(request, test_yaml, conf):
    with create_test_yaml(request, conf, local_test_yaml_contents, test_yaml, local=True):
        # Check that nested iheritance (and thus inheritance itself) works
        assert (conf[test_yaml].nested_test_root ==
            conf[test_yaml].inherit_value.inherit_nested_value)


def test_impersonate_module(request, test_yaml, conf):
    import importlib
    import sys
    with create_test_yaml(request, conf, local_test_yaml_contents, test_yaml, local=True):
        # put our module-to-be in sys.modules
        sys.modules['conf'] = conf
        # simulate 'from conf import test_yaml'
        conf_module = importlib.import_module('conf')
        assert getattr(conf_module, test_yaml)
