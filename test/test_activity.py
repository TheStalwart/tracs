
from datetime import datetime, timedelta
from datetime import time

from pytest import mark, raises

from tracs.activity import Activity, ActivityPart
from tracs.activity_types import ActivityTypes
from tracs.core import vfield, VirtualFields
from tracs.registry import Registry, virtualfield
from tracs.resources import Resource
from tracs.uid import UID

@mark.file( 'libraries/default/polar/1/0/0/100001/100001.json' )
def test_union( json ):
	src1 = Activity( id=1, name='One', uids=[ 'a1' ] )
	src2 = Activity( id=2, distance=10, calories=20, uids=['a2'] )
	src3 = Activity( id=3, calories=100, heartrate= 100, uids=[ 'a2', 'a3' ] )

	target = src1.union( [src2, src3], copy=True )
	assert target.name == 'One' and target.distance == 10 and target.calories == 20 and target.heartrate == 100
	assert target.id == 1
	assert target.uids == [ 'a1', 'a2', 'a3' ]
	assert src1.distance is None # source should be untouched

	target = src1.union( others=[src2, src3], force=True, copy=True )
	assert target.name == 'One' and target.distance == 10 and target.calories == 100 and target.heartrate == 100
	assert target.id == 3
	assert src1.distance is None # source should be untouched

	src1.union( [src2, src3], copy=False )
	assert src1.name == 'One' and src1.distance == 10 and src1.calories == 20 and src1.heartrate == 100
	assert src1.id == 1

	# test constructor
	src1 = Activity( id=1, name='One' )
	target = Activity( others=[src1, src2, src3] )
	assert target.name == 'One' and target.distance == 10 and target.calories == 20 and target.heartrate == 100
	assert target.id is None

def test_add():
	src1 = Activity( starttime=datetime( 2022, 2, 22, 7 ), distance=10, duration=timedelta( hours=1 ), heartrate_max=180, heartrate_min=100 )
	src2 = Activity( starttime=datetime( 2022, 2, 22, 8 ), distance=20, duration=timedelta( hours=1, minutes=20 ) )
	src3 = Activity( starttime=datetime( 2022, 2, 22, 9 ), heartrate_max=160, heartrate_min=80 )
	target = src1.add( others=[src2, src3], copy=True )

	assert target.starttime == datetime( 2022, 2, 22, 7 )
	assert target.endtime is None

	assert target.distance == 30
	assert target.ascent is None
	assert target.elevation_max is None

	assert target.duration == timedelta( hours=2, minutes=20 )
	assert target.duration_moving == timedelta( seconds=0 )
	assert target.heartrate_max == 180
	assert target.heartrate_min == 80

def test_activity_part():
	p = ActivityPart( uids=[ 'polar:1234' ] )
	assert p.as_uids == [ UID( classifier='polar', local_id=1234 ) ]
	assert p.classifiers == [ 'polar' ]

	p = ActivityPart( uids=['polar:2345', 'polar:1234' ] )
	assert p.as_uids == [ UID( 'polar:1234' ), UID( 'polar:2345' ) ]
	assert p.classifiers == [ 'polar' ]

	p = ActivityPart( uids=['polar:2345?rec.gpx', 'polar:2345?rec.tcx', 'polar:1234'] )
	assert p.as_uids == [ UID( 'polar:1234' ), UID( 'polar:2345?rec.gpx' ), UID( 'polar:2345?rec.tcx' ) ]
	assert p.as_activity_uids == [ UID( 'polar:1234' ), UID( 'polar:2345' ) ]
	assert p.activity_uids == [ 'polar:1234', 'polar:2345' ]
	assert p.classifiers == [ 'polar' ]

def test_singlepart_activity():
	a = Activity( uids=[ 'polar:101', 'strava:101', 'polar:102' ] )
	assert a.uids == [ 'polar:101', 'polar:102', 'strava:101' ]
	assert a.as_uids == [ UID( 'polar:101' ), UID( 'polar:102' ), UID( 'strava:101' ) ]
	assert a.classifiers == [ 'polar', 'strava' ]

	assert not a.multipart

	a.set_uids( [ 'polar:101', 'polar:101' ] )
	assert a.uids == [ 'polar:101' ]
	assert a.as_uids == [ UID( 'polar:101' ) ]
	assert a.classifiers == [ 'polar' ]

def test_multipart_activity():
	p1 = ActivityPart( uids=['polar:101' ], gap=time( 0, 0, 0 ) )
	p2 = ActivityPart( uids=['polar:102', 'strava:102' ], gap=time( 1, 0, 0 ) )
	a = Activity( parts=[ p1, p2 ] )

	assert a.multipart
	assert a.uids == [ 'polar:101', 'polar:102', 'strava:102' ]
	assert a.as_uids == [ UID( 'polar:101' ), UID( 'polar:102' ), UID( 'strava:102' ) ]
	assert a.classifiers == [ 'polar', 'strava' ]

	p1 = ActivityPart( uids=['polar:101?swim.gpx' ], gap=time( 0, 0, 0 ) )
	p2 = ActivityPart( uids=['polar:101?bike.gpx' ], gap=time( 1, 0, 0 ) )
	p3 = ActivityPart( uids=['polar:101?run.gpx' ], gap=time( 1, 0, 0 ) )
	a = Activity( parts=[ p1, p2, p3 ] )

	assert a.multipart
	assert a.uids == [ 'polar:101' ]
	assert a.as_uids == [ UID( 'polar:101' ) ]
	assert a.classifiers == [ 'polar' ]

def test_resource():
	some_string = 'some string value'
	r = Resource( content=some_string.encode( encoding='UTF-8' ) )
	assert type( r.content ) is bytes and len( r.content ) > 0
	assert r.as_text() == some_string

	r = Resource( text=some_string )
	assert type( r.content ) is bytes and len( r.content ) > 0
	assert r.as_text() == some_string
	assert r.text is None # todo: change to throw exception?

def test_fields():
	# load rule extension plugin
	from tracs.plugins.rule_extensions import TIME_FRAMES

	fields = Activity.fields()
	assert next( f for f in fields if f.name == 'name' )
	field_names = Activity.field_names()
	assert 'name' in field_names and '__uids__' in field_names and 'weekday' not in field_names

	field_names = Activity.field_names( include_internal=False )
	assert 'name' in field_names and '__uids__' not in field_names and 'weekday' not in field_names

	field_names = Activity.field_names( include_virtual=True )
	assert 'name' in field_names and '__uids__' in field_names and 'weekday' in field_names

	assert Activity.field_type( 'name' ) == 'Optional[str]'
	assert Activity.field_type( '__uids__' ) == 'List[UID]'
	assert Activity.field_type( 'weekday' ) == int
	assert Activity.field_type( 'noexist' ) is None

def test_virtual_activity_fields():

	@virtualfield
	def lower_name( a: Activity ) -> str:
		return a.name.lower()

	@virtualfield( name='upper_name' )
	def uppercase_name( a: Activity ) -> str:
		return a.name.upper()

	@virtualfield( name='title_name', type=str, description='titled activity name' )
	def title_name( a: Activity ):
		return a.name.title()

	@virtualfield( name='cap_name', description='capitalized activity name', type=str, display_name='Cap Name' )
	def capitalized_name( a: Activity ):
		return a.name.capitalize()

	assert 'lower_name' in VirtualFields.__fields__.keys()
	assert 'upper_name' in VirtualFields.__fields__.keys()
	assert 'title_name' in VirtualFields.__fields__.keys()
	assert 'cap_name' in VirtualFields.__fields__.keys()

	vf = VirtualFields.__fields__['lower_name']
	assert vf.name == 'lower_name'

	a = Activity(
		name='Afternoon run in Berlin',
		type=ActivityTypes.run,
	)

	assert a.vf.lower_name == 'afternoon run in berlin'
	assert a.vf.upper_name == 'AFTERNOON RUN IN BERLIN'
	assert a.vf.title_name == 'Afternoon Run In Berlin'
	assert a.vf.cap_name == 'Afternoon run in berlin'

	VirtualFields.__fields__['fixed_value'] = vfield( 'fixed_value', int, 10 )

	assert a.vf.fixed_value == 10

	with raises( AttributeError ):
		assert a.vf.does_not_exist == 10

	assert a.getattr( 'lower_name' ) == 'afternoon run in berlin'
	assert a.getattr( 'fixed_value' ) == 10
	assert a.getattr( 'does_not_exist', quiet=True ) is None

	with raises( AttributeError ):
		assert a.getattr( 'does_not_exist' ) is None

# don't allow overriding fields
def test_virtual_activity_field_override():

	a = Activity( id = 100, name='Run', type=ActivityTypes.run )

	@virtualfield
	def name( a: Activity ) -> str:
		return 'override attempt for run'

	assert 'name' in VirtualFields.__fields__
	assert a.name == 'Run' and a.getattr( 'name' ) == 'Run'
