from collections import namedtuple
from datetime import datetime
from importlib import import_module
from importlib.resources import path as pkgpath
from logging import getLogger
from os.path import dirname
from pathlib import Path
from pkgutil import iter_modules
from shutil import copytree, rmtree
from typing import cast, Dict, List, NamedTuple
from typing import Optional
from typing import Tuple

from fs.base import FS
from fs.copy import copy_fs
from fs.errors import NoSysPath
from fs.memoryfs import MemoryFS
from fs.multifs import MultiFS
from fs.subfs import SubFS
from fs.osfs import OSFS
from pytest import fixture
from yaml import load as load_yaml
from yaml import SafeLoader

from tracs.config import ApplicationConfig as cfg, DB_DIRNAME
from tracs.config import ApplicationConfig as state
from tracs.config import ApplicationContext
from tracs.db import ActivityDb
from tracs.pluginmgr import PluginManager
from tracs.registry import Registry
from tracs.rules import RuleParser
from tracs.service import Service
from tracs.utils import FsPath
from .helpers import get_db_as_json
from .helpers import get_file_as_json
from .helpers import get_file_path

log = getLogger( __name__ )

ENABLE_LIVE_TESTS = 'ENABLE_LIVE_TESTS'
PERSISTANCE_NAME = 'persistance_layer'

class Environment( NamedTuple ):
	ctx: ApplicationContext
	db: ActivityDb
	registry: Registry

def marker( request, name, key, default ):
	try:
		m = request.node.get_closest_marker( name )
		if key:
			return m.kwargs[key]
		elif not key:
			return m.args[0]
	except (AttributeError, KeyError, TypeError):
		log.error( f'unable to access marker {name}.{key}', exc_info=True )
		return default

# shared fixtures

@fixture
def config( request ) -> None:
	if marker := request.node.get_closest_marker( 'config' ):
		template = marker.kwargs.get( 'template' )
		writable = marker.kwargs.get( 'writable', False )
		cleanup = marker.kwargs.get( 'cleanup', True )
	else:
		return None

@fixture
def varfs( request ) -> FS:
	with pkgpath( 'test', '__init__.py' ) as test_pkg_path:
		tp = test_pkg_path.parent
		vrp = Path( tp, f'../var/run/{datetime.now().strftime( "%H%M%S_%f" )}' ).resolve()
		vrp.mkdir( parents=True, exist_ok=True )
		log.info( f'created new temporary persistance dir in {str( vrp )}' )
		yield OSFS( str( vrp ) )

# noinspection PyTestUnpassedFixture
@fixture
def fs( request ) -> FS:
	env = marker( request, 'context', 'env', 'empty' )
	persist = marker( request, 'context', 'persist', 'mem' )
	cleanup = marker( request, 'context', 'cleanup', True )

	with pkgpath( 'test', '__init__.py' ) as test_pkg_path:
		tp = test_pkg_path.parent
		env_fs = OSFS( root_path=f'{str( tp )}/environments/{env}' )
		ep = Path( tp, f'environments/{env}' )
		vrp = Path( tp, f'../var/run/{datetime.now().strftime( "%H%M%S_%f" )}' ).resolve()

		if persist in ['disk', 'clone']:
			vrp.mkdir( parents=True, exist_ok=True )
			root_fs = OSFS( str( vrp ), expand_vars=True )
			log.info( f'created new temporary persistance dir in {str( vrp )}' )

			if persist == 'clone':
				copytree( ep, vrp, dirs_exist_ok=True )

		elif persist == 'mem':
			root_fs = MemoryFS()
			log.info( f'using memory as root fs backend' )

			copy_fs( env_fs, root_fs, preserve_time=True )

		else:
			raise ValueError( 'value of key persist needs to be one of [mem, disk, clone]' )

	yield root_fs

	if cleanup:
		if isinstance( root_fs, OSFS ):
			sp = root_fs.getsyspath( '/' )
			if dirname( dirname( sp ) ).endswith( 'var/run' ):  # sanity check: only remove when in var/run
				rmtree( sp, ignore_errors=True )
				log.info( f'cleaned up temporary persistance dir {sp}' )

@fixture
def db_path( request, fs: FS ) -> Path:
	if isinstance( fs, OSFS ):
		path = Path( fs.getsyspath( DB_DIRNAME ) )
		path.mkdir( parents=True, exist_ok=True )
		yield path
	else:
		raise ValueError
	#env = marker( request, 'context', 'env', 'empty' )
	#with pkgpath( 'test', '__init__.py' ) as test_pkg_path:
	#	yield Path( test_pkg_path.parent, f'environments/{env}/db' )

@fixture
def db( request, fs: FS ) -> ActivityDb:
	if isinstance( fs, OSFS ):
		db_fs = OSFS( root_path=fs.getsyspath( DB_DIRNAME ), create=True )
	elif isinstance( fs, MemoryFS ):
		db_fs = MemoryFS()
	else:
		raise ValueError

	summary_types = marker( request, 'db', 'summary_types', [] )
	recording_types = marker( request, 'db', 'recording_types', [] )

	yield ActivityDb( fs=db_fs, summary_types=summary_types, recording_types=recording_types )
	#db_path = Path( env_fs.getsyspath( '/' ), DB_DIRNAME )
	#yield ActivityDb( path=db_path, read_only=False )

@fixture
def ctx( request, fs: FS ) -> ApplicationContext:

	context = ApplicationContext( config_fs=fs, verbose=True )
	yield context

#	try:
#		db_path = db.underlay_fs.getsyspath( '' )
#		context = ApplicationContext( config_dir=dirname( dirname( db_path ) ), verbose=True )
#	except NoSysPath:
#		context = ApplicationContext( config_fs=MemoryFS(), lib_fs=MemoryFS(), db_fs=db.underlay_fs, verbose=True )

#	context.db = db  # attach db to ctx

#	yield context

#	if context.db is not None:
#		context.db.close()

@fixture
def registry( request, ctx: ApplicationContext ) -> Registry:
	resource_types = marker( request, 'resource_type', 'types', [] )

	PluginManager.init()

	yield Registry.create(
		ctx=ctx,
		keywords=PluginManager.keywords,
		normalizers=PluginManager.normalizers,
		resource_types=PluginManager.resource_types,
		importers=PluginManager.importers,
		virtual_fields=PluginManager.virtual_fields,
		setups=PluginManager.setups,
		services=PluginManager.services,
	)

@fixture
def env( request, ctx: ApplicationContext, db: ActivityDb, registry: Registry ) -> Environment:
	return Environment( ctx, db, registry )

@fixture
def json( request ) -> Optional[Dict]:
	if marker := request.node.get_closest_marker( 'db' ):
		template = marker.kwargs.get( 'template', 'empty' )
		return get_db_as_json( template )
	elif marker := request.node.get_closest_marker( 'file' ):
		return get_file_as_json( marker.args[0] )

@fixture
def path( request ) -> Optional[Path]:
	with pkgpath( 'test', '__init__.py' ) as test_path:
		return Path( test_path.parent, marker( request, 'file', None, None ) )

@fixture
def fspath( request ) -> FsPath:
	with pkgpath( 'test', '__init__.py' ) as test_path:
		return FsPath( OSFS( root_path=str( test_path.parent ), create=False ), marker( request, 'file', None, None ) )

@fixture
def config_state( request ) -> Optional[Tuple[Dict, Dict]]:
	config_dict, state_dict = None, None

	if config_marker := request.node.get_closest_marker( 'config_file' ):
		with path( 'test', '__init__.py' ) as test_pkg_path:
			config_path = Path( test_pkg_path.parent.parent, 'var', config_marker.args[0] )
			if config_path.exists():
				cfg.set_file( config_path )
				config_dict = load_yaml( config_path.read_bytes(), SafeLoader )

	if state_marker := request.node.get_closest_marker( 'state_file' ):
		with path( 'test', '__init__.py' ) as test_pkg_path:
			state_path = Path( test_pkg_path.parent.parent, 'var', state_marker.args[0] )
			if state_path.exists():
				state.set_file( state_path )
				state_dict = load_yaml( state_path.read_bytes(), SafeLoader )

	return config_dict, state_dict

@fixture
def service( request, ctx: ApplicationContext, registry: Registry ) -> Optional[Service]:
	service_class = marker( request, 'service', 'cls', None )
	service_class_name = service_class.__name__.lower() if service_class else None
	register = marker( request, 'service', 'register', False )
	init = marker( request, 'service', 'init', False )

	if init:
		# service = service_class( fs=ctx.config_fs, _configuration=ctx.config['plugins'][service_class_name], _state=ctx.state['plugins'][service_class_name] )
		service = service_class( ctx=ctx )
	else:
		service = service_class( fs=fs )

	if register:
		registry.services[service_class_name] = service

	yield service

@fixture
def keywords() -> List[str]:
	# load keywords plugin
	from tracs.plugins.rule_extensions import TIME_FRAMES
	return list( Registry.instance().virtual_fields.keys() )

@fixture
def rule_parser( request, ctx: ApplicationContext, registry: Registry ) -> RuleParser:

	yield RuleParser( keywords=registry.keywords, normalizers=registry.normalizers )
