from os import getenv
from typing import List

from pytest import mark
from pytest import skip

from tracs.activity import Activity
from tracs.config import GlobalConfig as gc
from tracs.plugins.polar import BASE_URL
from tracs.plugins.polar import Polar
from tracs.plugins.polar import PolarActivity
from .conftest import ENABLE_LIVE_TESTS

from .fixtures import db_empty_inmemory
from .fixtures import var_dir
from .polar_server import TEST_BASE_URL

def test_constructor():
	polar = Polar()

	assert polar.base_url == f'{BASE_URL}'
	assert polar._login_url == f'{BASE_URL}/login'
	assert polar._ajax_login_url.startswith( f'{BASE_URL}/ajaxLogin?_=' )
	assert polar._events_url == f'{BASE_URL}/training/getCalendarEvents'
	assert polar._export_url == f'{BASE_URL}/api/export/training'

	polar = Polar( base_url = TEST_BASE_URL )

	assert polar.base_url == f'{TEST_BASE_URL}'
	assert polar._login_url == f'{TEST_BASE_URL}/login'
	assert polar._ajax_login_url.startswith( f'{TEST_BASE_URL}/ajaxLogin?_=' )
	assert polar._events_url == f'{TEST_BASE_URL}/training/getCalendarEvents'
	assert polar._export_url == f'{TEST_BASE_URL}/api/export/training'

@mark.service( (Polar, TEST_BASE_URL) )
@mark.service_config( ('test/configurations/default/config.yaml', 'test/configurations/default/state.yaml') )
def test_service( polar_server, service ):
	# login
	service.login()
	assert service.logged_in

	# fetch
	fetched: List[Activity] = list( service._fetch() )

	assert len( fetched ) == 3
	a = fetched[0]
	assert type( a ) is PolarActivity
	assert a.raw is not None
	assert a.raw_id == 300003
	assert a.raw_name == '300003.json'

	assert len( a.resources ) == 4

	# download
	for r in a.resources:
		content, status = service._download_file( a, r )
		assert content is not None and status == 200

@mark.service( (Polar, TEST_BASE_URL) )
@mark.service_config( ('test/configurations/default/config.yaml', 'test/configurations/default/state.yaml') )
@mark.db_inmemory( True )
def test_workflow( polar_server, service, db, var_dir ):
	gc.db = db
	gc.db_dir = var_dir
	service.login()
	fetched = service.fetch( True )

	assert len( fetched ) == 3

@mark.skipif( not getenv( ENABLE_LIVE_TESTS ), reason='live test not enabled' )
@mark.service( (Polar, BASE_URL) )
@mark.service_config( ('var/config_live.yaml', 'var/state_live.yaml' ) )
@mark.db_inmemory( True )
def test_live_workflow( service, db, config_state ):
	gc.db = db
	gc.db_dir = db.path.parent
	gc.db_file = db.path

	service.login()
	assert service.logged_in

	fetched = service.fetch( False )
	assert len( fetched ) > 0

	limit = 1 # don't download everything
	for i in range( limit ):
		service.download( fetched[i], force=True, pretend=False )
