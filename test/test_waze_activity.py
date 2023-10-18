from typing import cast

from pytest import mark

from tracs.plugins.waze import AccountActivity, Waze, WAZE_ACCOUNT_ACTIVITY_TYPE, WAZE_ACCOUNT_INFO_TYPE, WAZE_TYPE, WazeAccountActivityImporter, WazeImporter

@mark.file( 'takeouts/waze/waze/2020-09/account_activity_3.csv' )
def test_read_account_activity_2020( path ):
	resource = WazeAccountActivityImporter().load( path=path )
	location_details = cast( AccountActivity, resource.data ).location_details
	assert len( location_details ) == 1
	assert len( location_details[0].as_point_list() ) == 25

@mark.file( 'takeouts/waze/waze/2022-01/account_activity_3.csv' )
def test_read_account_activity_2022( path ):
	resource = WazeAccountActivityImporter().load( path=path )
	location_details = cast( AccountActivity, resource.data ).location_details
	assert len( location_details ) == 2
	assert len( location_details[0].as_point_list() ) == 310
	assert len( location_details[1].as_point_list() ) == 316

@mark.file( 'takeouts/waze/waze/2023-04/account_activity_3.csv' )
def test_read_account_activity_2023( path ):
	resource = WazeAccountActivityImporter().load( path=path )
	location_details = cast( AccountActivity, resource.data ).location_details
	assert len( location_details ) == 2
	assert len( location_details[0].as_point_list() ) == 146
	assert len( location_details[1].as_point_list() ) == 71

# dummy test case: can read, but data is not used anywhere
@mark.file( 'takeouts/waze/waze/2023-04/account_info.csv' )
def test_read_account_info( path ):
	resource = WazeAccountActivityImporter().load( path=path )

@mark.file( 'libraries/default/waze/20/07/12/200712074743/200712074743.txt' )
def test_activity_from_raw( path ):
	resource = WazeImporter().load( path )
	assert len( resource.data.points ) == 137

@mark.context( library='default', config='default', takeout='waze', cleanup=False )
@mark.service( cls=Waze )
def test_fetch_default( service ):
	resources = service.fetch( force=False, pretend=False )
	assert len( resources ) == 0

@mark.context( library='default', config='default', takeout='waze', cleanup=False )
@mark.service( cls=Waze )
def test_fetch_from_takeouts( service ):
	resources = service.fetch( force=False, pretend=False, from_takeouts=True )
	assert len( resources ) == 4
